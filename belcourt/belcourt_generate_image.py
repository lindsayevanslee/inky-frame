#https://python.plainenglish.io/generating-text-on-image-with-python-eefe4430fe77

#after running spider, navigate to belcourt folder before running
#cd ../..

print("Starting Belcourt showtime image generation...")

### setup -------------------------

from PIL import Image, ImageDraw, ImageFont, ImageOps
from datetime import datetime
import json

#message shown when the Belcourt lists no events for today (e.g. closed for a
#holiday). Without it the frame would show a blank image with no explanation.
NO_SHOWS_MESSAGE = "No showtimes today."

#create function for inserting indented new lines in a long string without breaking up words
def insert_newlines(string, every=64):
    lines = []
    while string:
        if len(string) <= every:
            lines.append(string)
            break
        else:
            space_position = string.rfind(' ', 0, every)
            if space_position >= 0:
                end = space_position
            else:
                end = every
            lines.append(string[:end])
            string = string[end:].lstrip()
    return '\n        '.join(lines)

#read showtime info
print("Reading showtime data from output_showtimes.json...")
with open("output_showtimes.json", "rt") as f:
    showtimes = json.load(f)

#the spider writes a one-element list; tolerate an empty file/list too
data = showtimes[0] if showtimes else {}
shows = data.get('shows') or {}

#pick the subtitle date. When the site has no "today" block at all (e.g. the
#theater is closed), the spider's date list is empty, and indexing [0] used to
#crash with IndexError. Fall back to the scrape time, formatted to match the
#site's style ("Sunday, Mar 10").
def get_subtitle(data):
    if data.get('date'):
        return data['date'][0].strip()
    try:
        when = datetime.strptime(data['currenttime'], "%Y-%m-%d %H:%M:%S")
    except (KeyError, TypeError, ValueError):
        when = datetime.now()
    return f"{when:%A, %b} {when.day}"

subtitle = get_subtitle(data)

print(f"Processing showtimes for date: {subtitle}")

#set dimensions
width = 800
height = 480

#define title
title = "TODAY'S SHOWTIMES"

#define font
font_title = ImageFont.truetype("Montserrat-Bold.ttf", size=40)
font_subtitle = ImageFont.truetype("Montserrat-Bold.ttf", size=30)
font_show = ImageFont.truetype("Montserrat-Bold.ttf", size=25)

### initialize background ---------------------

#open logo
logo = Image.open('belcourt-logo.png')

#resize logo
logo_resized = ImageOps.contain(logo, (round(width/3), round(height/3)))

#capture logo new size
logo_width, logo_height = logo_resized.size


#initialize background
background = Image.new('RGB', (width, height), color='white')

#define offset
#offset = ((width - logo_width)//2, (height - logo_height)//2) #for centered logo
offset = (5, 5)

#paste logo on background
background.paste(logo_resized, offset)

#initialize imagedraw object
imgDraw = ImageDraw.Draw(background)

### add text to image ------------------------

#draw text on image (https://pillow.readthedocs.io/en/stable/reference/ImageDraw.html#PIL.ImageDraw.ImageDraw.text)
imgDraw.text((width - 10, 30), anchor = 'rt', text = title, font=font_title, fill=(51, 51, 51))

imgDraw.text((width - 10, 70), anchor = 'rt', text = subtitle, font=font_subtitle, fill=(51, 51, 51))

#initialize showtimes string
showtime_string = ''
num_shows = len(shows)
print(f"Found {num_shows} shows to process")

for i in range(num_shows):

    this_show = shows[str(i)]['show'][0]
    print(f"Processing show: {this_show}")

    this_showtimes_list = shows[str(i)]['showtimes']

    #if length of showtimes element is 0, return empty string for showtimes
    if len(this_showtimes_list) == 0:
        this_showtimes = ''
    else:
        this_showtimes = ', '.join(this_showtimes_list)

    #concatenate this show with its showtimes into one string
    this_showtime_string = this_show + ' ' + this_showtimes + '\n'

    #insert newlines into this showtime string
    this_showtime_string = insert_newlines(this_showtime_string, every=50)

    #add this showtime string to the full showtime string
    showtime_string = showtime_string + this_showtime_string

#if there are no events today, say so instead of leaving the area blank
if num_shows == 0:
    print("No shows found; rendering closed message")
    showtime_string = NO_SHOWS_MESSAGE

#count number of lines in showtime string
num_lines = showtime_string.count('\n') + 1

#adjust size of font based on how many lines there are
if num_lines > 14:
    font_show = ImageFont.truetype("Montserrat-Bold.ttf", size = 25 * (12/num_lines))


imgDraw.text((10, 100), anchor = 'la', text = showtime_string, font=font_show, fill=(51, 51, 51))


### print -----------------------------------

#save result
print("Saving images...")
background.save('result.jpg', progressive = False)
background.save('result_optimized.jpg', progressive = False, optimize = True, quality = 30)