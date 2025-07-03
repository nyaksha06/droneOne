import logging

logger = logging.getLogger(__name__)

class CommandArbitrator:
    """
    Arbitrates between LLM-proposed commands and human-issued commands.
    Human commands always take precedence.
    """

    def __init__(self):
        """Initializes the CommandArbitrator."""
        self._human_command = None  # Stores the latest human command
        self._human_control_active = True  # True if human has explicit control, pausing LLM
        logger.info("CommandArbitrator initialized. Human control active by default.")

    def set_human_command(self, command: dict):
        """
        Sets a human-issued command. This command will take precedence.
        :param command: The dictionary representing the human's command.
        """
        self._human_command = command
        self._human_control_active = True # Human command means human control is active
        logger.info(f"Human command received: {command.get('action')}. Human control is now active.")

    def release_human_control(self):
        """
        Releases human control, allowing the LLM to propose commands again.
        """
        self._human_command = None # Clear any pending human command
        self._human_control_active = False
        logger.info("Human control released. LLM can now propose actions.")

    def set_human_control_active(self, is_active: bool): # NEW METHOD
        """
        Explicitly sets the human control active status.
        Used by main_controller to manage LLM pausing/resuming.
        :param is_active: Boolean, True if human control is active, False otherwise.
        """
        if self._human_control_active != is_active:
            self._human_control_active = is_active
            logger.info(f"CommandArbitrator: Human control status set to {is_active}.")
        if is_active:
            self._human_command = None # Clear any old human command if human takes back control

    def arbitrate_command(self, llm_proposed_command: dict) -> dict:
        """
        Decides which command to execute based on human control status.
        :param llm_proposed_command: The command proposed by the LLM.
        :return: The prioritized command (human's if active, else LLM's).
        """
        if self._human_control_active:
            if self._human_command:
                # If human control is active and there's a specific human command, use it
                command_to_execute = self._human_command
                self._human_command = None # Clear human command after it's been picked up
                logger.debug(f"Arbitrating: Executing human command: {command_to_execute.get('action')}")
                return command_to_execute
            else:
                # If human control is active but no specific command, LLM is paused.
                # Return 'do_nothing' to keep drone stable.
                logger.debug("Arbitrating: Human control active, no specific human command. Outputting 'do_nothing'.")
                return {"action": "do_nothing", "reason": "Human control active, awaiting specific command or release."}
        else:
            # Human control is not active, so execute the LLM's proposed command
            logger.debug(f"Arbitrating: Executing LLM proposed command: {llm_proposed_command.get('action')}")
            return llm_proposed_command

    @property
    def human_control_active(self) -> bool:
        """
        Returns the current status of human control.
        """
        return self._human_control_active

