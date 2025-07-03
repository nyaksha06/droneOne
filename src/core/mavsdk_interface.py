import asyncio
import logging
from mavsdk import System
from mavsdk.telemetry import FlightMode
from mavsdk.action import ActionError

logger = logging.getLogger(__name__)

class MAVSDKInterface:
    """
    Handles all direct communication with the drone via MAVSDK.
    Manages connection, basic flight actions, and telemetry subscriptions.
    """

    def __init__(self, system_address: str = "udp://:14540"):
        """
        Initializes the MAVSDKInterface.
        :param system_address: MAVLink connection string (e.g., "udp://:14540").
        """
        self.drone = System()
        self._system_address = system_address
        self.is_connected = False
        self._telemetry_tasks = []
        logger.info(f"MAVSDKInterface initialized for system address: {self._system_address}")

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

    async def disconnect(self):
        """
        Disconnects from the drone and stops any active telemetry subscriptions.
        """
        logger.info("Disconnecting from drone...")
        for task in self._telemetry_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._telemetry_tasks.clear()
        self.is_connected = False
        logger.info("Disconnected from drone.")

    async def arm(self) -> bool:
        """Arms the drone."""
        logger.info("Arming drone...")
        try:
            await self.drone.action.arm()
            logger.info("Drone armed.")
            return True
        except ActionError as e:
            logger.error(f"Failed to arm drone: {e}")
            return False

    async def disarm(self) -> bool:
        """Disarms the drone."""
        logger.info("Disarming drone...")
        try:
            await self.drone.action.disarm()
            logger.info("Drone disarmed.")
            return True
        except ActionError as e:
            logger.error(f"Failed to disarm drone: {e}")
            return False

    async def takeoff(self, altitude_m: float = 2.5) -> bool:
        """
        Commands the drone to takeoff to a specified altitude.
        :param altitude_m: Target altitude in meters.
        """
        logger.info(f"Taking off to {altitude_m} meters...")
        try:
            await self.drone.action.set_takeoff_altitude(altitude_m)
            await self.drone.action.takeoff()
            logger.info("Takeoff command sent.")
            return True
        except ActionError as e:
            logger.error(f"Failed to takeoff: {e}")
            return False

    async def land(self) -> bool:
        """Commands the drone to land."""
        logger.info("Landing drone...")
        try:
            await self.drone.action.land()
            logger.info("Land command sent.")
            return True
        except ActionError as e:
            logger.error(f"Failed to land: {e}")
            return False

    async def set_return_to_launch(self) -> bool:
        """Sets the drone to return to launch (RTL) mode."""
        logger.info("Setting RTL mode...")
        try:
            await self.drone.action.return_to_launch()
            logger.info("RTL command sent.")
            return True
        except ActionError as e:
            logger.error(f"Failed to set RTL: {e}")
            return False

    async def set_hold_mode(self) -> bool:
        """Sets the drone to hold its current position."""
        logger.info("Setting Hold mode...")
        try:
            await self.drone.action.hold()
            logger.info("Hold command sent.")
            return True
        except ActionError as e:
            logger.error(f"Failed to set Hold mode: {e}")
            return False

    async def goto_location(self, latitude_deg: float, longitude_deg: float, altitude_m: float, yaw_deg: float = 0.0) -> bool:
        """
        Commands the drone to go to a specific global latitude, longitude, and altitude.
        :param latitude_deg: Target latitude in degrees.
        :param longitude_deg: Target longitude in degrees.
        :param altitude_m: Target altitude in meters (relative to home).
        :param yaw_deg: Target yaw in degrees (0 for North, 90 for East, etc.).
        """
        logger.info(f"Going to Lat: {latitude_deg:.6f}, Lon: {longitude_deg:.6f}, Alt: {altitude_m:.2f}m, Yaw: {yaw_deg:.2f}deg...")
        try:
            # MAVSDK's goto_location uses relative altitude by default if not specified otherwise.
            # It also has a 'speed_m_s' parameter if you want to control speed.
            await self.drone.action.goto_location(latitude_deg, longitude_deg, altitude_m, yaw_deg)
            logger.info("Goto location command sent.")
            return True
        except ActionError as e:
            logger.error(f"Failed to go to location: {e}")
            return False

    async def _read_stream_value(self, stream_func):
        """
        Helper to read the current value from a MAVSDK telemetry stream without blocking.
        This is crucial for polling.
        :param stream_func: The MAVSDK telemetry stream function (e.g., self.drone.telemetry.position).
        :return: The latest value from the stream, or None if no value yet.
        """
        try:
            async for value in stream_func():
                return value
        except Exception as e:
            logger.debug(f"Could not read from stream {stream_func.__name__}: {e}")
            return None
        finally:
            if stream_func._generator is not None:
                try:
                    stream_func._generator.close()
                except RuntimeError:
                    pass

    async def subscribe_position(self, handler):
        """Subscribes to global position telemetry."""
        logger.debug("Subscribing to position telemetry (legacy).")
        task = asyncio.ensure_future(self._subscribe_and_handle(self.drone.telemetry.position, handler))
        self._telemetry_tasks.append(task)

    async def subscribe_position_velocity_ned(self, handler):
        """Subscribes to NED position and velocity telemetry."""
        logger.debug("Subscribing to position_velocity_ned telemetry (legacy).")
        task = asyncio.ensure_future(self._subscribe_and_handle(self.drone.telemetry.position_velocity_ned, handler))
        self._telemetry_tasks.append(task)

    async def subscribe_attitude_euler(self, handler):
        """Subscribes to attitude (Euler angles) telemetry."""
        logger.debug("Subscribing to attitude_euler telemetry (legacy).")
        task = asyncio.ensure_future(self._subscribe_and_handle(self.drone.telemetry.attitude_euler, handler))
        self._telemetry_tasks.append(task)

    async def subscribe_battery(self, handler):
        """Subscribes to battery status telemetry."""
        logger.debug("Subscribing to battery telemetry (legacy).")
        task = asyncio.ensure_future(self._subscribe_and_handle(self.drone.telemetry.battery, handler))
        self._telemetry_tasks.append(task)

    async def subscribe_flight_mode(self, handler):
        """Subscribes to flight mode telemetry."""
        logger.debug("Subscribing to flight_mode telemetry (legacy).")
        task = asyncio.ensure_future(self._subscribe_and_handle(self.drone.telemetry.flight_mode, handler))
        self._telemetry_tasks.append(task)

    async def _subscribe_and_handle(self, stream_func, handler):
        """Helper to subscribe to a stream and pass data to a handler."""
        try:
            async for data in stream_func():
                await handler(data)
        except asyncio.CancelledError:
            logger.debug(f"Telemetry subscription for {stream_func.__name__} cancelled.")
        except Exception as e:
            logger.error(f"Error in telemetry stream {stream_func.__name__}: {e}")

