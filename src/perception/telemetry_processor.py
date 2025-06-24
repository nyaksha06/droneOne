import asyncio
import logging
import sys

logger = logging.getLogger(__name__)

class TelemetryProcessor:
    """
    Processes raw telemetry data received from MAVSDK into more structured and meaningful insights.
    """

    def __init__(self):
        """Initializes the TelemetryProcessor."""
        self._latest_position_ned = None
        self._latest_attitude_euler = None
        self._latest_battery = None
        self._is_flying = False
        logger.info("TelemetryProcessor initialized.")

    async def process_position_velocity_ned(self, pos_vel_ned):
        """
        Processes incoming PositionVelocityNed telemetry data.
        Updates internal state and derives basic flying status.
        """
        self._latest_position_ned = pos_vel_ned
        # Determine if the drone is flying based on vertical velocity
        # A simple heuristic: if vertical speed (down_m_s) is significant, it's flying.
        # This can be refined with more robust flight state detection (e.g., from flight mode).
        vertical_speed = abs(pos_vel_ned.velocity.down_m_s)
        if vertical_speed > 0.5 or pos_vel_ned.position.relative_altitude_m > 0.5:
            self._is_flying = True
        else:
            self._is_flying = False # Assume not flying if close to ground and low vertical speed

        # logger.debug(f"Processed POS_VEL_NED: RelAlt={self._latest_position_ned.position.relative_altitude_m:.2f}m, IsFlying={self._is_flying}")

    async def process_attitude_euler(self, att_euler):
        """
        Processes incoming AttitudeEuler telemetry data.
        """
        self._latest_attitude_euler = att_euler
        # logger.debug(f"Processed ATT_EULER: Roll={self._latest_attitude_euler.roll_deg:.1f}deg")

    async def process_battery(self, battery_status):
        """
        Processes incoming Battery telemetry data.
        """
        self._latest_battery = battery_status
        # logger.debug(f"Processed BATTERY: {self._latest_battery.remaining_percent:.1f}%")

    def get_processed_data(self) -> dict:
        """
        Returns a dictionary of the latest processed telemetry data.
        This structured data is intended for the State & Context Manager.
        """
        data = {
            "is_flying": self._is_flying,
            "position": {},
            "velocity": {},
            "attitude": {},
            "battery": {}
        }

        if self._latest_position_ned:
            data["position"] = {
                "latitude_deg": self._latest_position_ned.position.latitude_deg,
                "longitude_deg": self._latest_position_ned.position.longitude_deg,
                "absolute_altitude_m": self._latest_position_ned.position.absolute_altitude_m,
                "relative_altitude_m": self._latest_position_ned.position.relative_altitude_m,
            }
            data["velocity"] = {
                "north_m_s": self._latest_position_ned.velocity.north_m_s,
                "east_m_s": self._latest_position_ned.velocity.east_m_s,
                "down_m_s": self._latest_position_ned.velocity.down_m_s,
                "ground_speed_m_s": (self._latest_position_ned.velocity.north_m_s**2 +
                                     self._latest_position_ned.velocity.east_m_s**2)**0.5
            }

        if self._latest_attitude_euler:
            data["attitude"] = {
                "roll_deg": self._latest_attitude_euler.roll_deg,
                "pitch_deg": self._latest_attitude_euler.pitch_deg,
                "yaw_deg": self._latest_attitude_euler.yaw_deg,
            }

        if self._latest_battery:
            data["battery"] = {
                "remaining_percent": self._latest_battery.remaining_percent,
                "voltage_v": self._latest_battery.voltage_v,
            }
        
        return data

    def is_battery_critical(self, threshold: float) -> bool:
        """
        Checks if the battery level is below a critical threshold.
        :param threshold: The battery percentage threshold (e.g., 20.0 for 20%).
        :return: True if battery is below threshold, False otherwise.
        """
        if self._latest_battery and self._latest_battery.remaining_percent < threshold:
            logger.warning(f"Battery is critical: {self._latest_battery.remaining_percent:.1f}%")
            return True
        return False

