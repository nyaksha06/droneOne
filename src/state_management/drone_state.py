import logging
import sys
import asyncio

logger = logging.getLogger(__name__)

class DroneState:
    """
    Manages the comprehensive state of the drone, aggregating data from
    telemetry and camera processing units, and preparing context for the LLM.
    """

    def __init__(self):
        self._telemetry_data = {}
        self._visual_insights = {}
        self._mission_objectives = "No specific mission objective set."
        self._last_actions = []
        self._mission_plan = None

        logger.info("DroneState initialized.")

    def update_telemetry(self, telemetry_data: dict):
        self._telemetry_data = telemetry_data
        # logger.debug(f"DroneState updated with telemetry: {telemetry_data.get('position', {}).get('relative_altitude_m')}")

    def update_visual_insights(self, visual_insights: dict):
        self._visual_insights = visual_insights
        # logger.debug(f"DroneState updated with visual insights: {visual_insights.get('detected_objects')}")

    def set_mission_objectives(self, objective: str):
        self._mission_objectives = objective
        logger.info(f"Mission objective set: {objective}")

    def update_last_actions(self, last_action: str):
        self._last_actions.append(last_action)     

    def update_mission_plan(self,mission_plan):
        self._mission_plan = mission_plan    
        print("Drone Mission Plan Updated")

    def get_current_state(self) -> dict:
        return {
            "last_actions": self._last_actions,
            "mission_plan": self._mission_plan,
            "telemetry": self._telemetry_data,
            "visual_insights": self._visual_insights,
            "mission_objectives": self._mission_objectives,
            
        }

    def generate_llm_prompt(self) -> str:
        state = self.get_current_state()
        
        telemetry = state.get("telemetry", {})
        position = telemetry.get("position", {})
        velocity = telemetry.get("velocity", {})
        battery = telemetry.get("battery", {})

        
        # Build telemetry summary
        telemetry_summary = []
        if position.get("relative_altitude_m") is not None:
            telemetry_summary.append(f"Rel Alt: {position['relative_altitude_m']:.2f}m")
        if position.get("latitude_deg") is not None and position.get("longitude_deg") is not None:
             telemetry_summary.append(f"Lat/Lon: {position['latitude_deg']:.4f},{position['longitude_deg']:.4f}")
        if velocity.get("ground_speed_m_s") is not None:
            telemetry_summary.append(f"Ground Speed: {velocity['ground_speed_m_s']:.2f}m/s")
        if battery.get("remaining_percent") is not None:
            telemetry_summary.append(f"Battery: {battery['remaining_percent']:.1f}%")
        telemetry_str = ", ".join(telemetry_summary) if telemetry_summary else "Telemetry data unavailable."

        # Build visual insights summary
        visual_summary = []
        detected_objects = state.get("visual_insights", {}).get("detected_objects", [])
        if detected_objects:
            for obj in detected_objects:
                visual_summary.append(
                    f"{obj.get('type')} at {obj.get('distance_m')}m {obj.get('relative_position')}"
                )
            visual_str = "Detected: " + "; ".join(visual_summary) + "."
        else:
            visual_str = "No objects currently detected."


        
        # Construct the final prompt
        prompt = (
    "You are an autonomous drone mission planner AI.\n"
    "Your ONLY task is to output a single JSON object representing the drone's next command.\n\n"
    " STRICT RULES:\n"
    "- DO NOT include any conversational text, comments, or explanations.\n"
    "- ONLY output a valid JSON object matching the schema below.\n"
    "- Think step-by-step internally but output ONLY the next command as JSON.\n\n"
    f"  -Here is your Mission Plan: {state.get('mission_plan')}\n"
    
    f"  -We have taken these steps -> Last Action: {self._last_actions}\n\n"
    "Now you have to provide next step from takeoff | goto | Land and follow instruction provided below."
    "If last_actions is empty means mission has not started so start with Takeoff,if we are in middle of the mission than do not output Takeoff , if we have completed all the mission steps in last actions and output Land."
    " Instructions:\n"
    "- Carefully analyze the current mission plan and the last action.\n"
    "- Decide the optimal next step toward completing the mission.\n"
    "- Choose ONLY from the following actions: \"takeoff\", \"goto\", \"land\".\n\n"
    " JSON Schema:\n"
    "```json\n"
    "{\n"
    '  "action": "takeoff" | "goto" | "land",\n'
    '  "parameters": {\n'
    '    "altitude_m"?: float,       // For "takeoff" and "goto"\n'
    '    "north_dist"?: float,       // For "goton"\n'
    '    "east_dist"?: float         // For "goto"\n'
    "  },\n"
    "}\n"
    "```\n\n"
    " IMPORTANT:\n"
    "- Provide all three parameter every time. if one is not in use than keep it's value 0."
    "- Ensure the JSON is well-formed and syntactically valid.\n"
    "- If the action is \"land\", parameters can be an empty object `{}`.\n"
    "- Only output the JSON object. No text before or after.\n"
)

        
        # logger.debug(f"Generated LLM Prompt:\n{prompt}")
        return prompt

