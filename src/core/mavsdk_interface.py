import asyncio
from mavsdk import System
from mavsdk.offboard import PositionNedYaw, OffboardError, VelocityBodyYawspeed,VelocityNedYaw
from mavsdk.action import ActionError
from mavsdk.telemetry import FlightMode 
import logging
import sys


logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


mavsdk_logger = logging.getLogger("mavsdk")
mavsdk_logger.setLevel(logging.INFO)

class MAVSDKInterface:
    """
    Manages all interactions with the drone via MAVSDK.
    Provides methods for connection, arming, taking off, landing,
    and subscribing to telemetry streams, and offboard control.
    """

    def __init__(self, system_address: str = "udp://:14540"):
        """
        Initializes the MAVSDKInterface.
        :param system_address: MAVLink connection string (e.g., "udp://:14540").
        """
        self.drone = System()
        self._system_address = system_address
        self.is_connected = False
        logger.info(f"MAVSDKInterface initialized for system address: {self._system_address}")

    async def _read_stream_value(self, stream_func, timeout=1.0):
        try:
            # Get the async iterator from the stream function (e.g., self.drone.telemetry.in_air())
            # and await its next value.
            value = await asyncio.wait_for(stream_func().__anext__(), timeout=timeout)
            return value
        except asyncio.TimeoutError:
            logger.debug(f"Timeout waiting for stream update from {stream_func.__name__}")
            return None
        except StopAsyncIteration:
            logger.warning(f"Stream {stream_func.__name__} stopped unexpectedly.")
            return None
        except Exception as e:
            logger.error(f"Error reading from stream {stream_func.__name__}: {e}", exc_info=True)
            return None

    async def connect(self):
        """
        Connects to the drone and waits for the drone to be ready.
        """
        logger.info(f"Attempting to connect to the drone at {self._system_address}...")
        try:
            await self.drone.connect(system_address=self._system_address)
            logger.info("MAVSDK connection initiated. Waiting for state...")

            async for health in self.drone.telemetry.health():
                if health.is_global_position_ok and health.is_home_position_ok:
                    logger.info("Drone global and home position are OK. Connected and Ready!")
                    self.is_connected = True
                    return True
                else:
                    logger.info(f"Waiting for drone health: Global Pos OK={health.is_global_position_ok}, Home Pos OK={health.is_home_position_ok}. Full health: {health}")
                    await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Error during drone connection: {e}")
            self.is_connected = False
            return False
        return False

    async def arm(self):
        """
        Arms the drone. Requires drone to be disarmed, in GUIDED mode, and healthy.
        """
        if not self.is_connected:
            logger.warning("Drone not connected. Cannot arm.")
            return False
        
        async for is_armed in self.drone.telemetry.armed():
            if is_armed:
                logger.info("Drone is already armed.")
                return True
            break

        logger.info("Arming drone...")
        try:
            await self.drone.action.arm()
            logger.info("Drone armed successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to arm drone: {e}")
            return False

    async def disarm(self):
        """
        Disarms the drone.
        """
        if not self.is_connected:
            logger.warning("Drone not connected. Cannot disarm.")
            return False

        async for is_armed in self.drone.telemetry.armed():
            if not is_armed:
                logger.info("Drone is already disarmed.")
                return True
            break

        logger.info("Disarming drone...")
        try:
            await self.drone.action.disarm()
            logger.info("Drone disarmed successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to disarm drone: {e}")
            return False

    async def takeoff(self, altitude_m: float = 2.5):
        if not self.is_connected:
            logger.warning("Drone not connected. Cannot takeoff.")
            return False
        
        logger.info(f"Taking off to {altitude_m} meters...")
        try:
            await self.drone.action.set_takeoff_altitude(altitude_m)
            await self.drone.action.takeoff()
                
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"Failed to takeoff: {e}", exc_info=True)
            return False

    async def land(self) -> bool:
        
        print("--- Commanding drone to LAND ---")
        try:
            await self.drone.action.land()
            print("-- Landing command sent.")

            print("Waiting for drone to land and disarm...")
            async for is_armed in self.drone.telemetry.armed():
                if is_armed:
                    pass
                else:
                    print("Drone is DISARMED")
                    break
                await asyncio.sleep(1) 
            return True 

        except Exception as e:
            print(f"Error during landing: {e}")
            return False
        

    async def send_position_ned_setpoint(self, north_m: float, east_m: float, down_m: float, yaw_deg: float = 0.0):
        """
        Sends a position setpoint in NED frame for offboard control.
        This must be called continuously at a high rate (e.g., 20-50Hz) when in Offboard mode.
        """
        try:
            await self.drone.offboard.set_position_ned(
                PositionNedYaw(north_m, east_m, down_m, yaw_deg)
            )
            # logger.debug(f"Sent NED setpoint: N={north_m}, E={east_m}, D={down_m}, Yaw={yaw_deg}")
        except OffboardError as e:
            logger.error(f"Failed to send OFFBOARD position setpoint: {e}")

    async def set_offboard_mode(self) -> bool:
        """
        Sets the drone's flight mode to OFFBOARD.
        Requires continuous setpoint streaming to maintain the mode.
        """
        if not self.is_connected:
            logger.warning("Drone not connected. Cannot set OFFBOARD mode.")
            return False
        
        logger.info("Setting flight mode to OFFBOARD...")
        try:
            await self.drone.offboard.set_position_ned(
                PositionNedYaw(0.0, 0.0, 0.0, 0.0) # Send a dummy setpoint first, as required by PX4 for OFFBOARD
            )
            await self.drone.offboard.start() # Start offboard mode
            logger.info("OFFBOARD mode activated.")
            return True
        except OffboardError as e:
            logger.error(f"Failed to set OFFBOARD mode: {e}")
            return False

    async def set_hold_mode(self) -> bool:
        """
        Sets the drone's flight mode to HOLD.
        """
        if not self.is_connected:
            logger.warning("Drone not connected. Cannot set HOLD mode.")
            return False

        logger.info("Setting flight mode to HOLD...")
        try:
            await self.drone.action.hold()
            logger.info("HOLD mode activated.")
            return True
        except ActionError as e:
            logger.error(f"Failed to set HOLD mode: {e}")
            return False    

    async def goto(self, north_m, east_m, down_m):
        print("-- Starting Offboard mode")

        await self.drone.offboard.set_position_ned(
        PositionNedYaw(
            north_m=north_m,
            east_m=east_m,
            down_m=down_m,
            yaw_deg=0.0
        )
        )

        try:
            await self.drone.offboard.start()
            print(f"-- Moving to (North: {north_m}m, East: {east_m}m, Down: {down_m}m)")
        except OffboardError as error:
            print(f"Offboard start failed: {error._result.result}")
            await self.drone.action.disarm()
            return

        await asyncio.sleep(20)  

        print("-- Stopping Offboard")
        await self.drone.offboard.stop()

        print("-- Landing")
        await self.drone.action.land()
        

    async def subscribe_position_velocity_ned(self, callback):
        """
        Subscribes to position and velocity NED data.
        :param callback: An async function to call with the PositionVelocityNed data.
        """
        logger.info("Subscribing to Position and Velocity NED...")
        async for pos_vel_ned in self.drone.telemetry.position_velocity_ned():
            await callback(pos_vel_ned)

    async def subscribe_position(self, callback):
        """
        Subscribes to global position (latitude, longitude, altitude) data.
        :param callback: An async function to call with the Position data.
        """
        logger.info("Subscribing to Global Position...")
        async for position in self.drone.telemetry.position():
            await callback(position)

    async def subscribe_attitude_euler(self, callback):
        """
        Subscribes to attitude (Euler angles) data.
        :param callback: An async function to call with the AttitudeEuler data.
        """
        logger.info("Subscribing to Attitude Euler...")
        async for att_euler in self.drone.telemetry.attitude_euler():
            await callback(att_euler)

    async def subscribe_battery(self, callback):
        """
        Subscribes to battery status.
        :param callback: An async function to call with the Battery data.
        """
        logger.info("Subscribing to Battery status...")
        async for battery_status in self.drone.telemetry.battery():
            await callback(battery_status)

    async def subscribe_flight_mode(self, callback):
        """
        Subscribes to the drone's current flight mode.
        :param callback: An async function to call with the FlightMode data.
        """
        logger.info("Subscribing to Flight Mode...")
        async for flight_mode_status in self.drone.telemetry.flight_mode():
            await callback(flight_mode_status)


    async def disconnect(self):
        """
        Performs any necessary cleanup before exiting.
        """
        logger.info("Disconnecting MAVSDK...")
        self.is_connected = False
        logger.info("MAVSDK interface shut down.")

    async def offboard_takeoff(self, target_altitude_m: float = 10.0) -> bool:
        print(f"--- Starting offboard take-off to {target_altitude_m} meters ---")

        # 1. Check for global position estimate (crucial for position control)
        print("Waiting for drone to have a global position estimate...")
        async for health in self.drone.telemetry.health():
            if health.is_global_position_ok and health.is_home_position_ok:
                print("-- Global position estimate OK")
                break

        # 2. Arm the drone
        print("-- Arming drone")
        try:
            await self.drone.action.arm()
            print("-- Drone armed successfully!")
        except Exception as e:
            print(f"Error arming drone: {e}")
            return False 

        # 3. Set initial setpoint before starting offboard mode
        print("-- Setting initial offboard setpoint (hover)")
        for _ in range(10):
            await self.drone.offboard.set_velocity_body(VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0))
            await asyncio.sleep(0.005) 
        
        # 4. Start offboard mode
        print("-- Starting offboard mode")
        try:
            await self.drone.offboard.start()
            print("-- Offboard mode started!")
        except OffboardError as error:
            print(f"Error starting offboard mode: {error._result.result}")
            print("-- Disarming drone due to offboard start failure.")
            await self.drone.action.disarm()
            return False 

        # 5. Command take-off to target altitude
        target_down_m = -abs(target_altitude_m) 

        print(f"-- Commanding take-off to altitude: {target_altitude_m}m (NED Down: {target_down_m}m)")
        
        initial_position = None
        async for pos in self.drone.telemetry.position():
            initial_position = pos
            break 

        if initial_position is None:
            print("Error: Could not get initial position for take-off monitoring.")
            await self.drone.offboard.stop()
            await self.drone.action.disarm()
            return False

        altitude_achieved = False
        altitude_tolerance = 0.1
        print("Monitoring altitude for take-off...")
        
        timeout_seconds = 60 
        start_time = asyncio.get_event_loop().time()

        while not altitude_achieved and (asyncio.get_event_loop().time() - start_time) < timeout_seconds:
            await self.drone.offboard.set_position_ned(PositionNedYaw(0.0, 0.0, target_down_m, 0.0))
            
            current_position = await self.drone.telemetry.position().__anext__() 
            current_down_m = current_position.relative_altitude_m
            
            print(f"Current altitude (NED Down): {current_down_m:.2f}m")

            if abs(current_down_m + target_down_m) < altitude_tolerance:
                print(f"-- Reached target altitude of {target_altitude_m}m!")
                altitude_achieved = True
                break

            await asyncio.sleep(0.1) 

        if altitude_achieved:
            print("--- Take-off successful!  ---")
            self.hold_position_indefinitely()
            return True 
        else:
            print(f"--- Take-off failed: Did not reach target altitude within {timeout_seconds}s. ---")
            self.hold_position_indefinitely()
            try:
                
                print("-- Offboard stopped after failed take-off.")
            except OffboardError:
                pass 
            return False     

    async def offboard_goto(self, north_m: float, east_m: float, down_m: float, yaw_deg: float = 0.0) -> bool:
        print(f"--- Commanding drone to GOTO N:{north_m:.2f}m, E:{east_m:.2f}m, D:{down_m:.2f}m with Yaw:{yaw_deg:.2f}deg ---")
        
        await self.drone.offboard.set_position_ned(
        PositionNedYaw(
            north_m=north_m,
            east_m=east_m,
            down_m=down_m,
            yaw_deg=0.0
        )
        )

        try:
            await self.drone.offboard.start()
            print(f"-- Moving to (North: {north_m}m, East: {east_m}m, Down: {down_m}m)")
        except OffboardError as error:
            print(f"Offboard start failed: {error._result.result}")
            await self.drone.action.disarm()
            return
        

        target_position = PositionNedYaw(north_m, east_m, down_m, yaw_deg)
        target_velocity = VelocityNedYaw(0.0, 0.0, 0.0, 0.0) 

        position_reached = False
        position_tolerance_xy = 0.1
        position_tolerance_z = 0.1  
        
        goto_timeout_seconds = 120 
        start_time = asyncio.get_event_loop().time()

        print("Monitoring position until target is reached...")
        async for current_telemetry_pv_info in self.drone.telemetry.position_velocity_ned():
            if (asyncio.get_event_loop().time() - start_time) > goto_timeout_seconds:
                print(f"--- GOTO failed: Did not reach target position within {goto_timeout_seconds}s. ---")
                return False 
            
           

            
            current_north_m = current_telemetry_pv_info.position.north_m
            current_east_m = current_telemetry_pv_info.position.east_m
            current_down_m = current_telemetry_pv_info.position.down_m 

            distance_xy = ((current_north_m - north_m)**2 + (current_east_m - east_m)**2)**0.5
            distance_z = abs(current_down_m - down_m) 

            print(f"Current Pos (N,E,D): ({current_north_m:.2f}, {current_east_m:.2f}, {current_down_m:.2f})m "
                  f"Dist to target: XY={distance_xy:.2f}m, Z={distance_z:.2f}m")

            if distance_xy < position_tolerance_xy and distance_z < position_tolerance_z:
                print(f"-- Reached target position (N:{north_m}, E:{east_m}, D:{down_m})!")
                position_reached = True
                break

            await asyncio.sleep(0.1) 

        if position_reached:
            print("--- GOTO successful! Drone is at target position. ---")
            self.hold_position_indefinitely()
            return True
        else:
            return False
        


    async def hold_position_indefinitely(self) -> bool:
        print("--- Commanding drone to HOLD current position indefinitely ---")
        try:
            await self.drone.action.hold()
            print("-- Drone commanded to HOLD. It will stay here until a new action/offboard command.")
            return True
        except Exception as e:
            print(f"Error putting drone in HOLD mode: {e}")
            return False    