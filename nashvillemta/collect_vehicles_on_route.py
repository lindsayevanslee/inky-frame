import requests
from google.transit import gtfs_realtime_pb2
import pandas as pd
from my_secrets import my_routes #objects with my secret info

#navigate to the nashvillemta directory: cd nashvillemta

# Replace this with your actual GTFS Realtime feed URL for vehicle positions
feed_url = 'http://transitdata.nashvillemta.org/TMGTFSRealTimeWebService/vehicle/vehiclepositions.pb'

def fetch_vehicles_by_route(url, target_route_ids):
    # Initialize the GTFS Realtime FeedMessage
    feed = gtfs_realtime_pb2.FeedMessage()
    
    # Fetch the data from the URL
    response = requests.get(url)
    
    # Parse the feed data
    feed.ParseFromString(response.content)
    
    # List to hold matching vehicles
    vehicles_on_route = []
    
    # Loop through each entity in the feed
    for entity in feed.entity:
        # Check if the entity has vehicle data and the trip data includes a route_id
        if entity.HasField('vehicle') and entity.vehicle.trip.route_id in target_route_ids:
            vehicle_info = {
                'route_id' : entity.vehicle.trip.route_id,
                'direction_id': entity.vehicle.trip.direction_id,
                'vehicle_id': entity.vehicle.vehicle.id,
                'latitude': entity.vehicle.position.latitude,
                'longitude': entity.vehicle.position.longitude,
                'timestamp': entity.vehicle.timestamp,
                'current_status': entity.vehicle.current_status,
                'congestion_level': entity.vehicle.congestion_level,
            }
            vehicles_on_route.append(vehicle_info)
    
    return vehicles_on_route

# Fetch and print vehicle info for vehicles on my routes
route_vehicles = fetch_vehicles_by_route(feed_url, my_routes)

#convert route_vehicles to data frame and print to csv
df = pd.DataFrame(route_vehicles)
print(df)
df.to_csv('temp_gtfs/route_vehicles.csv')

for vehicle in route_vehicles:
    print(vehicle)
