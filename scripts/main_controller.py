import asyncio
import sys
import os
import logging

# Configure logging for better visibility across all modules
logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add the parent directory (drone_control_software) to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.mavsdk_interface import MAVSDKInterface
from src.core.command_arbitrator import CommandArbitrator 
from src.core.command_executor import CommandExecutor     
from src.perception.telemetry_processor import TelemetryProcessor
from src.perception.camera_processor import CameraProcessor
from src.state_management.drone_state import DroneState
from src.decision_making.llm_engine import LLMDecisionEngine
from config.settings import SITL_SYSTEM_ADDRESS, CRITICAL_BATTERY_PERCENTAGE, OLLAMA_API_URL, OLLAMA_MODEL_NAME

# Global variable to hold human commands from a separate task
_human_command_queue = asyncio.Queue()

async def get_human_input_task():
    """
    Asynchronously reads human commands from stdin.
    This runs in a separate thread/task to not block the main asyncio loop.
    """
    logger.info("\n--- Human Control Input ---")
    logger.info("Type 'land' to land the drone.")
    logger.info("Type 'disarm' to disarm the drone.")
    logger.info("Type 'release' to let LLM take control again.")
    logger.info("Type 'exit' to stop the script.")
    logger.info("---------------------------\n")

    loop = asyncio.get_event_loop()
    while True:
        try:
            user_input = await loop.run_in_executor(None, sys.stdin.readline)
            command_text = user_input.strip().lower()

            if command_text == "exit":
                await _human_command_queue.put({"action": "exit"})
                break
            elif command_text == "land":
                await _human_command_queue.put({"action": "land", "reason": "Human override: manual land."})
            elif command_text == "disarm":
                await _human_command_queue.put({"action": "disarm", "reason": "Human override: manual disarm."})
            elif command_text == "release":
                await _human_command_queue.put({"action": "release", "reason": "Human released control."})
            else:
                logger.warning(f"Unknown human command: '{command_text}'. Please use 'land', 'disarm', 'release', or 'exit'.")
        except Exception as e:
            logger.error(f"Error reading human input: {e}")
            break

