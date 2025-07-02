import asyncio
import logging
import sys
from mavsdk import System

logger = logging.getLogger(__name__)

class SimTelemetryProcessor:
    """
    Processes raw telemetry data received from MAVSDK into more structured and meaningful insights.
    It can also perform basic calculations and health checks.
    """

    def __init__(self,drone : System):
        """Initializes the TelemetryProcessor."""
        self.drone = drone
        self.telemetry_data = {}
        self._latest_position_ned = None   
        # self._latest_global_position = None 
        # self._latest_attitude_euler = None
        self._latest_battery = None
        self._in_air = False
        logger.info("TelemetryProcessor initialized.")

    
    async def get_processed_data(self) -> dict:
        self.telemetry_data = {}

        #position global
        # async for position in self.drone.telemetry.position():
        #     telemetry_data["position"] = {
        #         "latitude_deg": position.latitude_deg,
        #         "longitude_deg": position.longitude_deg,
        #         "relative_altitude_m": position.relative_altitude_m
        #     }
        #     self._latest_global_position = telemetry_data["position"]
        #     break # Get current value and break


        # position NED
        async for position_ned in self.drone.telemetry.position_velocity_ned():
            self.telemetry_data["position_ned"] = {
                "north_m": position_ned.position.north_m,
                "east_m": position_ned.position.east_m,
                "down_m": position_ned.position.down_m
            }
            self._latest_position_ned = self.telemetry_data["position_ned"]
            break
        
        #velocity
        # async for velocity_ned in self.drone.telemetry.velocity_ned():
        #     telemetry_data["velocity_ned"] = {
        #         "north_m_s": velocity_ned.north_m_s,
        #         "east_m_s": velocity_ned.east_m_s,
        #         "down_m_s": velocity_ned.down_m_s
        #     }

        #     break

        #attitude
        # async for attitude_euler in self.drone.telemetry.attitude_euler():
        #     telemetry_data["attitude_euler"] = {
        #         "roll_deg": attitude_euler.roll_deg,
        #         "pitch_deg": attitude_euler.pitch_deg,
        #         "yaw_deg": attitude_euler.yaw_deg
        #     }
        #     break

        #battery status
        async for battery in self.drone.telemetry.battery():
            self.telemetry_data["battery"] = {
                "remaining_percent": int(battery.remaining_percent * 100),
                "voltage_v": round(battery.voltage_v, 2)
            }
            self._latest_battery = self.telemetry_data["battery"]
            break

        #flight mode
        # async for flight_mode in self.drone.telemetry.flight_mode():
        #     telemetry_data["flight_mode"] = flight_mode.name
        #     break

        # #GPS info
        # async for gps_info in self.drone.telemetry.gps_info():
        #     telemetry_data["gps_info"] = {
        #         "num_satellites": gps_info.num_satellites,
        #         "fix_type": gps_info.fix_type.value # 0: No Fix, 1: No GPS, 2: 2D Fix, 3: 3D Fix
        #     }
        #     break

        
        
        async for in_air in self.drone.telemetry.in_air():
            self.telemetry_data["in_air"] = in_air
            self._in_air = self.telemetry_data["in_air"]
            break
        
        # async for armed in self.drone.telemetry.armed():
        #     telemetry_data["armed"] = armed
        #     break

        return 

    
