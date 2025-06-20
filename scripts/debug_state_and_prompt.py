import asyncio
import sys
import os
import logging

# Configure logging for better visibility across all modules
logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add the parent directory (drone_control_software) to the Python path
# so we can import modules from src/config, src/core, src/perception, and src/state_management
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.mavsdk_interface import MAVSDKInterface
from src.perception.telemetry_processor import TelemetryProcessor
from src.perception.camera_processor import CameraProcessor
from src.state_management.drone_state import DroneState
from config.settings import SITL_SYSTEM_ADDRESS, CRITICAL_BATTERY_PERCENTAGE, DEFAULT_TAKEOFF_ALTITUDE_M

async def main():
    """
    Main function to orchestrate MAVSDK telemetry, camera processing,
    state management, and LLM prompt generation for debugging.
    """
    # Initialize components
    mavsdk_interface = MAVSDKInterface(system_address=SITL_SYSTEM_ADDRESS)
    telemetry_processor = TelemetryProcessor()
    camera_processor = CameraProcessor()
    drone_state = DroneState()

    logger.info("Connecting to drone...")
    connected = await mavsdk_interface.connect()
    if not connected:
        logger.error("Failed to connect to the drone. Please ensure SITL is running.")
        return

    # Set an initial mission objective for context
    drone_state.set_mission_objectives("Perform a search pattern over the area, identify any anomalies, and return to home.")

    # --- Telemetry Subscriptions and Processing ---
    # Callbacks to update TelemetryProcessor with raw MAVSDK data
    async def position_velocity_ned_handler(pos_vel_ned):
        await telemetry_processor.process_position_velocity_ned(pos_vel_ned)
        
    async def attitude_euler_handler(att_euler):
        await telemetry_processor.process_attitude_euler(att_euler)

    async def battery_handler(battery_status):
        await telemetry_processor.process_battery(battery_status)

    async def flight_mode_handler(flight_mode):
        drone_state.update_flight_mode(flight_mode.mode)


    # Start MAVSDK telemetry subscriptions concurrently
    asyncio.ensure_future(mavsdk_interface.subscribe_position_velocity_ned(position_velocity_ned_handler))
    asyncio.ensure_future(mavsdk_interface.subscribe_attitude_euler(attitude_euler_handler))
    asyncio.ensure_future(mavsdk_interface.subscribe_battery(battery_handler))
    # PX4's telemetry.flight_mode() is also useful
    asyncio.ensure_future(mavsdk_interface.drone.telemetry.flight_mode(flight_mode_handler))


    # --- Main Loop for State Update and Prompt Generation ---
    logger.info("Starting main loop for state updates and prompt generation.")
    loop_count = 0
    while True:
        loop_count += 1
        
        # 1. Process camera feed (mock for now)
        await camera_processor.process_camera_feed()

        # 2. Get processed data from perception units
        processed_telemetry = telemetry_processor.get_processed_data()
        visual_insights = camera_processor.get_visual_insights()

        # 3. Update central drone state
        drone_state.update_telemetry(processed_telemetry)
        drone_state.update_visual_insights(visual_insights)
        # Note: Flight mode is updated via its direct subscription handler above

        # 4. Generate LLM prompt
        llm_prompt = drone_state.generate_llm_prompt()

        # 5. Log the generated prompt periodically
        if loop_count % 20 == 0: # Log every 20 iterations (approx every 2 seconds if sleep is 0.1s)
            logger.info(f"\n--- LLM Prompt (Iteration {loop_count}) ---")
            logger.info(llm_prompt)
            logger.info("----------------------------------\n")

        # Optional: Check for critical battery (demonstrates using processed data)
        if telemetry_processor.is_battery_critical(CRITICAL_BATTERY_PERCENTAGE):
            logger.warning(f"ALERT: Battery critical ({telemetry_processor._latest_battery.remaining_percent:.1f}%). LLM should prioritize landing.")

        await asyncio.sleep(0.1) # Small delay to prevent busy-waiting and allow async tasks to run

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Script stopped by user (Ctrl+C).")
    except Exception as e:
        logger.exception(f"An unexpected error occurred in main loop: {e}")
    finally:
        logger.info("Exiting debug_state_and_prompt script.")

