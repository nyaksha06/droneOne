import logging
import asyncio

logger = logging.getLogger(__name__)

class CommandArbitrator:
    """
    Arbitrates between LLM-generated autonomous commands and human-issued manual commands.
    Human commands always take precedence.
    """

    def __init__(self):
        self._human_control_active = False
        self._last_human_command = None
        logger.info("CommandArbitrator initialized.")

    def set_human_command(self, command: dict):
        """
        Sets a human-issued command and activates human control.
        :param command: A structured dictionary representing the human command.
        """
        if command:
            self._last_human_command = command
            self._human_control_active = True
            logger.info(f"Human command received: {command['action']}. Human control activated.")
        else:
            self.release_human_control()

    def release_human_control(self):
        """
        Deactivates human control and clears the last human command.
        """
        if self._human_control_active:
            logger.info("Human control released. LLM can resume control.")
            self._human_control_active = False
            self._last_human_command = None

    def arbitrate_command(self, llm_command: dict) -> dict:
        """
        Decides which command to execute based on arbitration logic.
        :param llm_command: The structured command recommended by the LLM.
        :return: The prioritized command (human if active, else LLM).
        """
        if self._human_control_active and self._last_human_command:
            logger.debug(f"Arbitrator: Prioritizing human command: {self._last_human_command.get('action')}")
            return self._last_human_command
        else:
            logger.debug(f"Arbitrator: Using LLM command: {llm_command.get('action')}")
            return llm_command

