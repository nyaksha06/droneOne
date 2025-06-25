import asyncio
import logging
import sys
import random

logger = logging.getLogger(__name__)

class CameraProcessor:
    """
    Simulates processing of camera input for object detection.
    For SITL, this will provide mock data. In a real scenario, this would
    integrate with OpenCV and an object detection model.
    """

    def __init__(self):
        """Initializes the CameraProcessor with mock data capabilities."""
        self._mock_object_counter = 0
        self._current_visual_insights = {}
        logger.info("CameraProcessor (Mock) initialized.")

    async def process_camera_feed(self):
        """
        Simulates processing a camera feed to detect objects.
        For now, this generates random mock objects over time.
        In a real scenario, this would involve frame capture and ML inference.
        """
        # Simulate detection of objects periodically
        self._mock_object_counter += 1
        
        # Every 10 "frames" (or calls), simulate detecting a new object
        if self._mock_object_counter % 2 == 0:
            object_type = random.choice(["landing_pad", "obstacle", "person", "target_marker"])
            distance = round(random.uniform(2.0, 30.0), 1) # 2m to 30m
            relative_position = random.choice(["ahead_center", "ahead_left", "ahead_right", "below"])
            
            # Simple logic to sometimes make the landing pad appear
            if random.random() < 0.2: # 20% chance of landing pad
                object_type = "landing_pad"
                distance = round(random.uniform(1.0, 10.0), 1)
                relative_position = "below"
            
            detected_object = {
                "type": object_type,
                "distance_m": distance,
                "relative_position": relative_position,
                "confidence": round(random.uniform(0.7, 0.95), 2)
            }
            self._current_visual_insights = {"detected_objects": [detected_object]}
            logger.info(f"Mock Camera: Detected {object_type} at {distance}m {relative_position}")
        else:
            # Most of the time, no new object or same old object (clearing it after a while)
            if random.random() < 0.9: # 90% chance to clear previous detection
                self._current_visual_insights = {"detected_objects": []}

        # In a real system, this function would return insights immediately after processing a frame.
        # For this mock, we update an internal variable that `get_visual_insights` reads.
        await asyncio.sleep(0.1) # Simulate some processing time


    def get_visual_insights(self) -> dict:
        """
        Returns the latest processed visual insights from the camera.
        """
        return self._current_visual_insights

