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
        self._current_mission_stage = "INITIALIZING"
        self._mission_plan_steps = []
        self._last_executed_command = {"action": "none", "reason": "System startup."}
        self._human_control_active = True
        self._llm_following_active = False

        logger.info("DroneState initialized.")

    def update_telemetry(self, telemetry_data: dict):
        """
        Updates the drone's telemetry data.
        :param telemetry_data: Dictionary of processed telemetry from SimTelemetryProcessor.
        """
        self._telemetry_data = telemetry_data

    def update_visual_insights(self, visual_insights: dict):
        """
        Updates the drone's visual insights from camera processing.
        :param visual_insights: Dictionary of insights from CameraProcessor.
        """
        self._visual_insights = visual_insights

    def set_mission_objectives(self, objective: str, mission_steps: list = None):
        """
        Sets the current mission objective and optionally a list of structured mission steps.
        """
        self._mission_objectives = objective
        if mission_steps:
            self._mission_plan_steps = mission_steps
        else:
            self._mission_plan_steps = []
        logger.info(f"Mission objective set: {objective}")
        if self._mission_plan_steps:
            logger.info(f"Mission plan steps: {self._mission_plan_steps}")

    def set_current_mission_stage(self, stage: str):
        """
        Sets the current stage of the mission.
        """
        if self._current_mission_stage != stage:
            logger.info(f"Mission stage updated: {self._current_mission_stage} -> {stage}")
            self._current_mission_stage = stage

    def set_last_executed_command(self, command: dict):
        """
        Sets the last command that was successfully executed by the drone.
        """
        self._last_executed_command = command
        logger.debug(f"Last executed command updated: {command.get('action')}")

    def set_human_control_status(self, is_active: bool):
        """
        Updates whether human control is currently active.
        """
        if self._human_control_active != is_active:
            logger.info(f"Human control status changed: {self._human_control_active} -> {is_active}")
            self._human_control_active = is_active

    def set_llm_following_status(self, is_active: bool):
        """
        Updates whether the LLM is currently actively following a target.
        """
        if self._llm_following_active != is_active:
            logger.info(f"LLM following status changed: {self._llm_following_active} -> {is_active}")
            self._llm_following_active = is_active

    def update_flight_mode(self, flight_mode: str):
        """
        Updates the current flight mode of the drone.
        :param flight_mode: The current flight mode string.
        """
        self._current_flight_mode = flight_mode

    def get_current_state(self) -> dict:
        """
        Returns the complete current state of the drone.
        """
        return {
            "telemetry": self._telemetry_data,
            "visual_insights": self._visual_insights,
            "mission_objectives": self._mission_objectives,
            "current_flight_mode": self._current_flight_mode,
            "current_mission_stage": self._current_mission_stage,
            "mission_plan_steps": self._mission_plan_steps,
            "last_executed_command": self._last_executed_command,
            "human_control_active": self._human_control_active,
            "llm_following_active": self._llm_following_active,
            "timestamp": asyncio.get_event_loop().time()
        }

    def generate_llm_prompt(self) -> str:
        """
        Generates a concise, textual prompt for the LLM based on the current drone state.
        This prompt summarizes all relevant information for the LLM's decision-making.
        """
        state = self.get_current_state()
        
        telemetry = state.get("telemetry", {})
        
        # Extract specific telemetry fields for the prompt
        position_data = telemetry.get("position", {})
        position_ned_data = telemetry.get("position_ned", {})
        velocity_data = telemetry.get("velocity", {})
        battery_data = telemetry.get("battery", {})
        is_flying = telemetry.get("is_flying", False)
        is_armed = telemetry.get("is_armed", False)
        flight_mode = telemetry.get("flight_mode", "UNKNOWN")

        # Build telemetry summary string from the dictionary
        telemetry_summary = []
        if position_data.get("relative_altitude_m") is not None:
            telemetry_summary.append(f"Alt: {position_data['relative_altitude_m']:.1f}m")
        if position_ned_data.get("north_m") is not None:
            telemetry_summary.append(f"Pos(NED): N{position_ned_data['north_m']:.1f} E{position_ned_data['east_m']:.1f} D{position_ned_data['down_m']:.1f}m")
        if velocity_data.get("ground_speed_m_s") is not None:
            telemetry_summary.append(f"Speed: {velocity_data['ground_speed_m_s']:.1f}m/s")
        if battery_data.get("remaining_percent") is not None:
            telemetry_summary.append(f"Bat: {battery_data['remaining_percent']:.0f}%")
        
        telemetry_str = ", ".join(telemetry_summary) if telemetry_summary else "N/A"

        # Build visual insights summary and identify primary detected object
        visual_summary_items = []
        primary_detected_object = None
        detected_objects = state.get("visual_insights", {}).get("detected_objects", [])
        
        if detected_objects:
            primary_detected_object = detected_objects[0]
            for obj in detected_objects:
                obj_type = obj.get('type')
                obj_id = obj.get('id', 'N/A')
                obj_pos_ned = obj.get('absolute_position_ned', {})
                visual_summary_items.append(
                    f"{obj_type} (ID:{obj_id}) @N{obj_pos_ned.get('north_m', 'N/A'):.1f} E{obj_pos_ned.get('east_m', 'N/A'):.1f} D{obj_pos_ned.get('down_m', 'N/A'):.1f}m"
                )
            visual_str = "Detected: " + "; ".join(visual_summary_items)
        else:
            visual_str = "No objects detected."

        # --- NEW CONCISE LLM Prompt Logic ---
        
        # Core Instruction
        prompt_instruction = (
            f"You are a drone control AI. Output ONLY a JSON command.\n"
        )

        # Current State Summary
        contextual_info = (
            f"Drone Status: {'Flying' if is_flying else 'Grounded'}, {'Armed' if is_armed else 'Disarmed'}, Mode: {flight_mode}\n"
            f"Telemetry: {telemetry_str}\n"
            f"Visuals: {visual_str}\n"
            f"Last Cmd: {state.get('last_executed_command', {}).get('action', 'none')}\n"
        )

        # Role-based Guidance
        llm_role_guidance = ""
        if state["human_control_active"]:
            llm_role_guidance = "Human has control. Output: {'action': 'do_nothing'}"
        elif state["llm_following_active"]:
            # LLM is already following, just needs to affirm or stop
            llm_role_guidance = (
                f"You are following a target. Continue to follow by outputting 'follow_target'. "
                f"If target lost or situation changes, suggest 'do_nothing' or 'land'."
            )
        elif primary_detected_object: # Only check for primary_detected_object, not its specific NED
            llm_role_guidance = (
                f"New trigger detected. Human released control. Propose 'follow_target' to track it, or 'do_nothing'."
            )
        else:
            llm_role_guidance = "Human released control, no trigger. Maintain position ('do_nothing') or 'land'."

        # JSON Schema (simplified for follow_target)
        json_schema = (
            f"```json\n"
            f"{{\n"
            f'  "action": "takeoff" | "land" | "goto_location" | "follow_target" | "do_nothing",\n'
            f'  "parameters": {{\n'
            f'    "altitude_m"?: float, // for takeoff/goto_location\n'
            f'    "north_m"?: float, // for goto_location\n'
            f'    "east_m"?: float,  // for goto_location\n'
            f'    "target_id"?: string // for follow_target (optional, if multiple targets)\n'
            f'  }},\n'
            f'  "reason"?: string\n'
            f"}}\n"
            f"```"
        )
        
        prompt = f"{prompt_instruction}\n{contextual_info}\n{llm_role_guidance}\n\n{json_schema}"
        
        return prompt

