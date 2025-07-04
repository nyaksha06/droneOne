import httpx # Assuming httpx for async HTTP requests
import json
import logging
import sys

logger = logging.getLogger(__name__)

class LLMDecisionEngine:
    """
    Interacts with the Large Language Model (LLM) to get drone command suggestions.
    """

    def __init__(self, ollama_api_url: str, ollama_model_name: str, timeout: int = 30): # Increased default timeout
        """
        Initializes the LLMDecisionEngine.
        :param ollama_api_url: The URL of the Ollama API endpoint (e.g., "http://localhost:11434/api/generate").
        :param ollama_model_name: The name of the Ollama model to use (e.g., "llama2", "mistral").
        :param timeout: Timeout for the API request in seconds.
        """
        self.ollama_api_url = ollama_api_url
        self.ollama_model_name = ollama_model_name
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=self.timeout) # Use httpx.AsyncClient
        logger.info(f"LLMDecisionEngine initialized for model '{ollama_model_name}' at {ollama_api_url} with timeout {timeout}s.")

    async def get_action_from_llm(self, prompt: str) -> dict:
        """
        Sends the current drone state as a prompt to the LLM and parses its response.
        :param prompt: The formatted prompt string describing the drone's current state and task.
        :return: A dictionary representing the LLM's suggested action, or {"action": "do_nothing"} on error.
        """
        logger.info("Sending prompt to LLM...")
        logger.debug(f"LLM Prompt:\n{prompt}")

        payload = {
            "model": self.ollama_model_name,
            "prompt": prompt,
            "stream": False, # We want a single response, not a stream
            "options": {
                "temperature": 0.2, # Make it more deterministic
                "num_ctx": 4096 # Context window size, adjust based on model
            }
        }

        try:
            response = await self.client.post(self.ollama_api_url, json=payload)
            response.raise_for_status() # Raise an exception for 4xx/5xx responses

            response_data = response.json()
            
            # Ollama's /api/generate returns a JSON object with a 'response' field
            llm_raw_response_text = response_data.get("response", "").strip()

            logger.info(f"LLM Raw Response: {llm_raw_response_text}")

            # Attempt to parse the JSON from the LLM's response
            # The LLM might embed the JSON in markdown code blocks
            if llm_raw_response_text.startswith("```json") and llm_raw_response_text.endswith("```"):
                json_str = llm_raw_response_text[len("```json"): -len("```")].strip()
            else:
                json_str = llm_raw_response_text # Assume it's direct JSON

            try:
                llm_action = json.loads(json_str)
                if not isinstance(llm_action, dict) or "action" not in llm_action:
                    logger.warning(f"LLM response was not a valid action dictionary. Raw: {llm_raw_response_text}")
                    return {"action": "do_nothing", "reason": "LLM response format invalid."}
                logger.info(f"LLM parsed action: {llm_action.get('action')}")
                return llm_action
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM response as JSON: {e}. Raw response: {llm_raw_response_text}")
                return {"action": "do_nothing", "reason": f"LLM response JSON decode error: {e}"}

        except httpx.TimeoutException as e:
            logger.error(f"LLM API request timed out after {self.timeout} seconds: {e}")
            return {"action": "do_nothing", "reason": "LLM API timeout."}
        except httpx.RequestError as e:
            logger.error(f"LLM API request failed due to network or connection error: {e}")
            return {"action": "do_nothing", "reason": "LLM API connection error."}
        except httpx.HTTPStatusError as e:
            logger.error(f"LLM API returned an error status {e.response.status_code}: {e.response.text}")
            return {"action": "do_nothing", "reason": f"LLM API HTTP error: {e.response.status_code}"}
        except Exception as e:
            logger.exception(f"An unexpected error occurred during LLM API call: {e}")
            return {"action": "do_nothing", "reason": f"Unexpected LLM API error: {e}"}

