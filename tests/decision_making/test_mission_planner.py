import asyncio
import os
import json
import logging
import sys



sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from config.settings import SITL_SYSTEM_ADDRESS, CRITICAL_BATTERY_PERCENTAGE, OLLAMA_API_URL, OLLAMA_MODEL_NAME
from src.decision_making.mission_panner import LLMMissionPlanner






async def main_ollama_test():
    testcases = [
       " takeoff at 20m  then move 10 in north, then move 10m in east and then land.",
       "takeoff at 10m and inspect reagion in 10m radius."
    ]
    mission_planner = LLMMissionPlanner()
    for t in testcases:
        print(f"Testing Ollama -> {t}:")
        llm_output = await mission_planner.get_mission_plan(t)
        print(json.dumps(llm_output, indent=2))
    
    
    

if __name__ == "__main__":
    asyncio.run(main_ollama_test())