import pandas as pd
import requests
import zipfile
import io
from scipy.spatial import KDTree
from my_secrets import my_routes, my_lat, my_long #objects with my secret info

#navigate to the nashvillemta directory: cd nashvillemta

# URL of the GTFS zip file
gtfs_zip_url = 'http://www.nashvillemta.org/GoogleExport/google_transit.zip'

def download_and_extract_gtfs_files(url):
    # Send a GET request to the GTFS zip file URL
    response = requests.get(url)
    # Check if the request was successful
    if response.status_code == 200:
        # Use BytesIO for in-memory bytes buffer (the downloaded zip file)
        zip_file_bytes = io.BytesIO(response.content)
        # Use zipfile to open the zip file
        with zipfile.ZipFile(zip_file_bytes) as zfile:
            # Extract trips.txt and routes.txt
            zfile.extract('trips.txt', 'temp_gtfs')
            zfile.extract('routes.txt', 'temp_gtfs')
            zfile.extract('stops.txt', 'temp_gtfs')
            zfile.extract('stop_times.txt', 'temp_gtfs')
    else:
        print(f"Failed to download the GTFS zip file. Status code: {response.status_code}")

def load_and_process_route_files():
    # Load the extracted trips and routes data
    trips_df = pd.read_csv('temp_gtfs/trips.txt')
    routes_df = pd.read_csv('temp_gtfs/routes.txt')

    # Merge trips with routes to get comprehensive route information
    merged_df = pd.merge(trips_df, routes_df, on='route_id', how='left')

    # Inspect the dataframe to understand direction_id usage
    print(merged_df[['route_id', 'route_short_name', 'route_long_name', 'route_color', 'route_text_color', 'direction_id', 'trip_headsign']].drop_duplicates())

    # Print csv of merged data
    merged_df.to_csv('temp_gtfs/merged_data.csv', index=False)

def find_nearest_stops():
    # Load GTFS data
    stops_df = pd.read_csv('temp_gtfs/stops.txt')
    trips_df = pd.read_csv('temp_gtfs/trips.txt', dtype={'route_id': str})
    stop_times_df = pd.read_csv('temp_gtfs/stop_times.txt')

    #print(trips_df.head())

    #initialze dictionary of all nearest stops
    list_nearest_stops = []

    #loop through routes in my_routes
    for this_route in my_routes:

        #loop through directions
        for this_direction in [0, 1]:

            # Filter trips by route and direction
            trips_filtered = trips_df[(trips_df['route_id'] == this_route) & (trips_df['direction_id'] == this_direction)]
            #print(trips_filtered)

            # Get stop times for filtered trips
            stop_times_filtered = stop_times_df[stop_times_df['trip_id'].isin(trips_filtered['trip_id'])]
            #print(stop_times_filtered)

            # Get unique stops for these trips
            stops_filtered = stops_df[stops_df['stop_id'].isin(stop_times_filtered['stop_id'])]
            #print(stops_filtered)

            # Create a KDTree for efficient spatial search
            stops_kdtree = KDTree(stops_filtered[['stop_lat', 'stop_lon']].values)

            # Find the nearest stop to your house
            _, nearest_stop_idx = stops_kdtree.query([my_lat, my_long], k=1)
            nearest_stop = stops_filtered.iloc[nearest_stop_idx]
            
            print(f"Nearest Stop for Route {this_route} Direction {this_direction}: {nearest_stop['stop_name']} (ID: {nearest_stop['stop_id']})")

            #convert neraest_stop to dictionary format
            nearest_stop = nearest_stop.to_dict()
            #print(nearest_stop)

            #add columns for this_route and this_direction
            nearest_stop['route_id'] = this_route
            nearest_stop['direction_id'] = this_direction
            #print(nearest_stop)

            #add nearest_stop to list_nearest_stops
            list_nearest_stops.append(nearest_stop)

   
    print(list_nearest_stops)

    #convert list_nearest_stops to a dataframe
    df_nearest_stops = pd.DataFrame(list_nearest_stops)
    print(df_nearest_stops)

    #save df_nearest_stops to a csv file
    df_nearest_stops.to_csv(f'temp_gtfs/nearest_stops.csv', index=False)


download_and_extract_gtfs_files(gtfs_zip_url)
load_and_process_route_files()
find_nearest_stops()
