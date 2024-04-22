import googlemaps
from datetime import datetime
import pandas as pd
from my_secrets import google_api_directions_key #objects with my secret info

# Authenticate Google Maps API with key (restricted to Directions API)
gmaps = googlemaps.Client(key=google_api_directions_key)

# Load the vehicle data
df_vehicles = pd.read_csv('temp_gtfs/vehicles_with_nearest_stops.csv')

def calculate_eta_transit(origin, destination, gmaps_client):
    now = datetime.now()
    try:
        directions_result = gmaps_client.directions(origin,
                                                    destination,
                                                    mode="transit",
                                                    transit_mode="bus",
                                                    departure_time=now,
                                                    transit_routing_preference='fewer_transfers')
        # Check if the API call returned results
        if directions_result and 'legs' in directions_result[0]:
            duration = directions_result[0]['legs'][0]['duration']['value']  # duration in seconds
            return duration / 60  # convert to minutes
    except Exception as e:
        print(f"An error occurred: {e}")
    return None

"""
# Example usage with mock data
origin = (36.1627, -86.7816)  # Example coordinates (Nashville, TN)
destination = (36.165, -86.776)  # Example coordinates nearby
eta = calculate_eta_transit(origin, destination, gmaps)
print(f"Estimated time in minutes: {eta}")
"""


# Calculate ETA for each vehicle
df_vehicles['eta_minutes'] = df_vehicles.apply(lambda row: calculate_eta_transit(
    (row['latitude'], row['longitude']),  # origin from vehicle position
    (row['stop_lat'], row['stop_lon']),  # destination from stop position
    gmaps), axis=1)

# Print the vehicles that have not yet passed with calculated ETA
df_vehicles = df_vehicles.loc[~df_vehicles.has_passed][['route_id', 'direction_id', 'trip_id', 'vehicle_id', 'eta_minutes']].sort_values(['route_id', 'direction_id'])
print(df_vehicles)

