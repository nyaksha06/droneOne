import asyncio
from mavsdk import System
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
    and subscribing to telemetry streams.
    """

    def __init__(self, system_address: str = "udp://:14540"):
        # --- FIX for MAVSDK 1.3.0 API: System() constructor takes no arguments ---
        self.drone = System()
        self._system_address = system_address # Store the address to use with connect()
        self.is_connected = False
        logger.info(f"MAVSDKInterface initialized for system address: {self._system_address}")

    async def connect(self):
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

            logger.info("Takeoff command sent. Waiting for drone to be airborne (checking in_air status)...")
            in_air_confirmed = False
            timeout_seconds = 10 
            start_time = asyncio.get_event_loop().time()

            while asyncio.get_event_loop().time() - start_time < timeout_seconds:
                try:
                    current_in_air_status = await self.drone.telemetry.in_air().is_in_air
                    if current_in_air_status:
                        logger.info("Drone is airborne! Now monitoring altitude.")
                        in_air_confirmed = True
                        break
                    else:
                        logger.info("Drone not yet in air. Still waiting...")
                except Exception as e:
                    logger.warning(f"Error checking in_air status: {e}")
                await asyncio.sleep(1.0) 

            if not in_air_confirmed:
                logger.error("Drone did not report being in air within timeout. Aborting takeoff sequence.")
                return False

            
            logger.info("Giving telemetry a moment to update with meaningful altitude data...")
            await asyncio.sleep(2.0)

            
            logger.info("Monitoring drone altitude to reach target...")
            altitude_reached = False
            altitude_timeout_seconds = 30 
            start_altitude_monitor_time = asyncio.get_event_loop().time()

            while asyncio.get_event_loop().time() - start_altitude_monitor_time < altitude_timeout_seconds:
                try:
                    current_position = await self.drone.telemetry.position().read()
                    current_altitude = round(current_position.relative_altitude_m, 1)
                    logger.info(f"Current altitude: {current_altitude}m (Target: {altitude_m}m)")
                    if current_altitude >= altitude_m * 0.95: # Within 95% of target
                        logger.info(f"Reached target altitude of approx {altitude_m}m.")
                        altitude_reached = True
                        break
                except Exception as e:
                    logger.warning(f"Error reading position telemetry for altitude check: {e}")
                await asyncio.sleep(1.0) 

            if not altitude_reached:
                logger.error("Drone did not reach target altitude within timeout. Continuing anyway.")
                return False 

            return True 

        except Exception as e:
            logger.error(f"Failed to takeoff: {e}", exc_info=True) # Log full traceback
            return False

    async def land(self):
        if not self.is_connected:
            logger.warning("Drone not connected. Cannot land.")
            return False

        logger.info("Landing drone...")
        try:
            await self.drone.action.land()
            logger.info("Land command sent. Monitoring altitude...")
            async for position in self.drone.telemetry.position():
                if position.relative_altitude_m < 0.5: 
                    logger.info("Drone has landed.")
                    return True
                await asyncio.sleep(1) 
        except Exception as e:
            logger.error(f"Failed to land drone: {e}")
            return False

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

