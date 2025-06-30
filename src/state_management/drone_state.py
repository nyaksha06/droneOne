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
        self._current_flight_mode = "UNKNOWN" 
        self._last_action = "None"

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

    def update_flight_mode(self, flight_mode: str):
        self._current_flight_mode = flight_mode
        # logger.debug(f"Flight mode updated to: {flight_mode}")

    def update_last_action(self, last_action: str):
        self._last_action = last_action    

    def get_current_state(self) -> dict:
        return {
            "last_action": self._last_action,
            "telemetry": self._telemetry_data,
            "visual_insights": self._visual_insights,
            "mission_objectives": self._mission_objectives,
            "current_flight_mode": self._current_flight_mode,
            "timestamp": asyncio.get_event_loop().time() 
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
    " Current Drone Status:\n"
    f"  - Flight Mode: {state.get('current_flight_mode')}\n"
    f"  - Telemetry: {telemetry_str}\n"
    f"  - Visual Insights: {visual_str}\n"
    f"  - Mission Objective: {state.get('mission_objectives')}\n"
    f"  - Last Action: {self._last_action}\n\n"
    " Instructions:\n"
    "- Carefully analyze the current mission objective and the last action.\n"
    "- Decide the optimal next step toward completing the mission.\n"
    "- Choose ONLY from the following actions: \"takeoff\", \"goto_location\", \"land\".\n\n"
    " JSON Schema:\n"
    "```json\n"
    "{\n"
    '  "action": "takeoff" | "goto_location" | "land",\n'
    '  "parameters": {\n'
    '    "altitude_m"?: float,       // For "takeoff" and "goto_location"\n'
    '    "north_dist"?: float,       // For "goto_location"\n'
    '    "east_dist"?: float         // For "goto_location"\n'
    "  },\n"
    '  "reason"?: string             // (Optional) Brief reason for the action\n'
    "}\n"
    "```\n\n"
    " IMPORTANT:\n"
    "- Ensure the JSON is well-formed and syntactically valid.\n"
    "- If the action is \"land\", parameters can be an empty object `{}`.\n"
    "- Only output the JSON object. No text before or after.\n"
)

        
        # logger.debug(f"Generated LLM Prompt:\n{prompt}")
        return prompt

