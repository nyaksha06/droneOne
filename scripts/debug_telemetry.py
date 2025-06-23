import asyncio
import sys
import os

# Add the parent directory (drone_control_software) to the Python path
# so we can import modules from src/config and src/core
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.mavsdk_interface import MAVSDKInterface
from config.settings import SITL_SYSTEM_ADDRESS
import logging

logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def position_velocity_ned_callback(pos_vel_ned):
    logger.info(f"POS_NED: North={pos_vel_ned.position.north_m:.2f}m, "
                f"East={pos_vel_ned.position.east_m:.2f}m, "
                f"Down={pos_vel_ned.position.down_m:.2f}m"
                )
    logger.info(f"VEL_NED: Vx={pos_vel_ned.velocity.north_m_s:.2f}m/s, "
                f"Vy={pos_vel_ned.velocity.east_m_s:.2f}m/s, "
                f"Vz={pos_vel_ned.velocity.down_m_s:.2f}m/s")

async def global_position_callback(position):
    logger.info(f"GLOBAL_POS: Lat={position.latitude_deg:.6f}, "
                f"Lon={position.longitude_deg:.6f}, "
                f"AbsAlt={position.absolute_altitude_m:.2f}m, "
                f"RelAlt={position.relative_altitude_m:.2f}m")

async def attitude_callback(att_euler):
    """Callback for attitude (Euler angles) telemetry."""
    logger.info(f"ATT_EULER: Roll={att_euler.roll_deg:.2f}deg, "
                f"Pitch={att_euler.pitch_deg:.2f}deg, "
                f"Yaw={att_euler.yaw_deg:.2f}deg")

async def battery_callback(battery_status):
    """Callback for battery status telemetry."""
    logger.info(f"BATTERY: {battery_status.remaining_percent:.1f}% remaining, "
                f"Voltage={battery_status.voltage_v:.2f}V")

async def main():
    """
    Main function to connect to the drone and subscribe to telemetry.
    """
    mavsdk_interface = MAVSDKInterface(system_address=SITL_SYSTEM_ADDRESS)

    # Attempt to connect to the drone
    connected = await mavsdk_interface.connect()
    if not connected:
        logger.error("Failed to connect to the drone. Exiting.")
        return


    asyncio.ensure_future(mavsdk_interface.subscribe_position_velocity_ned(position_velocity_ned_callback))
    asyncio.ensure_future(mavsdk_interface.subscribe_position(global_position_callback))
    asyncio.ensure_future(mavsdk_interface.subscribe_attitude_euler(attitude_callback))
    asyncio.ensure_future(mavsdk_interface.subscribe_battery(battery_callback))

    logger.info("Telemetry subscriptions started. Monitoring drone data...")
    logger.info("You can open QGroundControl/Mission Planner to see the drone.")
    logger.info("Press Ctrl+C to stop.")


    while True:
        await asyncio.sleep(1) 

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Script stopped by user (Ctrl+C).")
    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")
    finally:
        # No explicit disconnect needed for MAVSDK, but good to clean up
        logger.info("Exiting debug_telemetry script.")

