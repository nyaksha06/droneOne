import asyncio
import logging
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
        logger.info("CommandExecutor initialized.")

    async def _start_offboard_setpoint_stream(self, north_m: float = 0.0, east_m: float = 0.0, down_m: float = 0.0, yaw_deg: float = 0.0):
        """
        Starts a continuous stream of NED position setpoints for offboard control.
        This is required before entering offboard mode.
        It will continuously send the specified setpoint.
        :param north_m: North component of position setpoint in meters.
        :param east_m: East component of position setpoint in meters.
        :param down_m: Down component of position setpoint in meters (negative for altitude).
        :param yaw_deg: Yaw angle in degrees.
        """
        if self._offboard_setpoint_task and not self._offboard_setpoint_task.done():
            logger.warning("Offboard setpoint stream already running. Stopping existing stream.")
            await self._stop_offboard_setpoint_stream() # Stop existing before starting new

        logger.info(f"Starting offboard position setpoint stream to N={north_m}, E={east_m}, D={down_m}, Yaw={yaw_deg}...")
        
        # Send a few setpoints before starting offboard mode
        # This is a MAVSDK requirement to ensure a smooth transition.
        for i in range(10):
            await self.drone.offboard.set_position_ned(
                PositionNedYaw(north_m, east_m, down_m, yaw_deg))
            await asyncio.sleep(0.1)

        async def send_setpoints_loop():
            """Continuously sends the specified position setpoints."""
            logger.info("Offboard setpoint task started, continuously sending setpoints.")
            try:
                while True:
                    await self.drone.offboard.set_position_ned(
                        PositionNedYaw(north_m, east_m, down_m, yaw_deg))
                    await asyncio.sleep(0.1) # Send setpoints at 10Hz
            except asyncio.CancelledError:
                logger.info("Offboard setpoint stream cancelled.")
            except Exception as e:
                logger.error(f"Error in offboard setpoint stream: {e}")

        self._offboard_setpoint_task = asyncio.ensure_future(send_setpoints_loop())
        self._offboard_active = True
        logger.info("Offboard setpoint stream initiated.")


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

    async def _try_set_offboard_mode(self, target_altitude_m: float = 10.0):
        """
        Tries to set the drone to Offboard mode.
        Assumes setpoints are already streaming.
        """
        if not self._offboard_active:
            # Start a default stream to hold current position/altitude if not already active
            current_pos_ned = await self.mavsdk_interface._read_stream_value(self.drone.telemetry.position_velocity_ned)
            if current_pos_ned:
                await self._start_offboard_setpoint_stream(
                    current_pos_ned.position.north_m,
                    current_pos_ned.position.east_m,
                    current_pos_ned.position.down_m,
                    0.0 # Keep current yaw for now
                )
            else:
                await self._start_offboard_setpoint_stream(0.0, 0.0, -target_altitude_m, 0.0) # Fallback to default alt
            await asyncio.sleep(0.5) # Give it a moment to start

        logger.info("Trying to set Offboard mode...")
        try:
            await self.drone.offboard.start()
            logger.info("Offboard mode enabled.")
            return True
        except OffboardError as e:
            logger.error(f"Failed to start offboard mode: {e}. Is the drone armed and in the air?")
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred while setting offboard mode: {e}")
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
                # Ensure offboard is stopped before landing with action.land()
                if self._offboard_active:
                    await self._stop_offboard_setpoint_stream()
                    await asyncio.sleep(0.5) # Give it a moment to stabilize
                success = await self.mavsdk_interface.land()
                # After landing, disarm
                if success:
                    await self.mavsdk_interface.disarm()
                return success

            elif action == "disarm":
                if not self.mavsdk_interface.is_connected:
                    logger.warning("Drone not connected, cannot disarm.")
                    return False
                # Ensure offboard is stopped before disarming
                if self._offboard_active:
                    await self._stop_offboard_setpoint_stream()
                return await self.mavsdk_interface.disarm()

            elif action == "goto_location":
                if not self.mavsdk_interface.is_connected:
                    logger.warning("Drone not connected, cannot goto_location.")
                    return False
                
                # For goto_location, we will use the high-level MAVSDK action.goto_location
                # This action handles its own mode switching and path planning.
                # It typically uses global coordinates.
                # If LLM provides relative NED, we need to convert it.
                
                # For simplicity in this phase, let's assume LLM provides global lat/lon
                # OR we calculate global target from current position + NED offset.
                # For now, let's assume LLM provides north_m, east_m, altitude_m relative to current.
                # We need current global position to calculate target global position.

                current_pos = await self.mavsdk_interface._read_stream_value(self.drone.telemetry.position)
                if not current_pos:
                    logger.error("Could not get current global position for goto_location.")
                    return False

                north_m = params.get("north_m")
                east_m = params.get("east_m")
                altitude_m = params.get("altitude_m") # This is relative altitude

                if north_m is None or east_m is None or altitude_m is None:
                    logger.error("goto_location requires north_m, east_m, and altitude_m parameters.")
                    return False

                # Convert relative NED to a new global Lat/Lon
                # This is a simplification. A proper conversion might use geographiclib.
                # For small distances, a simple approximation is often used:
                # 1 degree lat ~ 111,139 meters
                # 1 degree lon ~ 111,139 * cos(latitude) meters
                
                # Approximate conversion (for short distances in SITL)
                # More robust solution would involve a proper NED to Lat/Lon conversion
                # using a library like geographiclib or mavsdk-python's internal helpers if available.
                
                # For now, let's use the MAVSDK action.goto_location with current position as reference
                # and assume the LLM is smart enough to give us *relative* offsets that it expects
                # to be applied from the current drone position.
                # MAVSDK's action.goto_location takes absolute lat/lon, so we need to calculate it.
                
                # This is a placeholder. Real implementation needs a robust NED to Lat/Lon conversion.
                # For SITL, often it's easier to use Offboard.set_position_ned for relative moves.
                # If the LLM is providing relative N/E/Alt, then the CommandExecutor should use Offboard.
                # Let's revert to Offboard for `goto_location` for relative moves, as it's more direct.

                # REVERTING TO OFFBOARD FOR GOTO_LOCATION FOR RELATIVE MOVES
                # This is more consistent with LLM providing relative N/E/Alt.
                if not self._offboard_active:
                    success_offboard = await self._try_set_offboard_mode(target_altitude_m=altitude_m) # Start stream at target alt
                    if not success_offboard:
                        logger.error("Failed to enter offboard mode for goto_location.")
                        return False
                    await asyncio.sleep(0.5) # Give it a moment to stabilize in offboard

                logger.info(f"Going to relative NED: N={north_m}m, E={east_m}m, Alt={altitude_m}m")
                # MAVSDK's offboard.set_position_ned expects 'down' to be negative for altitude
                await self.drone.offboard.set_position_ned(
                    PositionNedYaw(north_m, east_m, -altitude_m, 0.0) # Yaw 0.0 for now
                )
                # For a simple goto, we send it once. For continuous tracking, this would be in a loop.
                return True

            elif action == "follow_target": # NEW ACTION
                if not self.mavsdk_interface.is_connected:
                    logger.warning("Drone not connected, cannot follow_target.")
                    return False
                
                target_id = params.get("target_id")
                follow_distance_m = params.get("follow_distance_m")
                altitude_m = params.get("altitude_m")

                if target_id is None or follow_distance_m is None or altitude_m is None:
                    logger.error("follow_target requires target_id, follow_distance_m, and altitude_m parameters.")
                    return False

                logger.info(f"Initiating mock follow for target '{target_id}' at {follow_distance_m}m distance, altitude {altitude_m}m.")
                # --- MOCK IMPLEMENTATION FOR PHASE 1 ---
                # In Phase 2, this would involve:
                # 1. Getting the *current* estimated position of the target from CameraProcessor/State.
                # 2. Calculating a desired drone position relative to the target (e.g., 10m behind, at 15m alt).
                # 3. Setting Offboard mode if not already active.
                # 4. Continuously sending position/velocity setpoints to track the target.
                
                # Ensure offboard mode is active if we want to realistically "follow"
                if not self._offboard_active:
                    success_offboard = await self._try_set_offboard_mode(target_altitude_m=altitude_m)
                    if not success_offboard:
                        logger.error("Failed to enter offboard mode for follow_target.")
                        return False
                    await asyncio.sleep(0.5) 

                # For a mock follow, we can just command it to hold its current position
                # or a predefined position to simulate "being ready to follow".
                # The _start_offboard_setpoint_stream will maintain the last commanded position.
                logger.info("Mock follow_target: Drone will attempt to hold current position/altitude.")
                
                return True


            elif action == "do_nothing":
                logger.info("Drone commanded to do nothing.")
                # If currently in offboard, ensure setpoints are still streaming to hold position
                if self._offboard_active and (not self._offboard_setpoint_task or self._offboard_setpoint_task.done()):
                     # This might be redundant if _try_set_offboard_mode is always called first.
                     # But it ensures the stream is active if LLM says "do_nothing" while already in offboard.
                     # For a true "do_nothing" in offboard, you'd send current position setpoints.
                     # For simplicity, we assume if offboard is active, the stream is running.
                     pass # The continuous stream started by _try_set_offboard_mode already handles holding position.
                # If not in offboard, it will just maintain its current flight mode (e.g., HOLD in SITL)
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

