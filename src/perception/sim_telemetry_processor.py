import asyncio
import logging
import sys
from mavsdk import System
# Assuming MAVSDKInterface is in src.core
from src.core.mavsdk_interface import MAVSDKInterface 

logger = logging.getLogger(__name__)

class SimTelemetryProcessor:
    """
    Processes raw telemetry data received from MAVSDK into more structured and meaningful insights.
    It can also perform basic calculations and health checks.
    """

    def __init__(self, mavsdk_interface: MAVSDKInterface): # MODIFIED: Take MAVSDKInterface instance
        """Initializes the SimTelemetryProcessor."""
        self.mavsdk_interface = mavsdk_interface # Store the MAVSDKInterface instance
        self.telemetry_data = {}
        self._latest_battery = None
        self._in_air = False
        self._armed = False # NEW: Track armed status
        self._flight_mode = "UNKNOWN" # NEW: Track flight mode

        logger.info("SimTelemetryProcessor initialized.")

    async def get_processed_data(self) -> dict:
        """
        Retrieves the latest telemetry data from the drone via MAVSDKInterface's helper
        and processes it into a structured dictionary.
        """
        processed_data = {}

        # Use the _read_stream_value helper from MAVSDKInterface for efficient polling
        # Position (includes relative altitude, lat/lon)
        position_data = await self.mavsdk_interface._read_stream_value(self.mavsdk_interface.drone.telemetry.position)
        if position_data:
            processed_data["position"] = {
                "latitude_deg": position_data.latitude_deg,
                "longitude_deg": position_data.longitude_deg,
                "absolute_altitude_m": position_data.absolute_altitude_m,
                "relative_altitude_m": position_data.relative_altitude_m,
            }
        else:
            processed_data["position"] = {} # Ensure key exists even if no data

        # Position and Velocity NED (includes north_m, east_m, down_m, and ground_speed_m_s)
        pos_vel_ned_data = await self.mavsdk_interface._read_stream_value(self.mavsdk_interface.drone.telemetry.position_velocity_ned)
        if pos_vel_ned_data:
            processed_data["position_ned"] = {
                "north_m": pos_vel_ned_data.position.north_m,
                "east_m": pos_vel_ned_data.position.east_m,
                "down_m": pos_vel_ned_data.position.down_m,
            }
            processed_data["velocity"] = { # Extract velocity from this stream
                "north_m_s": pos_vel_ned_data.velocity.north_m_s,
                "east_m_s": pos_vel_ned_data.velocity.east_m_s,
                "down_m_s": pos_vel_ned_data.velocity.down_m_s,
                "ground_speed_m_s": pos_vel_ned_data.velocity.ground_speed_m_s,
            }
        else:
            processed_data["position_ned"] = {}
            processed_data["velocity"] = {}

        # Battery status
        battery_data = await self.mavsdk_interface._read_stream_value(self.mavsdk_interface.drone.telemetry.battery)
        if battery_data:
            processed_data["battery"] = {
                "remaining_percent": int(battery_data.remaining_percent * 100),
                "voltage_v": round(battery_data.voltage_v, 2)
            }
            self._latest_battery = battery_data # Store raw object for is_battery_critical
        else:
            processed_data["battery"] = {}

        # In-air status
        in_air_data = await self.mavsdk_interface._read_stream_value(self.mavsdk_interface.drone.telemetry.in_air)
        if in_air_data:
            processed_data["is_flying"] = in_air_data.is_in_air # Use is_in_air boolean
            self._in_air = in_air_data.is_in_air # Update internal flag
        else:
            processed_data["is_flying"] = False

        # Armed status
        armed_data = await self.mavsdk_interface._read_stream_value(self.mavsdk_interface.drone.telemetry.armed)
        if armed_data is not None: # `armed()` can return None if no data yet
            processed_data["is_armed"] = armed_data
            self._armed = armed_data
        else:
            processed_data["is_armed"] = False

        # Flight mode
        flight_mode_data = await self.mavsdk_interface._read_stream_value(self.mavsdk_interface.drone.telemetry.flight_mode)
        if flight_mode_data:
            processed_data["flight_mode"] = str(flight_mode_data) # Convert enum to string
            self._flight_mode = str(flight_mode_data)
        else:
            processed_data["flight_mode"] = "UNKNOWN"

        # Store the complete processed data
        self.telemetry_data = processed_data
        return self.telemetry_data

    def is_battery_critical(self, threshold_percent: float) -> bool:
        """
        Checks if the battery level is below a critical threshold.
        :param threshold_percent: The percentage below which battery is considered critical.
        :return: True if battery is critical, False otherwise.
        """
        if self._latest_battery and self._latest_battery.remaining_percent is not None:
            return (self._latest_battery.remaining_percent * 100) < threshold_percent
        return False

