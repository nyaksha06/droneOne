import asyncio
from mavsdk import System
from mavsdk.offboard import PositionNedYaw, VelocityBodyYawspeed, OffboardError,VelocityNedYaw
from mavsdk.telemetry import Health, Position

class DroneController:
    def __init__(self, drone: System):
        self.drone = drone

    # Your existing offboard_takeoff function (no changes needed for this discussion)
    async def offboard_takeoff(self, target_altitude_m: float = 10.0) -> bool:
        # ... (your existing takeoff code) ...
        print(f"--- Starting offboard take-off to {target_altitude_m} meters ---")

        # 1. Check for global position estimate (crucial for position control)
        print("Waiting for drone to have a global position estimate...")
        async for health in self.drone.telemetry.health():
            if health.is_global_position_ok and health.is_home_position_ok:
                print("-- Global position estimate OK")
                break

        # 2. Arm the drone
        print("-- Arming drone")
        try:
            await self.drone.action.arm()
            print("-- Drone armed successfully!")
        except Exception as e:
            print(f"Error arming drone: {e}")
            return False # Indicate failure

        # 3. Set initial setpoint before starting offboard mode
        print("-- Setting initial offboard setpoint (hover)")
        for _ in range(10): # Send multiple setpoints
            await self.drone.offboard.set_velocity_body(VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0))
            await asyncio.sleep(0.005) 
        
        # 4. Start offboard mode
        print("-- Starting offboard mode")
        try:
            await self.drone.offboard.start()
            print("-- Offboard mode started!")
        except OffboardError as error:
            print(f"Error starting offboard mode: {error._result.result}")
            print("-- Disarming drone due to offboard start failure.")
            await self.drone.action.disarm()
            return False 

        # 5. Command take-off to target altitude
        target_down_m = -abs(target_altitude_m) 

        print(f"-- Commanding take-off to altitude: {target_altitude_m}m (NED Down: {target_down_m}m)")
        
        initial_position = None
        async for pos in self.drone.telemetry.position():
            initial_position = pos
            break 

        if initial_position is None:
            print("Error: Could not get initial position for take-off monitoring.")
            await self.drone.offboard.stop()
            await self.drone.action.disarm()
            return False

        altitude_achieved = False
        altitude_tolerance = 0.2
        print("Monitoring altitude for take-off...")
        
        timeout_seconds = 60 
        start_time = asyncio.get_event_loop().time()

        while not altitude_achieved and (asyncio.get_event_loop().time() - start_time) < timeout_seconds:
            await self.drone.offboard.set_position_ned(PositionNedYaw(0.0, 0.0, target_down_m, 0.0))
            
            current_position = await self.drone.telemetry.position().__anext__() 
            current_down_m = current_position.relative_altitude_m
            
            print(f"Current altitude (NED Down): {current_down_m:.2f}m")

            if abs(current_down_m + target_down_m) < altitude_tolerance:
                print(f"-- Reached target altitude of {target_altitude_m}m!")
                altitude_achieved = True
                break

            await asyncio.sleep(0.1) 

        if altitude_achieved:
            print("--- Take-off successful!  ---")
            # self.hold_position_indefinitely()
            return True 
        else:
            print(f"--- Take-off failed: Did not reach target altitude within {timeout_seconds}s. ---")
            # self.hold_position_indefinitely()
            try:
                await self.drone.offboard.stop()
                print("-- Offboard stopped after failed take-off.")
            except OffboardError:
                pass 
            return False

    # Your existing goto function (no changes needed for this discussion)
    async def goto(self, north_m: float, east_m: float, down_m: float, yaw_deg: float = 0.0) -> bool:
        """
        Commands the drone to go to a specific (North, East, Down) position relative to home,
        and optionally sets a yaw angle, using position-velocity commands.
        The drone will attempt to reach the target with zero velocity.
        Returns True on success, False on failure.
        """
        print(f"--- Commanding drone to GOTO N:{north_m:.2f}m, E:{east_m:.2f}m, D:{down_m:.2f}m with Yaw:{yaw_deg:.2f}deg ---")
        
        await self.drone.offboard.set_position_ned(
        PositionNedYaw(
            north_m=north_m,
            east_m=east_m,
            down_m=down_m,
            yaw_deg=0.0
        )
        )

        try:
            await self.drone.offboard.start()
            print(f"-- Moving to (North: {north_m}m, East: {east_m}m, Down: {down_m}m)")
        except OffboardError as error:
            print(f"Offboard start failed: {error._result.result}")
            await self.drone.action.disarm()
            return
        

        target_position = PositionNedYaw(north_m, east_m, down_m, yaw_deg)
        target_velocity = VelocityNedYaw(0.0, 0.0, 0.0, 0.0) 

        position_reached = False
        position_tolerance_xy = 0.5 
        position_tolerance_z = 0.5  
        
        goto_timeout_seconds = 120 
        start_time = asyncio.get_event_loop().time()

        print("Monitoring position until target is reached...")
        # **** IMPORTANT CHANGE HERE: Subscribe to position_velocity_ned() ****
        async for current_telemetry_pv_info in self.drone.telemetry.position_velocity_ned():
            # Exit loop if timeout reached (check only when new telemetry arrives)
            if (asyncio.get_event_loop().time() - start_time) > goto_timeout_seconds:
                print(f"--- GOTO failed: Did not reach target position within {goto_timeout_seconds}s. ---")
                return False # Exit the function, GOTO failed
            
           

            # **** Accessing north_m, east_m, down_m from the nested position object ****
            current_north_m = current_telemetry_pv_info.position.north_m
            current_east_m = current_telemetry_pv_info.position.east_m
            current_down_m = current_telemetry_pv_info.position.down_m 

            distance_xy = ((current_north_m - north_m)**2 + (current_east_m - east_m)**2)**0.5
            distance_z = abs(current_down_m - down_m) 

            print(f"Current Pos (N,E,D): ({current_north_m:.2f}, {current_east_m:.2f}, {current_down_m:.2f})m "
                  f"Dist to target: XY={distance_xy:.2f}m, Z={distance_z:.2f}m")

            if distance_xy < position_tolerance_xy and distance_z < position_tolerance_z:
                print(f"-- Reached target position (N:{north_m}, E:{east_m}, D:{down_m})!")
                position_reached = True
                break

            await asyncio.sleep(0.1) 

        if position_reached:
            print("--- GOTO successful! Drone is at target position. ---")
            return True
        else:
            return False

    # **** MODIFIED HOLD FUNCTION ****
    async def hold_position_indefinitely(self) -> bool:
        """
        Commands the drone to hold its current position indefinitely until a new command is issued.
        The Python function returns immediately after sending the command.
        """
        print("--- Commanding drone to HOLD current position indefinitely ---")
        try:
            # When action.hold() is called, the drone typically exits Offboard mode
            # and enters a high-level position-hold mode (e.g., PX4's 'Position' mode).
            await self.drone.action.hold()
            print("-- Drone commanded to HOLD. It will stay here until a new action/offboard command.")
            return True
        except Exception as e:
            print(f"Error putting drone in HOLD mode: {e}")
            return False

    # Your existing land_drone function (no changes needed for this discussion)
    async def land_drone(self) -> bool:
        # ... (your existing land code) ...
        print("--- Commanding drone to LAND ---")
        try:
            await self.drone.action.land()
            print("-- Landing command sent.")

            print("Waiting for drone to land and disarm...")
            async for is_armed in self.drone.telemetry.armed():
                if is_armed:
                    pass
                else:
                    print("Drone is DISARMED")
                    break
                await asyncio.sleep(1) 
            return True 

        except Exception as e:
            print(f"Error during landing: {e}")
            return False