async def main():
    """
    Main function to orchestrate the entire drone control system:
    Perception (Telemetry, Camera) -> State Management -> LLM Decision -> Command Arbitration -> Command Execution.
    Includes basic human override.
    """
    # Initialize components
    mavsdk_interface = MAVSDKInterface(system_address=SITL_SYSTEM_ADDRESS)
    telemetry_processor = TelemetryProcessor()
    camera_processor = CameraProcessor()
    drone_state = DroneState()
    llm_engine = LLMDecisionEngine(ollama_api_url=OLLAMA_API_URL, ollama_model_name=OLLAMA_MODEL_NAME)
    command_arbitrator = CommandArbitrator() 
    command_executor = CommandExecutor(mavsdk_interface) 

    logger.info("Connecting to drone...")
    connected = await mavsdk_interface.connect()
    if not connected:
        logger.error("Failed to connect to the drone. Please ensure SITL is running and accessible.")
        return

    # Set an initial mission objective for context
    drone_state.set_mission_objectives("Tackoff up to 20m than goto 10m in north  and than land.")

    # --- Telemetry Subscriptions and Processing ---
    async def position_velocity_ned_handler(pos_vel_ned):
        await telemetry_processor.process_position_velocity_ned(pos_vel_ned)
        
    async def global_position_handler(position):
        await telemetry_processor.process_global_position(position)

    async def attitude_euler_handler(att_euler):
        await telemetry_processor.process_attitude_euler(att_euler)

    async def battery_handler(battery_status):
        await telemetry_processor.process_battery(battery_status)

    async def flight_mode_handler(flight_mode_status):
        drone_state.update_flight_mode(str(flight_mode_status))


    # Start MAVSDK telemetry subscriptions concurrently
    asyncio.ensure_future(mavsdk_interface.subscribe_position_velocity_ned(position_velocity_ned_handler))
    asyncio.ensure_future(mavsdk_interface.subscribe_position(global_position_handler))
    asyncio.ensure_future(mavsdk_interface.subscribe_attitude_euler(attitude_euler_handler))
    asyncio.ensure_future(mavsdk_interface.subscribe_battery(battery_handler))
    asyncio.ensure_future(mavsdk_interface.subscribe_flight_mode(flight_mode_handler))

    
    human_input_task = asyncio.ensure_future(get_human_input_task())


    logger.info("Starting main control loop.")
    llm_loop_count = 0 
    main_loop_interval = 5
    llm_decision_interval_loops = 1 

    
    current_llm_action = {"action": "do_nothing", "reason": "System startup, awaiting first LLM decision."}
    
    while True:
        try:
            if not _human_command_queue.empty():
                human_cmd = await _human_command_queue.get()
                if human_cmd["action"] == "exit":
                    logger.info("Exit command received. Shutting down...")
                    break # Exit main loop
                elif human_cmd["action"] == "release":
                    command_arbitrator.release_human_control()
                else:
                    command_arbitrator.set_human_command(human_cmd)
                    if human_cmd["action"] in ["land", "disarm"]:
                        await command_executor.execute_command(human_cmd)

            # 1. Process camera feed (mock for now)
            await camera_processor.process_camera_feed()

            # 2. Update central drone state
            processed_telemetry = telemetry_processor.get_processed_data()
            visual_insights = camera_processor.get_visual_insights()
            drone_state.update_telemetry(processed_telemetry)
            drone_state.update_visual_insights(visual_insights)
            drone_state.update_last_action(current_llm_action["action"])

            # 3. Generate LLM prompt (only if LLM decision is needed this cycle)
            if llm_loop_count % llm_decision_interval_loops == 0:
                llm_prompt = drone_state.generate_llm_prompt()
                new_llm_action = await llm_engine.get_action_from_llm(llm_prompt)
                if new_llm_action: 
                    current_llm_action = new_llm_action
                logger.info(f"LLM Decision Cycle: Proposed action: {current_llm_action.get('action')}")
                llm_loop_count = 0 

            llm_loop_count += 1

            # 4. Arbitrate command
            final_command = command_arbitrator.arbitrate_command(current_llm_action)
            
            # 5. Execute command
            # Only execute if it's an LLM command OR a human command that wasn't already executed above (like 'release')
            if final_command.get("action") not in ["release"]:
                await command_executor.execute_command(final_command)
            else:
                logger.info(f"Skipping execution for command type: {final_command.get('action')}")


            # Optional: Check for critical battery 
            # if telemetry_processor.is_battery_critical(CRITICAL_BATTERY_PERCENTAGE):
            #     battery_percent = telemetry_processor._latest_battery.remaining_percent if telemetry_processor._latest_battery else 'N/A'
            #     logger.warning(f"ALERT: Battery critical ({battery_percent}%). LLM should prioritize landing.")
                #  force a land if battery is critically low, overriding LLM and human
                # await command_executor.execute_command({"action": "land", "reason": "Emergency: Critical Battery."})


            await asyncio.sleep(main_loop_interval)

        except KeyboardInterrupt:
            logger.info("Script stopped by user (Ctrl+C).")
            break
        except Exception as e:
            logger.exception(f"An unexpected error occurred in main loop: {e}")
            break 

    # --- Cleanup ---
    logger.info("Performing final cleanup and disconnecting from drone.")
    human_input_task.cancel()
    try:
        await human_input_task
    except asyncio.CancelledError:
        logger.info("Human input task cancelled.")
    await mavsdk_interface.disconnect()
    logger.info("Main controller shut down.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application terminated by user (Ctrl+C).")
    except Exception as e:
        logger.exception(f"Unhandled exception during application startup/shutdown: {e}")

