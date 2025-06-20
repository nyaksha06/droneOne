import asyncio
from mavsdk import System
from mavsdk.log_level import LogLevel
import logging
import sys

logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MAVSDKInterface:
    """
    Manages all interactions with the drone via MAVSDK.
    Provides methods for connection, arming, taking off, landing,
    and subscribing to telemetry streams.
    """

    def __init__(self, system_address: str = "udp://:14540"):
        self.drone = System(sys_address=system_address)
        self.is_connected = False
        logger.info(f"MAVSDKInterface initialized for system address: {system_address}")

    async def connect(self):
        logger.info(f"Attempting to connect to the drone at {self.drone.sys_address}...")
        try:
            # log level for MAVSDK internal messages
            await self.drone.log_debug(LogLevel.INFO)

            # Wait for connection
            async for state in self.drone.core.connection_state():
                if state.is_connected:
                    logger.info("MAVSDK connected!")
                    break
            
            # Wait for the drone to be discovered and ready
            async for health in self.drone.telemetry.health():
                if health.is_global_position_ok and health.is_home_position_ok and \
                   health.is_armed and health.is_gyrometer_calibration_ok and \
                   health.is_accelerometer_calibration_ok and health.is_magnetometer_calibration_ok:
                    logger.info("Drone health is good. Ready to arm/fly.")
                    self.is_connected = True
                    return True
                else:
                    logger.info(f"Waiting for drone to be ready: {health}")
                    await asyncio.sleep(1) # Wait a bit before checking again
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
        """
        Commands the drone to take off to a specified altitude.
        :param altitude_m: Target altitude in meters.
        """
        if not self.is_connected:
            logger.warning("Drone not connected. Cannot takeoff.")
            return False
        
        logger.info(f"Taking off to {altitude_m} meters...")
        try:
            await self.drone.action.set_takeoff_altitude(altitude_m)
            await self.drone.action.takeoff()

            logger.info("Takeoff command sent. Monitoring altitude...")
            async for position in self.drone.telemetry.position():
                current_altitude = round(position.relative_altitude_m, 1)
                logger.info(f"Current altitude: {current_altitude}m")
                if current_altitude >= altitude_m * 0.95: 
                    logger.info(f"Reached target altitude of approx {altitude_m}m.")
                    return True
                await asyncio.sleep(0.5) 
        except Exception as e:
            logger.error(f"Failed to takeoff: {e}")
            return False

    async def land(self):
        """
        Commands the drone to land at its current position.
        """
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

    async def disconnect(self):
        """
        Performs any necessary cleanup before exiting.
        """
        logger.info("Disconnecting MAVSDK...")
        self.is_connected = False
        logger.info("MAVSDK interface shut down.")

