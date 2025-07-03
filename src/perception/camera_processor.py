import logging
import sys
import random
import asyncio

logger = logging.getLogger(__name__)

class CameraProcessor:
    """
    Simulates a camera feed and object detection.
    In a real system, this would interface with a camera and CV model.
    """

    def __init__(self):
        """Initializes the CameraProcessor."""
        self._visual_insights = {"detected_objects": []}
        self._simulated_detection_active = False # NEW: Flag to control simulation
        self._simulated_detection_data = {} # NEW: Store specific detection data
        logger.info("CameraProcessor initialized (mock mode).")

    async def process_camera_feed(self):
        """
        Simulates processing a camera feed.
        In this mock, it updates visual insights based on internal flags.
        """
        # In a real system, this would involve:
        # 1. Capturing a frame from the camera.
        # 2. Running a computer vision model (e.g., YOLO) on the frame.
        # 3. Extracting detected objects and their properties.

        # For the mock, we simply return the current simulated detection state
        # as set by simulate_detection() or clear_detections().
        
        # If a simulated detection is active, ensure it's in the insights
        if self._simulated_detection_active and self._simulated_detection_data:
            self._visual_insights["detected_objects"] = [self._simulated_detection_data]
            logger.debug(f"Simulating detection: {self._simulated_detection_data['type']}")
        else:
            self._visual_insights["detected_objects"] = []
            logger.debug("No simulated detection active.")

        # Simulate some processing time
        await asyncio.sleep(0.05) 

    def get_visual_insights(self) -> dict:
        """
        Returns the latest processed visual insights.
        """
        return self._visual_insights

    def simulate_detection(self, object_type: str = "person", distance_m: float = 15.0, relative_position: str = "ahead_center"):
        """
        NEW: Manually triggers a simulated object detection.
        :param object_type: Type of object detected (e.g., "person", "vehicle", "critical_anomaly").
        :param distance_m: Simulated distance to the object in meters.
        :param relative_position: Relative position (e.g., "ahead_left", "behind_right").
        """
        self._simulated_detection_data = {
            "type": object_type,
            "distance_m": distance_m,
            "relative_position": relative_position,
            "confidence": random.uniform(0.7, 0.95)
        }
        self._simulated_detection_active = True
        logger.info(f"Simulating detection: {object_type} at {distance_m}m {relative_position}")

    def clear_detections(self):
        """
        NEW: Clears any active simulated object detections.
        """
        self._simulated_detection_active = False
        self._simulated_detection_data = {}
        self._visual_insights["detected_objects"] = []
        logger.info("Cleared all simulated detections.")

