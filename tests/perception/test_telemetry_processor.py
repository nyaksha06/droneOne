import asyncio
import logging
import sys
import os


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.core.mavsdk_interface import MAVSDKInterface   
from src.perception.telemetry_processor import TelemetryProcessor
from config.settings import SITL_SYSTEM_ADDRESS, CRITICAL_BATTERY_PERCENTAGE, OLLAMA_API_URL, OLLAMA_MODEL_NAME



async def main():
    mavsdk_interface = MAVSDKInterface(system_address=SITL_SYSTEM_ADDRESS)
    telemetry_processor = TelemetryProcessor()
    print("Connecting to the Drone")
    connected = await mavsdk_interface.connect()
    if not connected:
        print("Failed to connect to the drone. Please ensure SITL is running and accessible.")
        return
    

    async def position_velocity_ned_handler(pos_vel_ned):
        await telemetry_processor.process_position_velocity_ned(pos_vel_ned)
        
    async def global_position_handler(position):
        await telemetry_processor.process_global_position(position)

    async def attitude_euler_handler(att_euler):
        await telemetry_processor.process_attitude_euler(att_euler)

    async def battery_handler(battery_status):
        await telemetry_processor.process_battery(battery_status)

    


    # Start MAVSDK telemetry subscriptions concurrently
    asyncio.ensure_future(mavsdk_interface.subscribe_position_velocity_ned(position_velocity_ned_handler))
    asyncio.ensure_future(mavsdk_interface.subscribe_position(global_position_handler))
    asyncio.ensure_future(mavsdk_interface.subscribe_attitude_euler(attitude_euler_handler))
    asyncio.ensure_future(mavsdk_interface.subscribe_battery(battery_handler))
    

    processed_telemetry = telemetry_processor.get_processed_data()

    print(processed_telemetry)





if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Unhandled exception during application startup/shutdown: {e}")
