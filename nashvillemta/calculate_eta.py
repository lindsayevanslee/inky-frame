import googlemaps
from datetime import datetime
import pandas as pd
from datetime import datetime
from my_secrets import google_api_directions_key, my_routes #objects with my secret info

# Authenticate Google Maps API with key (restricted to Directions API)
gmaps = googlemaps.Client(key=google_api_directions_key)

# Load the vehicle data
df_vehicles = pd.read_csv('temp_gtfs/vehicles_with_nearest_stops.csv', dtype={'route_id': str, 'trip_id': str})

#read in stop data
df_stops = pd.read_csv('temp_gtfs/stops.txt')

#read in stop_times data
df_stop_times = pd.read_csv('temp_gtfs/stop_times.txt', dtype={'trip_id': str})

def calculate_eta_transit(origin, destination, trip_id, gmaps_client):
    now = datetime.now()
    try:
        directions_result = gmaps_client.directions(origin,
                                                    destination,
                                                    mode="transit",
                                                    transit_mode="bus",
                                                    departure_time=now,
                                                    transit_routing_preference='fewer_transfers')
        
        #print(directions_result)

        # Check if the API call returned results
        if directions_result and 'legs' in directions_result[0]:

            #initialize bus_duration
            bus_duration = 0

            #pull out steps from directions_result
            steps = directions_result[0]['legs'][0]['steps']

            #if there is only one step and travel mode is walking, assume bus is 1 minute away
            if len(steps) == 1 and steps[0]['travel_mode'] == 'WALKING':
                bus_duration = 60 
            #otherwise: 
            else:
                for step in steps:

                    #if step is a bus, add the duration to the total
                    if step['travel_mode'] == 'TRANSIT' and step['transit_details']['line']['vehicle']['type'] == 'BUS':
                        bus_duration += step['duration']['value']  # duration in seconds
                    
                    #if step is a walking step, recalculate the duration assuming person is already on the bus
                    #this will be recalculated by finding the relative position of the origin between the previous and next bus stops
                    #currently this assumes that the walking step goes in the same direction as the bus, meaning the walking doesn't
                    #backtrack to find the closest stop
                    elif step['travel_mode'] == 'WALKING':

                        #find all stops on this trip
                        trip_all_stops = df_stop_times[df_stop_times['trip_id'] == trip_id]

                        #next bus stop in the direction of travel - end point of WALKING step
                        next_stop_location = (step['end_location']['lat'], step['end_location']['lng'])
                        next_stop_name = step['html_instructions'].replace('Walk to ', '').upper()
                        next_stop_id = df_stops[df_stops['stop_name'] == next_stop_name]['stop_id'].values[0]

                        #find number of stop in the stop sequence for this trip
                        next_stop_sequence = trip_all_stops[trip_all_stops['stop_id'] == next_stop_id]['stop_sequence'].values[0]

                        # filter list of all trip stops to next stop and the previous stop
                        next_previous_stop_times = trip_all_stops[trip_all_stops['stop_sequence'].between(next_stop_sequence - 1, next_stop_sequence)]
                        print(next_previous_stop_times)

                        #pull distance from walking step in meters and convert to miles
                        step_distance = step['distance']['value'] * 0.000621371

                        #find distance between two stops in next_previous_stop_times
                        # find shape_dist_traveled for the next stop and the previous stop
                        next_stop_shape_dist_traveled = next_previous_stop_times[next_previous_stop_times['stop_sequence'] == next_stop_sequence]['shape_dist_traveled'].values[0]
                        previous_stop_shape_dist_traveled = next_previous_stop_times[next_previous_stop_times['stop_sequence'] == next_stop_sequence - 1]['shape_dist_traveled'].values[0]

                        total_distance = next_stop_shape_dist_traveled - previous_stop_shape_dist_traveled
                        print(f"Total distance (mi): {total_distance}")
                        

                        #find the relative position of the origin between the previous and next bus stops
                        origin_rel_pos = (total_distance - step_distance) / total_distance
                        print(f"Relative position of origin (%): {origin_rel_pos}")

                        #find time between two stops in next_previous_stop_times
                        # find arrival_time for the next stop and the previous stop
                        next_stop_arrival_time = next_previous_stop_times[next_previous_stop_times['stop_sequence'] == next_stop_sequence]['arrival_time'].values[0]
                        previous_stop_arrival_time = next_previous_stop_times[next_previous_stop_times['stop_sequence'] == next_stop_sequence - 1]['arrival_time'].values[0]

                        next_stop_arrival_time = datetime.strptime(next_stop_arrival_time, "%H:%M:%S").time()
                        previous_stop_arrival_time = datetime.strptime(previous_stop_arrival_time, "%H:%M:%S").time()

                        total_time = (datetime.combine(datetime.today(), next_stop_arrival_time) - datetime.combine(datetime.today(), previous_stop_arrival_time)).total_seconds()
                        print(f"Total time (s): {total_time}")

                        origin_rel_time_remaining = total_time * (1 - origin_rel_pos)
                        print(f"Remaining time from origin to next stop (s): {origin_rel_time_remaining}")

                        #add to bus_duration
                        bus_duration += origin_rel_time_remaining

            return bus_duration / 60  # convert to minutes
        

    except Exception as e:
        print(f"An error occurred: {e}")
    return None

"""
# Example usage with mock data
origin = (36.102149963378906,-86.87020874023438)  # Example coordinates of bus
destination = (36.153658,-86.794441)  # Example coordinates nearby stop
trip_id = '311576'
eta = calculate_eta_transit(origin, destination, trip_id, gmaps)
print(f"Estimated time in minutes: {eta}")
"""



# Calculate ETA for each vehicle
df_vehicles['eta_minutes'] = df_vehicles.apply(lambda row: calculate_eta_transit(
    (row['latitude'], row['longitude']),  # origin from vehicle position
    (row['stop_lat'], row['stop_lon']),  # destination from stop position
    row['trip_id'],  # trip_id to identify the route
    gmaps), axis=1)

# Print the vehicles that have not yet passed with calculated ETA
df_vehicles = df_vehicles.loc[~df_vehicles.has_passed][['route_id', 'direction_id', 'trip_id', 'vehicle_id', 'eta_minutes']].sort_values(['route_id', 'direction_id'])
print(df_vehicles)

#read in vehicle metadata
vehicle_metadata = pd.read_csv('temp_gtfs/merged_data.csv', dtype={'route_id': str, 'trip_id': str})[['route_id', 'direction_id', 'trip_id', 'trip_headsign', 'route_color', 'route_text_color']]

#print rows of vehicle_metadata on my route
print(vehicle_metadata.loc[vehicle_metadata['route_id'].isin(my_routes)])

# Merge the vehicle data with the metadata
vehicles_to_display = pd.merge(df_vehicles, vehicle_metadata, how='left', on=['route_id', 'direction_id', 'trip_id'])
print(vehicles_to_display)

# Save the data to a CSV file
vehicles_to_display.to_csv('temp_gtfs/vehicles_to_display.csv', index=False)