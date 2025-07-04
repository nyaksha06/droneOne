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
    logger.info("Type 'takeoff <altitude_m>' to takeoff (e.g., 'takeoff 10').")
    logger.info("Type 'goto <north_m> <east_m> <altitude_m>' to go to a relative position (e.g., 'goto 10 5 10').")
    logger.info("Type 'land' to land the drone.")
    logger.info("Type 'disarm' to disarm the drone.")
    logger.info("Type 'release' to let LLM take control (on trigger).")
    logger.info("Type 'stop_follow' to stop LLM-driven following.")
    logger.info("Type 'simulate_person <N> <E> <D> <vel_N> <vel_E> <vel_D>' to trigger a mock person detection with initial NED position and velocity (e.g., 'simulate_person 20 0 0 0.5 0 0').") # MODIFIED INSTRUCTION
    logger.info("Type 'clear_detection' to clear mock detection.")
    logger.info("Type 'exit' to stop the script.")
    logger.info("---------------------------\n")

    loop = asyncio.get_event_loop()
    while True:
        try:
            user_input = await loop.run_in_executor(None, sys.stdin.readline)
            command_parts = user_input.strip().lower().split()
            action = command_parts[0] if command_parts else ""

            if action == "exit":
                await _human_command_queue.put({"action": "exit"})
                break
            elif action == "land":
                await _human_command_queue.put({"action": "land", "reason": "Human override: manual land."})
            elif action == "disarm":
                await _human_command_queue.put({"action": "disarm", "reason": "Human override: manual disarm."})
            elif action == "release":
                await _human_command_queue.put({"action": "release", "reason": "Human released control."})
            elif action == "stop_follow":
                await _human_command_queue.put({"action": "stop_follow", "reason": "Human stopped LLM follow."})
            elif action == "clear_detection":
                await _human_command_queue.put({"action": "clear_detection", "reason": "Human cleared mock detection."})
            elif action == "takeoff":
                try:
                    altitude_m = float(command_parts[1])
                    await _human_command_queue.put({"action": "takeoff", "parameters": {"altitude_m": altitude_m}, "reason": f"Human commanded takeoff to {altitude_m}m."})
                except (IndexError, ValueError):
                    logger.warning("Invalid 'takeoff' command. Usage: 'takeoff <altitude_m>' (e.g., 'takeoff 10').")
            elif action == "goto":
                try:
                    north_m = float(command_parts[1])
                    east_m = float(command_parts[2])
                    altitude_m = float(command_parts[3])
                    await _human_command_queue.put({"action": "goto_location", "parameters": {"north_m": north_m, "east_m": east_m, "altitude_m": altitude_m}, "reason": f"Human commanded goto N:{north_m} E:{east_m} Alt:{altitude_m}."})
                except (IndexError, ValueError):
                    logger.warning("Invalid 'goto' command. Usage: 'goto <north_m> <east_m> <altitude_m>' (e.g., 'goto 10 5 10').")
            elif action == "simulate_person": # MODIFIED: New parsing for simulate_person
                try:
                    initial_north_m = float(command_parts[1])
                    initial_east_m = float(command_parts[2])
                    initial_down_m = float(command_parts[3])
                    velocity_north_m_s = float(command_parts[4])
                    velocity_east_m_s = float(command_parts[5])
                    velocity_down_m_s = float(command_parts[6])
                    await _human_command_queue.put({
                        "action": "simulate_person",
                        "parameters": {
                            "initial_north_m": initial_north_m,
                            "initial_east_m": initial_east_m,
                            "initial_down_m": initial_down_m,
                            "velocity_north_m_s": velocity_north_m_s,
                            "velocity_east_m_s": velocity_east_m_s,
                            "velocity_down_m_s": velocity_down_m_s
                        },
                        "reason": "Human triggered mock person detection with custom parameters."
                    })
                except (IndexError, ValueError):
                    logger.warning("Invalid 'simulate_person' command. Usage: 'simulate_person <N> <E> <D> <vel_N> <vel_E> <vel_D>' (e.g., 'simulate_person 20 0 0 0.5 0 0').")
            else:
                logger.warning(f"Unknown human command: '{' '.join(command_parts)}'.")
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
    command_arbitrator.set_human_control_active(True) 
    drone_state.set_human_control_status(True) # Inform drone_state

    # Flags to manage trigger and LLM following state
    llm_should_be_active = False # True when human types 'release'
    llm_is_currently_following = False # True when LLM has commanded 'follow_target' and it's active

    while not mission_finished:
        try:
            # --- Handle Human Commands ---
            if not _human_command_queue.empty():
                human_cmd = await _human_command_queue.get()
                action_type = human_cmd["action"]

                if action_type == "exit":
                    logger.info("Exit command received. Shutting down...")
                    mission_finished = True
                    break
                elif action_type in ["land", "disarm", "takeoff", "goto_location"]:
                    await command_executor.execute_command(human_cmd)
                    drone_state.set_last_executed_command(human_cmd)
                    # If human issues a direct flight command, they implicitly take control
                    command_arbitrator.set_human_control_active(True) 
                    drone_state.set_human_control_status(True)
                    llm_should_be_active = False # LLM pauses
                    llm_is_currently_following = False # Stop any LLM follow
                elif action_type == "release":
                    command_arbitrator.release_human_control() # This sets _human_control_active to False internally
                    drone_state.set_human_control_status(False) # Inform drone_state
                    llm_should_be_active = True # Allow LLM to make decisions now
                    logger.info("Human released control. LLM will now be queried if a trigger is active.")
                    llm_loop_count = llm_decision_interval_loops - 1 # Trigger immediate LLM decision
                elif action_type == "stop_follow":
                    command_arbitrator.set_human_control_active(True) # Human takes back control
                    drone_state.set_human_control_status(True) # Inform drone_state
                    drone_state.set_llm_following_status(False) # LLM is no longer following
                    llm_is_currently_following = False
                    llm_should_be_active = False # LLM pauses until new 'release'
                    logger.info("Human stopped LLM-driven follow. Control returned to human.")
                    await command_executor.execute_command({"action": "do_nothing", "reason": "Human stopped follow."})
                    drone_state.set_last_executed_command({"action": "do_nothing", "reason": "Human stopped follow."})
                elif action_type == "simulate_person": # MODIFIED: Handle new parameters
                    params = human_cmd.get("parameters", {})
                    camera_processor.simulate_detection(
                        object_type="person",
                        initial_north_m=params.get("initial_north_m", 0.0),
                        initial_east_m=params.get("initial_east_m", 0.0),
                        initial_down_m=params.get("initial_down_m", 0.0),
                        velocity_north_m_s=params.get("velocity_north_m_s", 0.0),
                        velocity_east_m_s=params.get("velocity_east_m_s", 0.0),
                        velocity_down_m_s=params.get("velocity_down_m_s", 0.0)
                    )
                    logger.info("Simulated person detection triggered with custom parameters.")
                elif action_type == "clear_detection":
                    camera_processor.clear_detections()
                    logger.info("Simulated detection cleared.")
                else:
                    logger.warning(f"Unknown human command: '{human_cmd['action']}'.")

            # 1. Process camera feed (mock for now)
            await camera_processor.process_camera_feed()

            # 2. Get processed data from perception units
            processed_telemetry = await telemetry_processor.get_processed_data() 
            visual_insights = camera_processor.get_visual_insights()

            # 3. Update central drone state
            drone_state.update_telemetry(processed_telemetry)
            drone_state.update_visual_insights(visual_insights)
            drone_state.update_flight_mode(processed_telemetry.get("flight_mode", "UNKNOWN"))
            
            # Update drone_state's internal flags for LLM prompting
            drone_state.set_human_control_status(command_arbitrator.human_control_active) 
            drone_state.set_llm_following_status(llm_is_currently_following)

            # --- LLM Decision Logic ---
            # Query LLM only if LLM should be active AND it's time for a new decision
            # (i.e., human has released control, and either a trigger is active or LLM is already following)
            if llm_should_be_active and \
               llm_loop_count % llm_decision_interval_loops == 0:
                
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
                            command_arbitrator.set_human_control_active(True) # LLM is done, human regains control
                            drone_state.set_human_control_status(True) # Inform drone_state
                    else:
                        logger.warning("LLM provided no valid action this cycle. Last valid LLM action remains in effect for arbitration.")
                else:
                    # If LLM should be active but no trigger and not following, LLM should do nothing
                    last_llm_proposed_action = {"action": "do_nothing", "reason": "No active trigger, LLM maintaining position."}
                    logger.debug("LLM active but no trigger/follow. Defaulting LLM action to 'do_nothing'.")

                llm_loop_count = 0 
            
            llm_loop_count += 1 

            # 4. Arbitrate command - LLM's command is only arbitrated if human control is NOT active
            # If human control is active, human commands are handled directly at the top.
            # If LLM is active, its proposed command is executed.
            if not command_arbitrator.human_control_active: 
                final_command = command_arbitrator.arbitrate_command(last_llm_proposed_action)
                success = await command_executor.execute_command(final_command)
                if success:
                    drone_state.set_last_executed_command(final_command)
                else:
                    logger.error(f"Command execution failed for: {final_command.get('action')}. Not updating last executed command.")
            else:
                logger.debug(f"Human control active. LLM commands are not being executed.")

            # Optional: Check for critical battery
            if telemetry_processor.is_battery_critical(CRITICAL_BATTERY_PERCENTAGE):
                battery_percent = processed_telemetry.get("battery", {}).get("remaining_percent", 'N/A')
                logger.warning(f"ALERT: Battery critical ({battery_percent}%). Forcing land.")
                await command_executor.execute_command({"action": "land", "reason": "Emergency: Critical Battery."})
                drone_state.set_last_executed_command({"action": "land", "reason": "Emergency: Critical Battery."})
                # After emergency land, return control to human and stop LLM follow
                command_arbitrator.set_human_control_active(True) 
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
    if command_executor._offboard_setpoint_task and not command_executor._offboard_setpoint_task.done():
        await command_executor._stop_offboard_setpoint_stream()
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

