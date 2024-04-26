import pandas as pd
from PIL import Image, ImageDraw, ImageFont

## setup -------------------------

# Path to the CSV file
csv_file = 'temp_gtfs/vehicles_to_display.csv'

# Path to the output image
output_image = 'departure_board.png'

# Font settings
font_size = 20
font_color = (0, 0, 0)  # White
font_path = 'Roboto-Regular.ttf'

# Image settings
image_width = 800
image_height = 480
anchor_x = 10
anchor_y = 10
line_height = font_size + 5

## read data -------------------------

# Load the CSV file into a DataFrame
df = pd.read_csv(csv_file)

## wrangle data -------------------------

# Sort the DataFrame by ETA
df_wrangled = df.sort_values(['eta_minutes'])

#remap values of direction_id
df_wrangled['direction_id'] = df_wrangled['direction_id'].replace({1: 'To Downtown', 0: 'From Downtown'})

#add column to df_wrangled converting eta_minutes to string of minutes and seconds
df_wrangled['eta_minutes_str'] = df_wrangled['eta_minutes'].apply(lambda x: f"{int(x)}m {int((x % 1) * 60)}s")

print(df_wrangled)


## create image -------------------------

# Create a blank image
image = Image.new('RGB', (image_width, image_height), color = 'white')
draw = ImageDraw.Draw(image)

# Set the font
font = ImageFont.truetype(font_path, font_size)

# Loop through the DataFrame and draw the trip information
for index, row in df_wrangled.iterrows():
    # Get the route color and text color
    route_color = '#' + row['route_color']
    route_text_color = '#' + row['route_text_color']
    
    # Draw the oval with route color
    oval_height = font_size
    oval_width = oval_height * 2
    oval_x = anchor_x
    oval_y = anchor_y
    draw.ellipse([(oval_x, oval_y), (oval_x + oval_width, oval_y + oval_height)], fill=route_color)
    
    # add route number in the center of the oval
    text_x = oval_x + (oval_width - font_size) / 2
    text_y = oval_y + (oval_height - font_size) / 2
    draw.text((text_x, text_y), f"{row['route_id']}", font=font, fill=route_text_color)
    
    # Draw the text with route id
    draw.text((anchor_x + oval_width + 5, anchor_y), f"{row['trip_headsign']} - {row['eta_minutes_str']}", font=font, fill=font_color)
    
    anchor_y += line_height

## print -------------------------

# Save the image
image.save(output_image)