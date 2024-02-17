#https://python.plainenglish.io/generating-text-on-image-with-python-eefe4430fe77

#after running spider, navigate to belcourt folder before running
#cd ../..

### setup -------------------------

from PIL import Image, ImageDraw, ImageFont, ImageOps
import json

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
with open("output_showtimes.json", "rt") as f:
    showtimes = json.load(f)

#set dimensions
width = 800
height = 480

#define title
title = "TODAY'S SHOWTIMES"

#define subtitle
subtitle = showtimes[0]['date'][0]


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

for i in range(len(showtimes[0]['shows'])):

    this_show = showtimes[0]['shows'][str(i)]['show'][0]
    this_showtimes = ', '.join(showtimes[0]['shows'][str(i)]['showtimes'])

    #concatenate this show with its showtimes into one string
    this_showtime_string = this_show + ' ' + this_showtimes + '\n'

    #insert newlines into this showtime string
    this_showtime_string = insert_newlines(this_showtime_string, every=50)

    #add this showtime string to the full showtime string
    showtime_string = showtime_string + this_showtime_string

#count number of lines in showtime string
num_lines = showtime_string.count('\n') + 1

#adjust size of font based on how many lines there are
if num_lines > 14:
    font_show = ImageFont.truetype("Montserrat-Bold.ttf", size = 25 * (12/num_lines))


imgDraw.text((10, 100), anchor = 'la', text = showtime_string, font=font_show, fill=(51, 51, 51))


### print -----------------------------------

#save result
background.save('result.jpg', progressive = False)

background.save('result_optimized.jpg', progressive = False, optimize = True, quality = 30)