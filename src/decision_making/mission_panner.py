import httpx
import json
import asyncio
from typing import Dict, Any
import logging


logger = logging.getLogger(__name__)


class LLMMissionPlanner:

    def __init__(self, ollama_api_url: str, ollama_model_name: str):
        self.ollama_api_url = ollama_api_url
        self.ollama_model_name = ollama_model_name
        self.headers = {"Content-Type": "application/json"}
        logger.info(f"LLMDecisionEngine initialized for model '{ollama_model_name}' at {ollama_api_url}")


    async def get_mission_plan(self,mission_statement: str) -> Dict[str, Any]:
        prompt_content = f"""
            You are a highly accurate Drone Mission Planner AI.

            Your task is to convert the given mission statement (written in simple natural language) into a step-by-step list of **structured micro steps** for the drone.

            You are limited to using only **three actions**:
            - `"takeoff"` — with a specified altitude in meters.
            - `"goto"` — move relative to the current position with directions in meters (north/south, east/west) and maintain a specified altitude.
            - `"land"` — end the mission.

            ### Response Format Rules:
            - Respond in **valid JSON only**.
            - Do **not include any extra text**, explanations, or comments.
            - Each step must have a key like `"step 1"`, `"step 2"`, etc.
            - The value is a string describing the action and parameters.

            ### Example JSON Format:
            {{
            "step 1": "takeoff to 20m",
            "step 2": "goto north 5m, east -10m, altitude 20m",
            "step 3": "goto north 10m, east -5m, altitude 30m",
            "step 4": "land"
            }}

            ### Mission:
            {mission_statement}
            """

        payload = {
            "model": self.ollama_model_name,
            "prompt": prompt_content,
            "stream": False,
            "format": "json"
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(f"{self.ollama_api_url}/api/generate", json=payload)
                response.raise_for_status()

                response_json = response.json()
                raw_text = response_json.get("response", "").strip()

                try:
                    # Attempt to parse directly
                    parsed_json = json.loads(raw_text)
                    return parsed_json
                except json.JSONDecodeError:
                    # Fallback: Clean markdown artifacts if any (shouldn't happen with format='json')
                    clean_text = (
                        raw_text.replace("```json", "")
                        .replace("```", "")
                        .strip()
                    )
                    parsed_json = json.loads(clean_text)
                    return parsed_json

        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON parsing error from Ollama: {e}")
            print(f"[DEBUG] Ollama Raw Response:\n{raw_text}")
            return {"action": "error", "message": f"Invalid JSON response: {e}"}

        except httpx.RequestError as e:
            print(f"[ERROR] Network error communicating with Ollama: {e}")
            return {"action": "error", "message": f"Connection failed: {e}"}

        except httpx.HTTPStatusError as e:
            print(f"[ERROR] HTTP error {e.response.status_code} - {e.response.text}")
            return {"action": "error", "message": f"HTTP error {e.response.status_code}: {e.response.text}"}

        except Exception as e:
            print(f"[ERROR] Unexpected error: {e}")
            return {"action": "error", "message": f"Unexpected error: {e}"} 