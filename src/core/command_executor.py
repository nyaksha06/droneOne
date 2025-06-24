import asyncio
import logging
import sys
from mavsdk.action import ActionError

logger = logging.getLogger(__name__)

class CommandExecutor:
    """
    Translates structured commands (from LLM or human) into MAVSDK API calls
    and sends them to the drone.
    Includes basic safety checks.
    """

    def __init__(self, mavsdk_interface):
        """
        Initializes the CommandExecutor.
        :param mavsdk_interface: An instance of MAVSDKInterface.
        """
        self.mavsdk_interface = mavsdk_interface
        logger.info("CommandExecutor initialized.")

    async def execute_command(self, command: dict) -> bool:
        """
        Executes a structured drone command.
        :param command: A dictionary representing the command (e.g., {"action": "takeoff", "parameters": {"altitude_m": 10.0}}).
        :return: True if the command was successfully sent/initiated, False otherwise.
        """
        action_type = command.get("action")
        parameters = command.get("parameters", {})
        reason = command.get("reason", "No specific reason provided.")

        if not self.mavsdk_interface.is_connected:
            logger.warning(f"Drone not connected. Cannot execute command: {action_type}. Reason: {reason}")
            return False

        logger.info(f"Executing command: {action_type} with parameters {parameters}. Reason: {reason}")
        success = False
        try:
            if action_type == "takeoff":
                altitude = parameters.get("altitude_m", 2.5) 
                success = await self.mavsdk_interface.arm() and await self.mavsdk_interface.takeoff(altitude)
            elif action_type == "land":
                success = await self.mavsdk_interface.land()
            elif action_type == "goto_location":
                latitude = parameters.get("latitude_deg")
                longitude = parameters.get("longitude_deg")
                altitude = parameters.get("altitude_m")
                if latitude is not None and longitude is not None and altitude is not None:
                    latitude = float(latitude)
                    longitude = float(longitude)
                    altitude = float(altitude)
                    # skipping  goto for now , it will require mode switching
                    logger.warning("goto_location is not fully implemented for MAVSDK 1.3.0 API and needs careful testing.")
                    logger.warning(f"Attempting to go to Lat: {latitude}, Lon: {longitude}, Alt: {altitude}")
                    
                else:
                    logger.error(f"Goto command missing required parameters: {parameters}")
                    success = False
            elif action_type == "do_nothing":
                logger.info("Command is 'do_nothing'. Drone maintains current state.")
                success = True
            elif action_type == "disarm": # Added for human override testing
                success = await self.mavsdk_interface.disarm()
            else:
                logger.warning(f"Unknown command type received: {action_type}. Doing nothing.")
                success = False

        except ActionError as e:
            logger.error(f"MAVSDK ActionError for {action_type}: {e}")
            success = False
        except Exception as e:
            logger.error(f"Unexpected error during command execution for {action_type}: {e}", exc_info=True)
            success = False

        return success

