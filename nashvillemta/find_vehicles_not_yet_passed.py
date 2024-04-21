import pandas as pd

# Load the stops and vehicles data
df_nearest_stops = pd.read_csv('temp_gtfs/nearest_stops.csv')
df_vehicles = pd.read_csv('temp_gtfs/route_vehicles.csv')

#for some reason the route_vehicles.csv has different direction_ids than the static data.
# it looks like 16 corresponds with 1 and 13 corresponds with 0. 
# for now recode these values
df_vehicles['direction_id'] = df_vehicles['direction_id'].replace({16: 1, 13: 0})
print(df_vehicles)

# Merge the vehicle data with the stops data based on route_id and direction_id
vehicles_with_nearest_stops = pd.merge(df_vehicles, df_nearest_stops, on=['route_id', 'direction_id'])

print(vehicles_with_nearest_stops)

# Function to determine if a vehicle has passed a stop
def has_passed_stop(vehicle_lat, vehicle_lon, stop_lat, stop_lon, vehicle_direction):
    # Implementing a simple logic based on latitude and longitude:
    # This needs adjustment according to the specific orientation and route direction.
    # This example assumes a simple North-South/East-West orientation for simplicity.
    if vehicle_direction in [1, 16]:  # Assuming 1 means North or East bound (to downtown)
        return vehicle_lat > stop_lat or vehicle_lon > stop_lon
    elif vehicle_direction in [0, 13]:  # Assuming 0 means South or West bound (from downtown)
        return vehicle_lat < stop_lat or vehicle_lon < stop_lon

# Apply the function to determine if vehicles have passed their nearest stop
vehicles_with_nearest_stops['has_passed'] = vehicles_with_nearest_stops.apply(lambda row: has_passed_stop(
    row['latitude'], row['longitude'],
    row['stop_lat'], row['stop_lon'],
    row['direction_id']
), axis=1)

print(vehicles_with_nearest_stops)

# Save the data to a CSV file
vehicles_with_nearest_stops.sort_values(['route_id', 'direction_id']).to_csv('temp_gtfs/vehicles_with_nearest_stops.csv', index=False)

# Filter out vehicles that have already passed the stop
#vehicles_not_passed = vehicles_with_nearest_stops[vehicles_with_nearest_stops['has_passed'] == False]
