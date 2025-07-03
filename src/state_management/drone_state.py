import logging
import sys
import asyncio # Re-added for timestamp in get_current_state

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
        # logger.debug(f"DroneState updated with telemetry: {telemetry_data.get('position', {}).get('relative_altitude_m')}")

    def update_visual_insights(self, visual_insights: dict):
        """
        Updates the drone's visual insights from camera processing.
        :param visual_insights: Dictionary of insights from CameraProcessor.
        """
        self._visual_insights = visual_insights
        # logger.debug(f"DroneState updated with visual insights: {visual_insights.get('detected_objects')}")

    def set_mission_objectives(self, objective: str, mission_steps: list = None): # Re-added
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
        # logger.debug(f"Flight mode updated to: {flight_mode}")

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
            telemetry_summary.append(f"Rel Alt: {position_data['relative_altitude_m']:.2f}m")
        if position_data.get("latitude_deg") is not None and position_data.get("longitude_deg") is not None:
             telemetry_summary.append(f"Lat/Lon: {position_data['latitude_deg']:.4f},{position_data['longitude_deg']:.4f}")
        if position_ned_data.get("north_m") is not None:
            telemetry_summary.append(f"NED Pos: N={position_ned_data['north_m']:.2f}m, E={position_ned_data['east_m']:.2f}m, D={position_ned_data['down_m']:.2f}m")
        if velocity_data.get("ground_speed_m_s") is not None:
            telemetry_summary.append(f"Ground Speed: {velocity_data['ground_speed_m_s']:.2f}m/s")
        if battery_data.get("remaining_percent") is not None:
            telemetry_summary.append(f"Battery: {battery_data['remaining_percent']:.1f}%")
        
        telemetry_str = ", ".join(telemetry_summary) if telemetry_summary else "Telemetry data unavailable."

        # Build visual insights summary and identify primary detected object
        visual_summary = []
        primary_detected_object = None
        detected_objects = state.get("visual_insights", {}).get("detected_objects", [])
        
        if detected_objects:
            # Assume the first detected object is the primary focus for the LLM
            primary_detected_object = detected_objects[0]
            for obj in detected_objects:
                visual_summary.append(
                    f"{obj.get('type')} at {obj.get('distance_m')}m {obj.get('relative_position')}"
                )
            visual_str = "Detected: " + "; ".join(visual_summary) + "."
        else:
            visual_str = "No objects currently detected."

        flying_status = "is flying" if is_flying else "is on the ground"
        armed_status = "is armed" if is_armed else "is disarmed"
        
        # --- LLM Prompt Logic for Trigger-Based Control ---
        
        # Base instruction for the LLM
        prompt_instruction = (
            f"You are a drone control AI assistant. Your ONLY task is to output a single JSON object representing a drone command.\n"
            f"You MUST NOT include any conversational text, explanations, or extraneous characters outside the JSON.\n\n"
        )

        # Contextual information for the LLM
        contextual_info = (
            f"Current Drone Status:\n"
            f"  - Drone {flying_status} and {armed_status}\n" # Added armed status
            f"  - Flight Mode: {flight_mode}\n" # Used flight_mode from processed data
            f"  - Telemetry: {telemetry_str}\n"
            f"  - Visual Insights: {visual_str}\n"
            f"  - Last Executed Command: {state.get('last_executed_command', {}).get('action', 'none')} (Reason: {state.get('last_executed_command', {}).get('reason', 'N/A')})\n\n"
        )

        # LLM's specific role based on human control and trigger status
        llm_role_guidance = ""
        if state["human_control_active"]:
            llm_role_guidance = (
                f"The human operator currently has full control. "
                f"Your role is currently paused. Therefore, you MUST output 'do_nothing'."
            )
        elif state["llm_following_active"]:
            # If LLM is already following, it needs to continue or adjust
            llm_role_guidance = (
                f"You are currently autonomously following a detected target. "
                f"Based on current telemetry and visual insights, continue to maintain optimal follow parameters for the primary detected object ({primary_detected_object.get('type', 'N/A')}). "
                f"If the target is lost or the situation changes, you may suggest 'do_nothing' or 'land'."
            )
        elif primary_detected_object:
            # If a trigger is detected and human has released control, LLM needs to react to the trigger
            llm_role_guidance = (
                f"A new activity/object ('{primary_detected_object.get('type', 'N/A')}') has been detected at {primary_detected_object.get('distance_m', 'N/A')}m {primary_detected_object.get('relative_position', 'N/A')}. "
                f"The human operator has released control, and you need to propose the optimal action to address this trigger. "
                f"Consider actions like 'follow_target' to autonomously track it, or 'do_nothing' if no action is needed."
            )
        else:
            # Human has released control, but no trigger is active (e.g., after a follow completes)
            llm_role_guidance = (
                f"The human operator has released control, but no specific activity or object is currently detected. "
                f"You should maintain the drone's current position/altitude by outputting 'do_nothing', "
                f"or suggest 'land' if appropriate."
            )

        # Define the JSON schema, including the new 'follow_target' action
        json_schema = (
            f"The JSON object should conform to the following schema. Ensure all required parameters for the chosen action are present:\n"
            f"```json\n"
            f"{{\n"
            f'  "action": "takeoff" | "land" | "goto_location" | "follow_target" | "do_nothing",\n'
            f'  "parameters": {{\n'
            f'    // Required for "takeoff":\n'
            f'    "altitude_m"?: float, // Target altitude in meters (e.g., 20.0)\n'
            f'\n'
            f'    // Required for "goto_location" (relative to current position):\n'
            f'    "north_m"?: float, // Distance North in meters (positive) or South (negative) (e.g., 10.0)\n'
            f'    "east_m"?: float,  // Distance East in meters (positive) or West (negative) (e.g., 0.0)\n'
            f'    "altitude_m"?: float // Target relative altitude in meters (e.g., 20.0)\n'
            f'\n'
            f'    // Required for "follow_target":\n'
            f'    "target_id"?: string, // Identifier for the target to follow (e.g., "person_1", "vehicle_A")\n'
            f'    "follow_distance_m"?: float, // Desired distance to maintain from the target in meters (e.g., 10.0)\n'
            f'    "altitude_m"?: float // Desired relative altitude to maintain while following (e.g., 15.0)\n'
            f'  }},\n'
            f'  "reason"?: string // Optional human-readable reason for the action\n'
            f"}}\n"
            f"```\n"
            f"Only output the JSON object."
        )
        
        # Combine all parts of the prompt
        prompt = f"{prompt_instruction}{contextual_info}{llm_role_guidance}\n\n{json_schema}"
        
        return prompt

