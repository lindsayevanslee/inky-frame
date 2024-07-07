import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

## setup -------------------------

# Path to the CSV file
csv_file = 'temp_gtfs/vehicles_to_display.csv'

# Path to the output image
output_image = 'departure_board.png'

# Font settings
font_size = 40
font_size_title = 60
font_color = 'black'
font_path = 'Roboto-Regular.ttf'

# Image settings
image_width = 800
image_height = 480
anchor_x = 10
anchor_y = 200
#line_height = font_size + 5
anchor_y_title = 10

title = "Bus Departures Near Me"

## read data -------------------------

# Load the CSV file into a DataFrame
df = pd.read_csv(csv_file)

## wrangle data -------------------------

# Sort the DataFrame by ETA
df_wrangled = df.sort_values(['eta_minutes'])

#remap values of direction_id
df_wrangled['direction_id'] = df_wrangled['direction_id'].replace({1: 'To Downtown', 0: 'From Downtown'})

#add column to df_wrangled converting eta_minutes to string of minutes and seconds
#df_wrangled['eta_minutes_str'] = df_wrangled['eta_minutes'].apply(lambda x: f"{int(x)}m {int((x % 1) * 60)}s")

#add column to df_wrangled converting eta_minutes to string of minutes and seconds or "error" if not possible to convert
df_wrangled['eta_minutes_str'] = df_wrangled['eta_minutes'].apply(lambda x: f"{int(x)}m {int((x % 1) * 60)}s" if not pd.isnull(x) else "error")

print(df_wrangled)

#print number of rows in df_wrangled
print(df_wrangled.shape[0])

#current time
now = datetime.now()
current_datetime = now.strftime("%Y-%m-%d %H:%M:%S")
print("Current Time =", current_datetime)

## create image -------------------------

# Create a blank image
image = Image.new('RGB', (image_width, image_height), color = 'white')
draw = ImageDraw.Draw(image)

#update font size if there are more than 6 rows
if df_wrangled.shape[0] > 6:
    font_size = font_size * (5.5/df_wrangled.shape[0])

#set line height based on font size
line_height = font_size + 5

# Set the font
font = ImageFont.truetype(font_path, font_size)
font_title = ImageFont.truetype(font_path, size=font_size_title)
font_subtitle = ImageFont.truetype(font_path, size=font_size_title * (2/3))


# Draw the title
draw.text((anchor_x, anchor_y_title), title, font=font_title, fill=font_color)

# Draw the subtitle
draw.text((anchor_x, anchor_y_title + font_size_title + 5), current_datetime, font=font_subtitle, fill=font_color)

# Loop through the DataFrame and draw the trip information
for index, row in df_wrangled.iterrows():

    # Get the route color and text color
    route_color = '#' + row['route_color']
    route_text_color = '#' + row['route_text_color']
    
    shape_width_to_height_ratio = 1.5

    """
    # Draw the oval with route color
    oval_height = font_size
    oval_width = oval_height * shape_width_to_height_ratio
    oval_x = anchor_x
    oval_y = anchor_y
    #draw.ellipse([(oval_x, oval_y), (oval_x + oval_width, oval_y + oval_height)], fill=route_color)
    
    """

    # Draw a rounded rectangle with route color
    corner_radius = 10  # adjust as needed
    rectangle_x1 = anchor_x
    rectangle_y1 = anchor_y
    rectangle_x2 = anchor_x + font_size * shape_width_to_height_ratio
    rectangle_y2 = anchor_y + font_size
    draw.rounded_rectangle([(rectangle_x1, rectangle_y1), (rectangle_x2, rectangle_y2)], fill=route_color, radius=corner_radius)


    # Get the bounding box of the text
    bbox = draw.textbbox((0, 0), f"{row['route_id']}", font=font)

    # Calculate the width and height of the text
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    #print(f"Text width: {text_width}, Text height: {text_height}")

    # Calculate the new x and y coordinates for text
    text_x = anchor_x + (font_size * shape_width_to_height_ratio - text_width) / 2
    #text_y = anchor_y + (font_size - text_height) / 2

    #text_x = anchor_x + (font_size * shape_width_to_height_ratio - font_size) / 2
    text_y = anchor_y + (font_size - font_size) / 2 #for some reason vertical alignment works better using font_size instead of the bbox height

    # Draw the text with route number
    draw.text((text_x, text_y), f"{row['route_id']}", font=font, fill=route_text_color)
    
    # Draw the text with route name and ETA
    draw.text((anchor_x + font_size * shape_width_to_height_ratio + 5, anchor_y), f"{row['trip_headsign']} - {row['eta_minutes_str']}", font=font, fill=font_color)
    
    # Increment the y coordinate for the next line
    anchor_y += line_height

## print -------------------------

# Save the image
image.save(output_image)