import asyncio
import logging
import math # NEW: For distance calculations
from mavsdk import System
from mavsdk.offboard import OffboardError, PositionNedYaw, VelocityNedYaw
from mavsdk.action import ActionError

# Assuming MAVSDKInterface is in src.core
from src.core.mavsdk_interface import MAVSDKInterface 

logger = logging.getLogger(__name__)

class CommandExecutor:
    """
    Executes drone commands by translating high-level actions into MAVSDK calls.
    Handles offboard control setup and continuous setpoint streaming (for actions like follow_target).
    """

    def __init__(self, mavsdk_interface: MAVSDKInterface):
        """
        Initializes the CommandExecutor.
        :param mavsdk_interface: An instance of MAVSDKInterface for drone communication.
        """
        self.mavsdk_interface = mavsdk_interface
        self.drone = mavsdk_interface.drone # Direct access to the MAVSDK System object
        self._offboard_setpoint_task = None # Task for continuous offboard setpoints
        self._offboard_active = False # Flag to track if offboard mode is active
        self._current_offboard_setpoint = PositionNedYaw(0.0, 0.0, 0.0, 0.0) # Store the last commanded setpoint
        
        # NEW: For follow_target logic
        self._target_info = None # Stores {"id": ..., "north_m": ..., "east_m": ..., "down_m": ...}
        self._follow_distance_m = 0.0
        self._follow_altitude_m = 0.0
        self._follow_task = None # Task for the continuous follow loop

        logger.info("CommandExecutor initialized.")

    async def _start_offboard_setpoint_stream(self, north_m: float, east_m: float, down_m: float, yaw_deg: float):
        """
        Starts a continuous stream of NED position setpoints for offboard control.
        This is required before entering offboard mode.
        It will continuously send the specified setpoint.
        :param north_m: North component of position setpoint in meters.
        :param east_m: East component of position setpoint in meters.
        :param down_m: Down component of position setpoint in meters (negative for altitude).
        :param yaw_deg: Yaw angle in degrees.
        """
        # Store the new setpoint
        self._current_offboard_setpoint = PositionNedYaw(north_m, east_m, down_m, yaw_deg)

        if self._offboard_setpoint_task and not self._offboard_setpoint_task.done():
            logger.debug("Offboard setpoint stream already running. Cancelling existing task to start new one.")
            self._offboard_setpoint_task.cancel()
            try:
                await self._offboard_setpoint_task
            except asyncio.CancelledError:
                pass # Expected cancellation
            self._offboard_setpoint_task = None

        logger.info(f"Starting offboard position setpoint stream to N={north_m}, E={east_m}, D={down_m}, Yaw={yaw_deg}...")
        
        # Send a few setpoints before starting offboard mode (MAVSDK requirement)
        for i in range(10):
            await self.drone.offboard.set_position_ned(self._current_offboard_setpoint)
            await asyncio.sleep(0.1)

        async def send_setpoints_loop():
            """Continuously sends the specified position setpoints."""
            logger.info("Offboard setpoint task started, continuously sending setpoints.")
            try:
                while True:
                    await self.drone.offboard.set_position_ned(self._current_offboard_setpoint)
                    await asyncio.sleep(0.1) # Send setpoints at 10Hz
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
                pass # Expected cancellation
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
                # Start stream to hold current NED position
                await self._start_offboard_setpoint_stream(
                    current_pos_ned_data.position.north_m,
                    current_pos_ned_data.position.east_m,
                    current_pos_ned_data.position.down_m,
                    0.0 # Assuming current yaw for now, or get it from telemetry.attitude_euler
                )
                logger.info(f"Initial Offboard stream started at current NED: N={current_pos_ned_data.position.north_m:.2f}, E={current_pos_ned_data.position.east_m:.2f}, D={current_pos_ned_data.position.down_m:.2f}")
            else:
                logger.warning("Could not get current NED position for initial offboard stream. Starting at (0,0,-10) NED.")
                await self._start_offboard_setpoint_stream(0.0, 0.0, -10.0, 0.0) # Fallback to default alt if no position data
            
            await asyncio.sleep(0.5) # Give it a moment to start streaming setpoints

        logger.info("Trying to set Offboard mode...")
        try:
            await self.drone.offboard.start()
            logger.info("Offboard mode enabled successfully.")
            return True
        except OffboardError as e:
            logger.error(f"Failed to start offboard mode: {e}. Is the drone armed and in the air with good GPS?")
            # Attempt to stop the setpoint stream if offboard failed to start
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
            # Stop offboard first
            await self.drone.offboard.stop()
            self._offboard_active = False
            logger.info("Offboard mode stopped.")
            # Optionally set to a stable mode like HOLD or POSITION_CONTROL
            # await self.drone.action.set_flight_mode(FlightMode.HOLD) # Requires FlightMode import
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
                if not self._target_info:
                    logger.warning("Follow target info lost. Stopping follow loop.")
                    break # Exit loop if target info is gone

                # Get current drone position (NED)
                drone_pos_ned = await self.mavsdk_interface._read_stream_value(self.drone.telemetry.position_velocity_ned)
                if not drone_pos_ned:
                    logger.warning("Could not get drone's current position for follow. Skipping setpoint.")
                    await asyncio.sleep(0.1)
                    continue

                target_north = self._target_info["north_m"]
                target_east = self._target_info["east_m"]
                target_down = self._target_info["down_m"] # Target's absolute down position

                # Calculate desired drone position relative to the target
                # For simplicity, let's try to stay 'follow_distance_m' behind the target
                # along the East axis, and at 'follow_altitude_m' relative altitude.
                # This is a very basic follow. A more advanced one would consider target velocity,
                # drone's current heading, and desired relative angle.

                # Simple follow: drone tries to go to target's (N, E) but maintain follow_distance_m
                # from it, and maintain follow_altitude_m relative to ground.
                # Let's just try to go to the target's N/E, and maintain the specified follow_altitude_m
                # The 'follow_distance_m' can be interpreted as a safety buffer or minimum distance.

                # Desired drone position (absolute NED)
                # For a simple follow, let's just aim for the target's N/E coordinates
                # and maintain a fixed altitude relative to home (or current ground level).
                # The 'follow_distance_m' can be a buffer.
                
                # For a basic follow, let's aim for the target's (N, E) and the specified follow_altitude_m
                # The drone's 'down' coordinate is negative altitude.
                # We want the drone to be at follow_altitude_m *above* the ground,
                # so its 'down' value will be -follow_altitude_m relative to home.
                
                # Let's simplify: target_down is absolute from home. Drone wants to be at follow_altitude_m *above* ground.
                # Assuming target_down is also relative to home, and represents ground level for target.
                # Desired drone down position = target_down - follow_altitude_m (if follow_altitude_m is relative to target's ground)
                # Or, if follow_altitude_m is relative to drone's home, then simply -follow_altitude_m.
                # For now, let's assume follow_altitude_m is relative to drone's home.

                desired_drone_north = target_north
                desired_drone_east = target_east
                desired_drone_down = -self._follow_altitude_m # Negative for altitude up

                # Check if drone is close enough to target (horizontal distance)
                dx = desired_drone_north - drone_pos_ned.position.north_m
                dy = desired_drone_east - drone_pos_ned.position.east_m
                horizontal_distance = math.sqrt(dx**2 + dy**2)

                # Only command movement if outside desired follow distance (or buffer)
                if horizontal_distance > self._follow_distance_m:
                    # Update the continuous setpoint stream
                    await self._start_offboard_setpoint_stream(
                        desired_drone_north,
                        desired_drone_east,
                        desired_drone_down,
                        0.0 # Keep yaw fixed for simplicity, or point towards target
                    )
                    logger.debug(f"Following: Drone moving towards target. Current H-dist: {horizontal_distance:.2f}m")
                else:
                    logger.debug(f"Following: Drone within follow distance ({self._follow_distance_m:.2f}m). Holding position.")
                    # If already close, ensure it's holding its current position
                    # by updating the setpoint stream to its current position, 
                    # or simply let the existing stream continue sending the last commanded target.
                    # For simplicity, if it's within distance, we don't send new setpoints to avoid jitter.
                    # The existing _offboard_setpoint_task will keep sending the last commanded setpoint.
                    pass # The current_offboard_setpoint will remain the target's last known position

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
                    pass # Expected
                self._target_info = None # Clear target info
                self._follow_task = None # Clear task reference
            
            # --- Stop offboard setpoint stream if a non-offboard action is commanded ---
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

                # Ensure offboard mode is active and setpoints are streaming
                if not self._offboard_active:
                    success_offboard = await self._try_set_offboard_mode()
                    if not success_offboard:
                        logger.error("Failed to enter offboard mode for goto_location. Cannot proceed.")
                        return False
                    await asyncio.sleep(0.5) # Give it a moment to stabilize in offboard

                logger.info(f"Commanding relative NED position: N={north_m}m, E={east_m}m, Alt={altitude_m}m (Down={-altitude_m}m)")
                # Update the continuous setpoint stream with the new target.
                await self._start_offboard_setpoint_stream(
                    north_m, east_m, -altitude_m, 0.0 # Yaw 0.0 for now
                )
                logger.info(f"Offboard setpoint stream updated for goto_location.")
                return True

            elif action == "follow_target":
                if not self.mavsdk_interface.is_connected:
                    logger.warning("Drone not connected, cannot follow_target.")
                    return False
                
                target_north_m = params.get("target_north_m")
                target_east_m = params.get("target_east_m")
                target_down_m = params.get("target_down_m")
                follow_distance_m = params.get("follow_distance_m")
                follow_altitude_m = params.get("follow_altitude_m") # This is the desired altitude for the drone

                if any(p is None for p in [target_north_m, target_east_m, target_down_m, follow_distance_m, follow_altitude_m]):
                    logger.error("follow_target requires target_north_m, target_east_m, target_down_m, follow_distance_m, and follow_altitude_m parameters.")
                    return False

                self._target_info = {
                    "id": params.get("target_id", "unknown_target"),
                    "north_m": target_north_m,
                    "east_m": target_east_m,
                    "down_m": target_down_m
                }
                self._follow_distance_m = follow_distance_m
                self._follow_altitude_m = follow_altitude_m

                logger.info(f"Initiating follow for target '{self._target_info['id']}' at N:{target_north_m:.2f}, E:{target_east_m:.2f}, D:{target_down_m:.2f}. Desired follow distance: {follow_distance_m:.2f}m, altitude: {follow_altitude_m:.2f}m.")
                
                # Ensure offboard mode is active
                if not self._offboard_active:
                    success_offboard = await self._try_set_offboard_mode()
                    if not success_offboard:
                        logger.error("Failed to enter offboard mode for follow_target. Cannot proceed.")
                        return False
                    await asyncio.sleep(0.5) 

                # Start the continuous follow loop
                if not self._follow_task or self._follow_task.done():
                    self._follow_task = asyncio.ensure_future(self._follow_target_loop())
                else:
                    logger.warning("Follow task already running. Parameters updated.")
                
                return True

            elif action == "do_nothing":
                logger.info("Drone commanded to do nothing.")
                # If currently in offboard, ensure setpoints are still streaming to hold current position
                if self._offboard_active and (not self._offboard_setpoint_task or self._offboard_setpoint_task.done()):
                    current_pos_ned_data = await self.mavsdk_interface._read_stream_value(self.drone.telemetry.position_velocity_ned)
                    if current_pos_ned_data:
                        await self._start_offboard_setpoint_stream(
                            current_pos_ned_data.position.north_m,
                            current_pos_ned_data.position.east_m,
                            current_pos_ned_data.position.down_m,
                            0.0 # Keep current yaw for now
                        )
                    else:
                        logger.warning("Could not get current NED position for 'do_nothing' offboard stream. Drone might drift.")
                        if self._offboard_active:
                            await self._try_set_hold_mode() # Exit offboard if we can't hold position
                elif not self._offboard_active:
                    pass # If not in offboard, "do_nothing" means stay in current flight mode (e.g., HOLD in SITL)
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

