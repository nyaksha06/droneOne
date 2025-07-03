import asyncio
import sys
import os
import logging


logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.mavsdk_interface import MAVSDKInterface
from src.core.command_arbitrator import CommandArbitrator
from src.core.command_executor import CommandExecutor
from src.perception.sim_telemetry_processor import SimTelemetryProcessor 
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
    logger.info("Type 'release' to let LLM take control (on trigger).")
    logger.info("Type 'stop_follow' to stop LLM-driven following.")
    logger.info("Type 'simulate_person' to trigger a mock person detection.")
    logger.info("Type 'clear_detection' to clear mock detection.")
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
            elif command_text == "stop_follow":
                await _human_command_queue.put({"action": "stop_follow", "reason": "Human stopped LLM follow."})
            elif command_text == "simulate_person":
                await _human_command_queue.put({"action": "simulate_person", "reason": "Human triggered mock person detection."})
            elif command_text == "clear_detection":
                await _human_command_queue.put({"action": "clear_detection", "reason": "Human cleared mock detection."})
            else:
                logger.warning(f"Unknown human command: '{command_text}'.")
        except Exception as e:
            logger.error(f"Error reading human input: {e}")
            break

async def main():
    """
    Main function to orchestrate the drone control system in a human-centric,
    trigger-based LLM assistance paradigm.
    """
    # Initialize components
    mavsdk_interface = MAVSDKInterface(system_address=SITL_SYSTEM_ADDRESS)
    
    # MODIFIED: Pass mavsdk_interface to SimTelemetryProcessor
    telemetry_processor = SimTelemetryProcessor(mavsdk_interface=mavsdk_interface) 
    
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

    # --- Initial System State & Mission Context ---
    overall_mission_objective = (
        "Maintain human-guided surveillance. If a specific activity/object is detected "
        "and human control is released, the AI should propose and execute a 'follow_target' action. "
        "Human can always override."
    )
    drone_state.set_mission_objectives(overall_mission_objective) 
    
  

    # Start human input task
    human_input_task = asyncio.ensure_future(get_human_input_task())

    # --- Main Control Loop ---
    logger.info("Starting main control loop. Human control is active by default.")
    llm_loop_count = 0
    main_loop_interval = 0.1 # 100ms
    llm_decision_interval_loops = 50 # Call LLM every 50 loops (i.e., every 5 seconds)

    last_llm_proposed_action = {"action": "do_nothing", "reason": "System startup, awaiting human input."}
    
    # --- Control flags for human/LLM interaction ---
    mission_finished = False
    # Start with human control active. LLM will not be queried initially.
    # command_arbitrator.set_human_control({"action": "pause_llm", "reason": "System startup, human control active."})
    drone_state.set_human_control_status(True) # Inform drone_state

    # Flags to manage trigger and LLM following state
    llm_should_be_active = False # True when human types 'release'
    llm_is_currently_following = False # True when LLM has commanded 'follow_target' and it's active

    while not mission_finished:
        try:
            # --- Handle Human Commands ---
            if not _human_command_queue.empty():
                human_cmd = await _human_command_queue.get()
                if human_cmd["action"] == "exit":
                    logger.info("Exit command received. Shutting down...")
                    mission_finished = True
                    break
                elif human_cmd["action"] == "land":
                    await command_executor.execute_command(human_cmd)
                    drone_state.set_last_executed_command(human_cmd)
                    # If human lands, they implicitly take control back, LLM pauses
                    command_arbitrator.set_human_control({"action": "pause_llm", "reason": "Human landed drone."})
                    drone_state.set_human_control_status(True)
                    llm_should_be_active = False
                    llm_is_currently_following = False
                elif human_cmd["action"] == "disarm":
                    await command_executor.execute_command(human_cmd)
                    drone_state.set_last_executed_command(human_cmd)
                    # If human disarms, they implicitly take control back, LLM pauses
                    command_arbitrator.set_human_control({"action": "pause_llm", "reason": "Human disarmed drone."})
                    drone_state.set_human_control_status(True)
                    llm_should_be_active = False
                    llm_is_currently_following = False
                elif human_cmd["action"] == "release":
                    command_arbitrator.release_human_control()
                    drone_state.set_human_control_status(False) # Inform drone_state
                    llm_should_be_active = True # Allow LLM to make decisions now
                    logger.info("Human released control. LLM will now be queried if a trigger is active.")
                    llm_loop_count = llm_decision_interval_loops - 1 # Trigger immediate LLM decision
                elif human_cmd["action"] == "stop_follow":
                    command_arbitrator.set_human_control({"action": "do_nothing", "reason": "Human stopped LLM follow."})
                    drone_state.set_human_control_status(True) # Human takes back control
                    drone_state.set_llm_following_status(False) # LLM is no longer following
                    llm_is_currently_following = False
                    llm_should_be_active = False # LLM pauses until new 'release'
                    logger.info("Human stopped LLM-driven follow. Control returned to human.")
                    await command_executor.execute_command({"action": "do_nothing", "reason": "Human stopped follow."})
                    drone_state.set_last_executed_command({"action": "do_nothing", "reason": "Human stopped follow."})
                elif human_cmd["action"] == "simulate_person":
                    camera_processor.simulate_detection(object_type="person", distance_m=15.0, relative_position="ahead_center")
                    logger.info("Simulated person detection triggered.")
                elif human_cmd["action"] == "clear_detection":
                    camera_processor.clear_detections()
                    logger.info("Simulated detection cleared.")
                else:
                    logger.warning(f"Unknown human command: '{human_cmd['action']}'.")

            # 1. Process camera feed (mock for now)
            await camera_processor.process_camera_feed()

            # 2. Get processed data from perception units
            # MODIFIED: Call get_processed_data() on telemetry_processor
            processed_telemetry = await telemetry_processor.get_processed_data() 
            visual_insights = camera_processor.get_visual_insights()

            # 3. Update central drone state
            drone_state.update_telemetry(processed_telemetry)
            drone_state.update_visual_insights(visual_insights)
            # MODIFIED: Update flight mode from processed telemetry
            drone_state.update_flight_mode(processed_telemetry.get("flight_mode", "UNKNOWN"))
            
            # Update drone_state's internal flags for LLM prompting
            drone_state.set_human_control_status(command_arbitrator._human_control_active)
            drone_state.set_llm_following_status(llm_is_currently_following)

            # --- LLM Decision Logic ---
            # Query LLM only if LLM should be active AND it's time for a new decision
            # (i.e., human has released control, and either a trigger is active or LLM is already following)
            if llm_should_be_active and (llm_loop_count % llm_decision_interval_loops) == 0:
                
                # Check for active trigger (detected object)
                current_detected_objects = visual_insights.get("detected_objects", [])
                trigger_active = len(current_detected_objects) > 0

                # Only query LLM if there's a trigger OR LLM is already following
                if trigger_active or llm_is_currently_following:
                    llm_prompt = drone_state.generate_llm_prompt()
                    new_llm_action = await llm_engine.get_action_from_llm(llm_prompt)
                    
                    if new_llm_action and "action" in new_llm_action:
                        last_llm_proposed_action = new_llm_action
                        logger.info(f"LLM Decision Cycle: Proposed new action: {last_llm_proposed_action.get('action')}")
                        
                        # Update LLM following status based on its proposed action
                        if last_llm_proposed_action["action"] == "follow_target":
                            llm_is_currently_following = True
                        elif last_llm_proposed_action["action"] == "do_nothing" and llm_is_currently_following:
                            # If LLM proposes do_nothing while following, it might mean target lost
                            logger.info("LLM proposed 'do_nothing' while following. Assuming target lost or follow complete.")
                            llm_is_currently_following = False
                            # Human control will remain released, LLM will keep proposing do_nothing until new trigger or human takes control
                        elif last_llm_proposed_action["action"] in ["land", "disarm"]:
                            # If LLM proposes land/disarm, it means it's ending its autonomous control
                            llm_is_currently_following = False
                            llm_should_be_active = False # LLM pauses after this action
                            command_arbitrator.set_human_control({"action": "pause_llm", "reason": "LLM completed its task."})
                            drone_state.set_human_control_status(True) # Human control implicitly re-activated
                    else:
                        logger.warning("LLM provided no valid action this cycle. Last valid LLM action remains in effect for arbitration.")
                else:
                    # If LLM should be active but no trigger and not following, LLM should do nothing
                    last_llm_proposed_action = {"action": "do_nothing", "reason": "No active trigger, LLM maintaining position."}
                    logger.debug("LLM active but no trigger/follow. Defaulting LLM action to 'do_nothing'.")

                llm_loop_count = 0 
            
            llm_loop_count += 1 

            # 4. Arbitrate command
            final_command = command_arbitrator.arbitrate_command(last_llm_proposed_action)
            
            # 5. Execute command (simplified logic for this new paradigm)
            # If human control is active, human commands are handled directly at the top.
            # If LLM is active, its proposed command is executed.
            if not command_arbitrator._human_control_active: # Only execute LLM commands if human has released
                success = await command_executor.execute_command(final_command)
                if success:
                    drone_state.set_last_executed_command(final_command)
                else:
                    logger.error(f"Command execution failed for: {final_command.get('action')}. Not updating last executed command.")
            else:
                logger.debug(f"Human control active. Skipping LLM command execution: {final_command.get('action')}")

            # Optional: Check for critical battery
            if telemetry_processor.is_battery_critical(CRITICAL_BATTERY_PERCENTAGE):
                battery_percent = processed_telemetry.get("battery", {}).get("remaining_percent", 'N/A')
                logger.warning(f"ALERT: Battery critical ({battery_percent}%). Forcing land.")
                await command_executor.execute_command({"action": "land", "reason": "Emergency: Critical Battery."})
                drone_state.set_last_executed_command({"action": "land", "reason": "Emergency: Critical Battery."})
                # After emergency land, return control to human and stop LLM follow
                command_arbitrator.set_human_control({"action": "pause_llm", "reason": "Emergency landing."})
                drone_state.set_human_control_status(True)
                drone_state.set_llm_following_status(False)
                llm_is_currently_following = False
                llm_should_be_active = False


            await asyncio.sleep(main_loop_interval)

        except KeyboardInterrupt:
            logger.info("Script stopped by user (Ctrl+C).")
            mission_finished = True 
        except Exception as e:
            logger.exception(f"An unexpected error occurred in main loop: {e}")
            mission_finished = True 

    # --- Cleanup ---
    logger.info("Performing final cleanup and disconnecting from drone.")
    # Note: command_executor._offboard_setpoint_task needs to be managed if 'follow_target'
    # involves continuous offboard setpoints. For now, it's not explicitly stopped here.
    # If a continuous offboard stream is started by command_executor, ensure it's stopped.
    # Example: if command_executor._offboard_setpoint_task and not command_executor._offboard_setpoint_task.done():
    #             await command_executor._stop_offboard_setpoint_stream()
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

