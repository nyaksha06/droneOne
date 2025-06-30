import asyncio
from mavsdk import System

async def inspect_telemetry_object():
    drone = System()
    # Connect to drone (replace with your actual connection string)
    await drone.connect(system_address="udp://:14540")

    # Wait for connection
    print("Waiting for drone to connect...")
    async for state in drone.core.connection_state():
        if state.is_connected:
            print(f"-- Connected to drone!")
            break

    # Get the telemetry object
    telemetry_obj = drone.telemetry

    print("\n--- Attributes and methods of the Telemetry object ---")
    for attr in dir(telemetry_obj):
        # Filter out private/internal attributes (starting with __) unless you need them
        if not attr.startswith('__'):
            print(attr)

    print("\n--- Specifically checking for 'position_ned' and 'altitude' ---")
    if hasattr(telemetry_obj, 'position_ned'):
        print("Telemetry object has 'position_ned' attribute.")
    else:
        print("Telemetry object DOES NOT have 'position_ned' attribute.")

    if hasattr(telemetry_obj, 'position'):
        print("Telemetry object has 'position' attribute.")
    else:
        print("Telemetry object DOES NOT have 'position' attribute.")

    if hasattr(telemetry_obj, 'altitude'):
        print("Telemetry object has 'altitude' attribute.")
    else:
        print("Telemetry object DOES NOT have 'altitude' attribute.")

    # If it has 'altitude', let's try to get one sample and inspect it
    if hasattr(telemetry_obj, 'altitude'):
        print("\n--- Inspecting a sample Altitude object ---")
        try:
            # Use a small timeout just in case it never yields
            async for alt_info in telemetry_obj.altitude():
                print(f"Sample Altitude object received: {alt_info}")
                print(f"Attributes of the Altitude object:")
                for attr in dir(alt_info):
                    if not attr.startswith('__'):
                        value = getattr(alt_info, attr)
                        print(f"  {attr}: {value}")
                break # Get only one sample
        except Exception as e:
            print(f"Could not get sample Altitude info: {e}")

    # You can do the same for 'position' if it exists and you want to see its fields
    if hasattr(telemetry_obj, 'position'):
        print("\n--- Inspecting a sample Position object ---")
        try:
            async for pos_info in telemetry_obj.position():
                print(f"Sample Position object received: {pos_info}")
                print(f"Attributes of the Position object:")
                for attr in dir(pos_info):
                    if not attr.startswith('__'):
                        value = getattr(pos_info, attr)
                        print(f"  {attr}: {value}")
                break # Get only one sample
        except Exception as e:
            print(f"Could not get sample Position info: {e}")



    if hasattr(telemetry_obj, 'position_velocity_ned'):
        print("\n--- Inspecting a sample position_velocity_ned object ---")
        try:
            async for pos_info in telemetry_obj.position():
                print(f"Sample position_velocity_ned object received: {pos_info}")
                print(f"Attributes of the position_velocity_ned object:")
                for attr in dir(pos_info):
                    if not attr.startswith('__'):
                        value = getattr(pos_info, attr)
                        print(f"  {attr}: {value}")
                break # Get only one sample
        except Exception as e:
            print(f"Could not get sample position_velocity_ned info: {e}")
   
    # Disconnect (optional, but good practice)
    await drone.action.disarm() # Disarm before disconnecting if armed
    # MAVSDK will often clean up connections automatically when the script ends

if __name__ == "__main__":
    asyncio.run(inspect_telemetry_object())