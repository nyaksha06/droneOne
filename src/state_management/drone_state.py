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
        """Initializes the DroneState with default empty values."""
        self._telemetry_data = {}
        self._visual_insights = {}
        self._mission_objectives = "No specific mission objective set."
        self._current_flight_mode = "UNKNOWN" 
        self._last_action = "None"

        logger.info("DroneState initialized.")

    def update_telemetry(self, telemetry_data: dict):
        """
        Updates the drone's telemetry data.
        :param telemetry_data: Dictionary of processed telemetry from TelemetryProcessor.
        """
        self._telemetry_data = telemetry_data
        # logger.debug(f"DroneState updated with telemetry: {telemetry_data.get('position', {}).get('relative_altitude_m')}")

    def update_visual_insights(self, visual_insights: dict):
        """
        Updates the drone's visual insights from camera processing.
        :param visual_insights: Dictionary of insights from CameraProcessor.
        """
        self._visual_insights = visual_insights
        # logger.debug(f"DroneState updated with visual insights: {visual_insights.get('detected_objects')}")

    def set_mission_objectives(self, objective: str):
        """
        Sets the current mission objective for the drone.
        :param objective: A string describing the current mission objective.
        """
        self._mission_objectives = objective
        logger.info(f"Mission objective set: {objective}")

    def update_flight_mode(self, flight_mode: str):
        """
        Updates the current flight mode of the drone.
        :param flight_mode: The current flight mode string.
        """
        self._current_flight_mode = flight_mode
        # logger.debug(f"Flight mode updated to: {flight_mode}")

    def update_last_action(self, last_action: str):
        self._last_action = last_action    

    def get_current_state(self) -> dict:
        """
        Returns the complete current state of the drone.
        """
        return {
            "last_action": self._last_action,
            "telemetry": self._telemetry_data,
            "visual_insights": self._visual_insights,
            "mission_objectives": self._mission_objectives,
            "current_flight_mode": self._current_flight_mode,
            "timestamp": asyncio.get_event_loop().time() 
        }

    def generate_llm_prompt(self) -> str:
        """
        Generates a concise, textual prompt for the LLM based on the current drone state.
        This prompt summarizes all relevant information for the LLM's decision-making.
        """
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
            f"You are a highly precise drone control AI assistant. "
            f"Your ONLY task is to output a single JSON object representing a drone command. "
            f"You MUST NOT include any conversational text, explanations, or extraneous characters "
            f" here is current drone state and mission statement output next step with appropriate parameters."
            f"Current Drone Status:\n"
            f"  - Flight Mode: {state.get('current_flight_mode')}\n"
            f"  - Telemetry: {telemetry_str}\n"
            f"  - Visual Insights: {visual_str}\n"
            f"  - Mission Objective: {state.get('mission_objectives')}\n\n"
            f"  -Last Action: {self._last_action}"
            f"Based on this information, what is the optimal next action for the drone to achieve its mission?\n"
            f'choose action from "takeoff" , "land" , "goto_location" , "do_nothing" only.\n'
            f"The JSON object should conform to the following schema:\n"
            f"```json\n"
            f"{{\n"
            f'  "action": "takeoff" | "land" | "goto_location" | "do_nothing",\n'
            f'  "parameters": {{\n'
            f'    "altitude_m"?: float,      // Required for "takeoff", "goto_location" (e.g.,20)\n'
            f'    "north_dist"?: float,    // Required for "goto_location" (e.g., 5 )\n'
            f'    "east_dist"?: float    // Required for "goto_location" (e.g., 7)\n'
            f'  }},\n'
            f'  "reason"?: string           // Optional human-readable reason for the action\n'
            f"}}\n"
            f"```\n"
            f"Ensure the JSON is well-formed and strictly follows this schema. Only output the JSON."
        )
        
        # logger.debug(f"Generated LLM Prompt:\n{prompt}")
        return prompt