# Example of how you might use these functions in a main async loop:
async def main():
    drone = System()
    await drone.connect(system_address="udp://:14540") 

    print("Waiting for drone connection...")
    async for state in drone.core.connection_state():
        if state.is_connected:
            print(f"-- Connected to drone!")
            break

    drone_controller = DroneController(drone)

    # 1. Take off to 10 meters
    if not await drone_controller.offboard_takeoff(target_altitude_m=10.0):
        print("Take-off failed. Exiting.")
        return

    # 2. Go to a new position (e.g., 10m North, 5m East, stay at 10m altitude)
    if await drone_controller.goto(north_m=2.0, east_m=0.0, down_m=-10.0, yaw_deg=0.0):
        print("Successfully reached the first GOTO point.")
        
        # 3. Enter indefinite hold mode after the GOTO
        if await drone_controller.hold_position_indefinitely():
            print("Drone is now holding its position. Waiting for manual trigger or another function call...")
            
            
            print("Simulating a 10-second wait in hold mode...")
            await asyncio.sleep(10) # Drone continues to hold here
            print("Simulated wait finished. Proceeding...")

        else:
            print("Failed to command drone to HOLD. Attempting to land.")
            await drone_controller.land_drone()
            return

        # 4. Go to another position after the hold
        if await drone_controller.goto(north_m=0.0, east_m=2.0, down_m=-10.0, yaw_deg=90):
            print("Successfully reached the second GOTO point.")
        else:
            print("Failed to reach the second GOTO point. Attempting to land.")
            await drone_controller.land_drone()
            return

    else:
        print("Failed to reach the first GOTO point. Attempting to land.")
        await drone_controller.land_drone()
        return

    # 5. Land the drone
    print("--- Mission complete. Landing the drone. ---")
    if await drone_controller.land_drone():
        print("Drone safely landed.")
    else:
        print("Landing failed or interrupted.")

    print("Script finished.")

if __name__ == "__main__":
    asyncio.run(main())