import logging
import sys
import random
import asyncio
import time # NEW: For tracking time for movement simulation

logger = logging.getLogger(__name__)

class CameraProcessor:
    """
    Simulates a camera feed and object detection.
    In a real system, this would interface with a camera and CV model.
    """

    def __init__(self):
        """Initializes the CameraProcessor."""
        self._visual_insights = {"detected_objects": []}
        self._simulated_detection_active = False
        self._simulated_detection_data = {}
        self._target_start_time = 0.0 # NEW: To track when simulation started
        self._target_initial_ned = {"north_m": 0.0, "east_m": 0.0, "down_m": 0.0} # NEW: Initial position of target
        self._target_velocity_ned = {"north_m_s": 0.5, "east_m_s": 0.0, "down_m_s": 0.0} # NEW: Target movement velocity
        logger.info("CameraProcessor initialized (mock mode).")

    async def process_camera_feed(self):
        """
        Simulates processing a camera feed.
        If a simulated detection is active, it updates the target's position
        based on a simple linear movement model.
        """
        if self._simulated_detection_active and self._simulated_detection_data:
            # Calculate elapsed time since detection started
            elapsed_time = time.monotonic() - self._target_start_time

            # Calculate current position of the simulated target based on initial position and velocity
            current_north = self._target_initial_ned["north_m"] + (self._target_velocity_ned["north_m_s"] * elapsed_time)
            current_east = self._target_initial_ned["east_m"] + (self._target_velocity_ned["east_m_s"] * elapsed_time)
            current_down = self._target_initial_ned["down_m"] + (self._target_velocity_ned["down_m_s"] * elapsed_time) # Assuming target stays at same ground level for simplicity

            # Update the simulated detection data with the new absolute NED position
            self._simulated_detection_data["absolute_position_ned"] = {
                "north_m": current_north,
                "east_m": current_east,
                "down_m": current_down
            }
            
            # For logging/display, we can still update relative position/distance if needed
            # (though the LLM will primarily use absolute_position_ned for following)
            # For a true relative calculation, you'd need drone's current NED position.
            # For simplicity, we'll keep the initial relative description for the prompt.

            self._visual_insights["detected_objects"] = [self._simulated_detection_data]
            logger.debug(f"Simulating detection: {self._simulated_detection_data['type']} at N:{current_north:.2f}, E:{current_east:.2f}")
        else:
            self._visual_insights["detected_objects"] = []
            logger.debug("No simulated detection active.")

        await asyncio.sleep(0.05) # Simulate some processing time

    def get_visual_insights(self) -> dict:
        """
        Returns the latest processed visual insights.
        """
        return self._visual_insights

    def simulate_detection(self, object_type: str = "person", 
                           initial_north_m: float = 10.0, initial_east_m: float = 0.0, initial_down_m: float = 0.0,
                           velocity_north_m_s: float = 0.5, velocity_east_m_s: float = 0.0, velocity_down_m_s: float = 0.0):
        """
        Manually triggers a simulated object detection with an initial position and velocity.
        The initial position is relative to the drone's home/start point (NED).
        :param object_type: Type of object detected (e.g., "person", "vehicle").
        :param initial_north_m: Initial North position of the target (relative to drone's home/start).
        :param initial_east_m: Initial East position of the target (relative to drone's home/start).
        :param initial_down_m: Initial Down position of the target (relative to drone's home/start).
        :param velocity_north_m_s: North component of target's velocity.
        :param velocity_east_m_s: East component of target's velocity.
        :param velocity_down_m_s: Down component of target's velocity.
        """
        self._target_initial_ned = {
            "north_m": initial_north_m,
            "east_m": initial_east_m,
            "down_m": initial_down_m
        }
        self._target_velocity_ned = {
            "north_m_s": velocity_north_m_s,
            "east_m_s": velocity_east_m_s,
            "down_m_s": velocity_down_m_s
        }
        self._target_start_time = time.monotonic()

        # Initial data for the detected object, including its absolute NED position
        self._simulated_detection_data = {
            "type": object_type,
            "id": f"{object_type}_{random.randint(1000, 9999)}", # Give it a unique ID
            "confidence": random.uniform(0.8, 0.98),
            # This will be updated in process_camera_feed
            "absolute_position_ned": self._target_initial_ned.copy(), 
            # Keep initial relative for prompt, though it will become stale
            "distance_m": (initial_north_m**2 + initial_east_m**2 + initial_down_m**2)**0.5,
            "relative_position": "initial_ahead" # Placeholder, will be dynamic in real system
        }
        self._simulated_detection_active = True
        logger.info(f"Simulating detection of {object_type} at initial NED: N={initial_north_m}, E={initial_east_m}, D={initial_down_m} with velocity N:{velocity_north_m_s}, E:{velocity_east_m_s}.")

    def clear_detections(self):
        """
        Clears any active simulated object detections.
        """
        self._simulated_detection_active = False
        self._simulated_detection_data = {}
        self._visual_insights["detected_objects"] = []
        self._target_start_time = 0.0
        self._target_initial_ned = {"north_m": 0.0, "east_m": 0.0, "down_m": 0.0}
        self._target_velocity_ned = {"north_m_s": 0.0, "east_m_s": 0.0, "down_m_s": 0.0}
        logger.info("Cleared all simulated detections.")

