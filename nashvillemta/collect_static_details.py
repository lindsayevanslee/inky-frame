import pandas as pd
import requests
import zipfile
import io

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
    else:
        print(f"Failed to download the GTFS zip file. Status code: {response.status_code}")

def load_and_process_gtfs_files():
    # Load the extracted trips and routes data
    trips_df = pd.read_csv('temp_gtfs/trips.txt')
    routes_df = pd.read_csv('temp_gtfs/routes.txt')

    # Merge trips with routes to get comprehensive route information
    merged_df = pd.merge(trips_df, routes_df, on='route_id', how='left')

    # Inspect the dataframe to understand direction_id usage
    print(merged_df[['route_id', 'route_short_name', 'route_long_name', 'route_color', 'route_text_color', 'direction_id', 'trip_headsign']].drop_duplicates())

    # Print csv of merged data
    merged_df.to_csv('temp_gtfs/merged_data.csv', index=False)

# Replace 'URL_OF_YOUR_GTFS_ZIP_FILE' with the actual GTFS zip file URL
download_and_extract_gtfs_files(gtfs_zip_url)
load_and_process_gtfs_files()
