import asyncio
import logging
import math
from mavsdk import System
from mavsdk.offboard import OffboardError, PositionNedYaw, VelocityNedYaw
from mavsdk.action import ActionError

# Assuming MAVSDKInterface is in src.core
from src.core.mavsdk_interface import MAVSDKInterface 
# Assuming DroneState is in src.state_management
from src.state_management.drone_state import DroneState # NEW: Import DroneState

logger = logging.getLogger(__name__)

# Define default follow parameters here, or make them configurable in settings.py
DEFAULT_FOLLOW_DISTANCE_M = 5.0  # meters behind/around target
DEFAULT_FOLLOW_ALTITUDE_M = 10.0 # meters relative altitude for the drone

class CommandExecutor:
    """
    Executes drone commands by translating high-level actions into MAVSDK calls.
    Handles offboard control setup and continuous setpoint streaming (for actions like follow_target).
    """

    def __init__(self, mavsdk_interface: MAVSDKInterface, drone_state: DroneState): # MODIFIED: Take DroneState instance
        """
        Initializes the CommandExecutor.
        :param mavsdk_interface: An instance of MAVSDKInterface for drone communication.
        :param drone_state: An instance of DroneState to access current system state.
        """
        self.mavsdk_interface = mavsdk_interface
        self.drone = mavsdk_interface.drone
        self.drone_state = drone_state # Store DroneState instance
        self._offboard_setpoint_task = None
        self._offboard_active = False
        self._current_offboard_setpoint = PositionNedYaw(0.0, 0.0, 0.0, 0.0)
        
        self._target_info = None 
        self._follow_task = None 

        logger.info("CommandExecutor initialized.")

    async def _start_offboard_setpoint_stream(self, north_m: float, east_m: float, down_m: float, yaw_deg: float):
        """
        Starts a continuous stream of NED position setpoints for offboard control.
        It will continuously send the specified setpoint.
        """
        self._current_offboard_setpoint = PositionNedYaw(north_m, east_m, down_m, yaw_deg)

        if self._offboard_setpoint_task and not self._offboard_setpoint_task.done():
            logger.debug("Offboard setpoint stream already running. Cancelling existing task to start new one.")
            self._offboard_setpoint_task.cancel()
            try:
                await self._offboard_setpoint_task
            except asyncio.CancelledError:
                pass
            self._offboard_setpoint_task = None

        logger.info(f"Starting offboard position setpoint stream to N={north_m:.2f}, E={east_m:.2f}, D={down_m:.2f}, Yaw={yaw_deg:.2f}...")
        
        for i in range(10):
            await self.drone.offboard.set_position_ned(self._current_offboard_setpoint)
            await asyncio.sleep(0.1)

        async def send_setpoints_loop():
            """Continuously sends the specified position setpoints."""
            logger.info("Offboard setpoint task started, continuously sending setpoints.")
            try:
                while True:
                    await self.drone.offboard.set_position_ned(self._current_offboard_setpoint)
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                logger.info("Offboard setpoint stream cancelled.")
            except Exception as e:
                logger.error(f"Error in offboard setpoint stream: {e}")

        self._offboard_setpoint_task = asyncio.ensure_future(send_setpoints_loop())
        self._offboard_active = True
        logger.info("Offboard setpoint stream initiated and running.")


    async def _stop_offboard_setpoint_stream(self):
        """
        Stops the continuous offboard setpoint stream.
        """
        if self._offboard_setpoint_task:
            self._offboard_setpoint_task.cancel()
            try:
                await self._offboard_setpoint_task
            except asyncio.CancelledError:
                pass
            self._offboard_setpoint_task = None
            self._offboard_active = False
            logger.info("Offboard setpoint stream stopped.")

    async def _try_set_offboard_mode(self):
        """
        Tries to set the drone to Offboard mode.
        Ensures a setpoint stream is active before attempting to start Offboard.
        If no stream is active, it starts one to hold the current position.
        """
        if not self._offboard_active:
            logger.info("Offboard not active. Attempting to start initial setpoint stream to hold current position.")
            current_pos_ned_data = await self.mavsdk_interface._read_stream_value(self.drone.telemetry.position_velocity_ned)
            
            if current_pos_ned_data:
                await self._start_offboard_setpoint_stream(
                    current_pos_ned_data.position.north_m,
                    current_pos_ned_data.position.east_m,
                    current_pos_ned_data.position.down_m,
                    0.0
                )
                logger.info(f"Initial Offboard stream started at current NED: N={current_pos_ned_data.position.north_m:.2f}, E={current_pos_ned_data.position.east_m:.2f}, D={current_pos_ned_data.position.down_m:.2f}")
            else:
                logger.warning("Could not get current NED position for initial offboard stream. Starting at (0,0,-10) NED.")
                await self._start_offboard_setpoint_stream(0.0, 0.0, -10.0, 0.0)
            
            await asyncio.sleep(0.5)

        logger.info("Trying to set Offboard mode...")
        try:
            await self.drone.offboard.start()
            logger.info("Offboard mode enabled successfully.")
            return True
        except OffboardError as e:
            logger.error(f"Failed to start offboard mode: {e}. Is the drone armed and in the air with good GPS?")
            if self._offboard_active:
                await self._stop_offboard_setpoint_stream()
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred while setting offboard mode: {e}")
            if self._offboard_active:
                await self._stop_offboard_setpoint_stream()
            return False

    async def _try_set_hold_mode(self):
        """
        Tries to set the drone to Hold mode (or equivalent like Position mode)
        and stops offboard control.
        """
        logger.info("Trying to set Hold mode and stop Offboard...")
        try:
            await self.drone.offboard.stop()
            self._offboard_active = False
            logger.info("Offboard mode stopped.")
            return True
        except OffboardError as e:
            logger.error(f"Failed to stop offboard mode: {e}")
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred while stopping offboard mode: {e}")
            return False

    async def _follow_target_loop(self):
        """
        Continuously calculates and sends setpoints to follow the target.
        This runs as a separate asyncio task when 'follow_target' is active.
        """
        logger.info(f"Starting continuous follow loop for target ID: {self._target_info.get('id')}")
        try:
            while True:
                # Get the latest state from DroneState
                current_drone_state = self.drone_state.get_current_state()
                detected_objects = current_drone_state.get("visual_insights", {}).get("detected_objects", [])
                
                # Find the target we're supposed to follow (by ID or just the first one)
                target_data = None
                if self._target_info and self._target_info.get("id"):
                    for obj in detected_objects:
                        if obj.get("id") == self._target_info["id"]:
                            target_data = obj
                            break
                if not target_data and detected_objects: # Fallback to first detected if ID not found or not specified
                    target_data = detected_objects[0]
                    logger.debug(f"Target ID '{self._target_info.get('id')}' not found, following first detected object (ID: {target_data.get('id')}).")

                if not target_data or "absolute_position_ned" not in target_data:
                    logger.warning("Follow target not detected or position unavailable. Holding last known position.")
                    # If target lost, try to maintain current drone position using the last setpoint
                    # (which _start_offboard_setpoint_stream would have set to the target's last known position)
                    # Or, we could transition to a 'loiter' or 'do_nothing' state.
                    # For now, just keep sending the last commanded setpoint.
                    await asyncio.sleep(0.5) # Wait before next check
                    continue

                target_pos_ned = target_data["absolute_position_ned"]
                target_north = target_pos_ned["north_m"]
                target_east = target_pos_ned["east_m"]
                target_down = target_pos_ned["down_m"] # Target's absolute down position

                # Get current drone position (NED)
                drone_pos_ned_data = current_drone_state.get("telemetry", {}).get("position_ned", {})
                if not drone_pos_ned_data:
                    logger.warning("Could not get drone's current NED position for follow. Skipping setpoint.")
                    await asyncio.sleep(0.1)
                    continue
                
                drone_north = drone_pos_ned_data.get("north_m", 0.0)
                drone_east = drone_pos_ned_data.get("east_m", 0.0)
                drone_down = drone_pos_ned_data.get("down_m", 0.0)

                # Calculate desired drone position relative to the target
                # We want the drone to be at DEFAULT_FOLLOW_DISTANCE_M from the target horizontally
                # and at DEFAULT_FOLLOW_ALTITUDE_M relative to home (or current ground).
                
                # For a simple "behind" follow (assuming target moves mostly North/East):
                # Desired drone position will be (target_N - offset_N, target_E - offset_E)
                # Let's aim to be directly above the target horizontally, and at DEFAULT_FOLLOW_ALTITUDE_M
                
                # Desired drone position (absolute NED)
                desired_drone_north = target_north
                desired_drone_east = target_east
                desired_drone_down = -DEFAULT_FOLLOW_ALTITUDE_M # Negative for altitude up from home

                # Calculate horizontal distance to desired point
                dx = desired_drone_north - drone_north
                dy = desired_drone_east - drone_east
                horizontal_distance_to_target_point = math.sqrt(dx**2 + dy**2)

                # If the drone is far from the desired horizontal point, move towards it.
                # Otherwise, just ensure it's at the correct altitude.
                if horizontal_distance_to_target_point > DEFAULT_FOLLOW_DISTANCE_M: # Use follow_distance as a threshold for movement
                    logger.debug(f"Following: Moving towards target point. H-dist: {horizontal_distance_to_target_point:.2f}m")
                    await self._start_offboard_setpoint_stream(
                        desired_drone_north,
                        desired_drone_east,
                        desired_drone_down,
                        0.0 # Keep yaw fixed for simplicity, or point towards target
                    )
                else:
                    logger.debug(f"Following: Within horizontal follow distance ({DEFAULT_FOLLOW_DISTANCE_M:.2f}m). Adjusting altitude if needed.")
                    # If already close horizontally, ensure vertical position is correct
                    # We can directly update the setpoint without restarting the stream
                    self._current_offboard_setpoint.north_m = desired_drone_north
                    self._current_offboard_setpoint.east_m = desired_drone_east
                    self._current_offboard_setpoint.down_m = desired_drone_down
                    # The _offboard_setpoint_task is continuously sending self._current_offboard_setpoint

                await asyncio.sleep(0.5) # Update follow position every 0.5 seconds
        except asyncio.CancelledError:
            logger.info("Follow target loop cancelled.")
        except Exception as e:
            logger.error(f"Error in follow target loop: {e}")
        finally:
            self._target_info = None # Clear target info when loop ends
            self._follow_task = None # Clear task reference

    async def execute_command(self, command: dict) -> bool:
        """
        Executes a given drone command.
        :param command: A dictionary representing the command (e.g., {"action": "takeoff", "parameters": {"altitude_m": 10.0}}).
        :return: True if command was executed successfully, False otherwise.
        """
        action = command.get("action")
        params = command.get("parameters", {})
        reason = command.get("reason", "No specific reason provided.")

        logger.info(f"Executing command: {action} (Reason: {reason})")

        try:
            # --- Stop any active follow task if a new command comes in ---
            if self._follow_task and not self._follow_task.done() and action != "follow_target":
                logger.info(f"Stopping active follow task due to new command: {action}")
                self._follow_task.cancel()
                try:
                    await self._follow_task
                except asyncio.CancelledError:
                    pass
                self._target_info = None
                self._follow_task = None
            
            # --- Stop offboard setpoint stream if a non-offboard action is commanded ---
            # This ensures we exit offboard mode cleanly if we're doing a non-offboard action
            if self._offboard_active and action not in ["goto_location", "follow_target", "do_nothing"]:
                logger.info(f"Stopping offboard setpoint stream for action: {action}")
                await self._stop_offboard_setpoint_stream()
                await asyncio.sleep(0.5) # Give it a moment to transition

            if action == "takeoff":
                if not self.mavsdk_interface.is_connected:
                    logger.warning("Drone not connected, cannot takeoff.")
                    return False
                success = await self.mavsdk_interface.arm()
                if success:
                    success = await self.mavsdk_interface.takeoff(params.get("altitude_m", 2.5))
                return success

            elif action == "land":
                if not self.mavsdk_interface.is_connected:
                    logger.warning("Drone not connected, cannot land.")
                    return False
                success = await self.mavsdk_interface.land()
                if success:
                    await self.mavsdk_interface.disarm()
                return success

            elif action == "disarm":
                if not self.mavsdk_interface.is_connected:
                    logger.warning("Drone not connected, cannot disarm.")
                    return False
                return await self.mavsdk_interface.disarm()

            elif action == "goto_location":
                if not self.mavsdk_interface.is_connected:
                    logger.warning("Drone not connected, cannot goto_location.")
                    return False
                
                north_m = params.get("north_m")
                east_m = params.get("east_m")
                altitude_m = params.get("altitude_m") # This is relative altitude (positive up)
                
                if north_m is None or east_m is None or altitude_m is None:
                    logger.error("goto_location requires north_m, east_m, and altitude_m parameters.")
                    return False

                if not self._offboard_active:
                    success_offboard = await self._try_set_offboard_mode()
                    if not success_offboard:
                        logger.error("Failed to enter offboard mode for goto_location. Cannot proceed.")
                        return False
                    await asyncio.sleep(0.5)

                logger.info(f"Commanding relative NED position: N={north_m}m, E={east_m}m, Alt={altitude_m}m (Down={-altitude_m}m)")
                await self._start_offboard_setpoint_stream(
                    north_m, east_m, -altitude_m, 0.0
                )
                logger.info(f"Offboard setpoint stream updated for goto_location.")
                return True

            elif action == "follow_target":
                if not self.mavsdk_interface.is_connected:
                    logger.warning("Drone not connected, cannot follow_target.")
                    return False
                
                # LLM no longer provides these parameters directly.
                # We get the target's current position from DroneState.
                # Follow distance and altitude are defaults.
                
                current_state = self.drone_state.get_current_state()
                detected_objects = current_state.get("visual_insights", {}).get("detected_objects", [])

                if not detected_objects:
                    logger.error("No target detected for 'follow_target' command. Cannot initiate follow.")
                    return False
                
                # Assuming the first detected object is the primary target
                # If LLM provides target_id, we could search for it.
                primary_target = detected_objects[0]
                target_pos_ned = primary_target.get("absolute_position_ned")

                if not target_pos_ned:
                    logger.error("Detected target has no absolute NED position. Cannot initiate follow.")
                    return False

                self._target_info = {
                    "id": primary_target.get("id", "unknown_target"),
                    "north_m": target_pos_ned.get("north_m"),
                    "east_m": target_pos_ned.get("east_m"),
                    "down_m": target_pos_ned.get("down_m")
                }
                # Use predefined default follow distance and altitude
                # These could be passed as parameters to execute_command if LLM *did* provide them,
                # or read from a settings file. For now, hardcoded defaults.
                # self._follow_distance_m = DEFAULT_FOLLOW_DISTANCE_M # No longer needed as instance var for loop
                # self._follow_altitude_m = DEFAULT_FOLLOW_ALTITUDE_M # No longer needed as instance var for loop

                logger.info(f"Initiating follow for target '{self._target_info['id']}' at N:{self._target_info['north_m']:.2f}, E:{self._target_info['east_m']:.2f}, D:{self._target_info['down_m']:.2f}. Desired follow distance: {DEFAULT_FOLLOW_DISTANCE_M:.2f}m, altitude: {DEFAULT_FOLLOW_ALTITUDE_M:.2f}m.")
                
                if not self._offboard_active:
                    success_offboard = await self._try_set_offboard_mode()
                    if not success_offboard:
                        logger.error("Failed to enter offboard mode for follow_target. Cannot proceed.")
                        return False
                    await asyncio.sleep(0.5) 

                if not self._follow_task or self._follow_task.done():
                    self._follow_task = asyncio.ensure_future(self._follow_target_loop())
                else:
                    logger.warning("Follow task already running. Updating target info.")
                
                return True

            elif action == "do_nothing":
                logger.info("Drone commanded to do nothing.")
                if self._offboard_active and (not self._offboard_setpoint_task or self._offboard_setpoint_task.done()):
                    current_pos_ned_data = await self.mavsdk_interface._read_stream_value(self.drone.telemetry.position_velocity_ned)
                    if current_pos_ned_data:
                        await self._start_offboard_setpoint_stream(
                            current_pos_ned_data.position.north_m,
                            current_pos_ned_data.position.east_m,
                            current_pos_ned_data.position.down_m,
                            0.0
                        )
                    else:
                        logger.warning("Could not get current NED position for 'do_nothing' offboard stream. Drone might drift.")
                        if self._offboard_active:
                            await self._try_set_hold_mode()
                elif not self._offboard_active:
                    pass
                return True

            else:
                logger.warning(f"Unknown command action: {action}")
                return False

        except ActionError as e:
            logger.error(f"MAVSDK ActionError for {action}: {e}")
            return False
        except OffboardError as e:
            logger.error(f"MAVSDK OffboardError for {action}: {e}")
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred during command execution for {action}: {e}")
            return False

