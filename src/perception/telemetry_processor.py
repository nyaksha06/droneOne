import asyncio
import logging
import sys

logger = logging.getLogger(__name__)

class TelemetryProcessor:
    """
    Processes raw telemetry data received from MAVSDK into more structured and meaningful insights.
    It can also perform basic calculations and health checks.
    """

    def __init__(self):
        """Initializes the TelemetryProcessor."""
        self._latest_position_ned = None    # Stores data from position_velocity_ned()
        self._latest_global_position = None # Stores data from position() for Lat/Lon/AbsAlt
        self._latest_attitude_euler = None
        self._latest_battery = None
        self._is_flying = False
        logger.info("TelemetryProcessor initialized.")

    async def process_position_velocity_ned(self, pos_vel_ned):
        """
        Processes incoming PositionVelocityNed telemetry data.
        Updates internal state and derives basic flying status using NED data.
        """
        self._latest_position_ned = pos_vel_ned
        
        # Determine if the drone is flying based on vertical velocity (down_m_s)
        # and potentially its 'down_m' position (altitude in NED frame, positive down).
        # We'll use absolute altitude from global_position if available for robustness later.
        vertical_speed = abs(pos_vel_ned.velocity.down_m_s)
        
        # A simple heuristic: if vertical speed (down_m_s) is significant, it's flying.
        # Or if it's significantly above ground (using down_m, or relative_altitude_m if available from global_position)
        # Note: 'down_m' is positive downwards. So a negative value means it's above the origin.
        current_altitude_ned = -pos_vel_ned.position.down_m if pos_vel_ned.position.down_m is not None else 0.0

        if vertical_speed > 0.5 or current_altitude_ned > 0.5: # 0.5m/s or 0.5m altitude threshold
            self._is_flying = True
        else:
            self._is_flying = False # Assume not flying if close to ground and low vertical speed

        # logger.debug(f"Processed POS_VEL_NED: DownM={self._latest_position_ned.position.down_m:.2f}m, IsFlying={self._is_flying}")

    async def process_global_position(self, global_position):
        """
        Processes incoming Position (global lat/lon/alt) telemetry data.
        """
        self._latest_global_position = global_position
        # logger.debug(f"Processed GLOBAL_POS: Lat={self._latest_global_position.latitude_deg:.4f}, Lon={self._latest_global_position.longitude_deg:.4f}")

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
        Returns a dictionary of the latest processed telemetry data, combining
        local NED and global position data.
        """
        data = {
            "is_flying": self._is_flying,
            "position": {},
            "velocity": {},
            "attitude": {},
            "battery": {}
        }

        # Global position data (Lat/Lon/AbsAlt/RelAlt) from _latest_global_position
        if self._latest_global_position:
            data["position"] = {
                "latitude_deg": self._latest_global_position.latitude_deg,
                "longitude_deg": self._latest_global_position.longitude_deg,
                "absolute_altitude_m": self._latest_global_position.absolute_altitude_m,
                "relative_altitude_m": self._latest_global_position.relative_altitude_m,
            }
        # Local NED position and velocity from _latest_position_ned
        if self._latest_position_ned:
            if not data["position"]: # If global position wasn't set, at least put NED alt
                 data["position"]["relative_altitude_m"] = -self._latest_position_ned.position.down_m if self._latest_position_ned.position.down_m is not None else 0.0

            data["position"]["north_m"] = self._latest_position_ned.position.north_m
            data["position"]["east_m"] = self._latest_position_ned.position.east_m
            data["position"]["down_m"] = self._latest_position_ned.position.down_m
            
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
