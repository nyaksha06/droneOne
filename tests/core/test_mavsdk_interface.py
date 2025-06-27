import asyncio
import os
from mavsdk import System
from mavsdk.offboard import PositionNedYaw, OffboardError, VelocityBodyYawspeed
from mavsdk.action import ActionError
from mavsdk.telemetry import FlightMode 
import logging
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from config.settings import SITL_SYSTEM_ADDRESS, CRITICAL_BATTERY_PERCENTAGE, OLLAMA_API_URL, OLLAMA_MODEL_NAME
from src.core.mavsdk_interface import MAVSDKInterface









async def main():

    mavsdk_interface = MAVSDKInterface(system_address=SITL_SYSTEM_ADDRESS)
    print("Connecting to drone...")
    connected = await mavsdk_interface.connect()
    if not connected:
        print("Failed to connect to the drone. Please ensure SITL is running and accessible.")
        return

    # Execute the offboard take-off
    success = await mavsdk_interface.offboard_takeoff(target_altitude_m=3.0) 

    if success:
        print("\nDrone is now in Offboard mode at 3 meters altitude.")
        print("You can now send further offboard commands (e.g., move, hover, land).")

        # Example: Hover for 10 seconds after take-off
        print("-- Hovering for 10 seconds...")
        # Continuously send the position setpoint to maintain hover
        target_down_m = -3.0 # Maintain 3 meters altitude
        hover_start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - hover_start_time < 10:
            await mavsdk_interface.drone.offboard.set_position_ned(PositionNedYaw(0.0, 0.0, target_down_m, 0.0))
            await asyncio.sleep(0.1) # Send at a good rate

        print("-- Hover complete. Stopping offboard and landing.")
        try:
            await mavsdk_interface.drone.offboard.stop()
            print("-- Offboard stopped.")
            print("-- Commanding drone to land...")
            await mavsdk_interface.drone.action.land()
            print("-- Land command sent. Disarming when landed...")
            async for flight_mode in mavsdk_interface.drone.telemetry.flight_mode():
                if flight_mode == FlightMode.LANDED:
                    print("-- Drone landed and disarmed!")
                    break
                await asyncio.sleep(1)

        except OffboardError as error:
            print(f"Failed to stop offboard: {error._result.result}")
        except Exception as e:
            print(f"An error occurred during landing: {e}")
    else:
        print("\nOffboard take-off failed. Check logs.")

    print("--- Script finished ---")



if __name__ == "__main__":
    # Run the main asynchronous function
    asyncio.run(main())
