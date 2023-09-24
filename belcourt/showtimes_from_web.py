"""
Script loaded onto inky frame that pulls the jpg from github pages, loads onto the SD card, and displays on the screen. 

Run this script as main.py on the inky frame to run on screen start up

"""

import gc
import uos
import machine
import jpegdec
import uasyncio
import sdcard
import secrets
from urllib import urequest
from network_manager import NetworkManager
from picographics import PicoGraphics, DISPLAY_INKY_FRAME_7 as DISPLAY  # 7.3"

gc.collect()  # We're really gonna need that RAM!


def status_handler(mode, status, ip):
    print(mode, status, ip)


network_manager = NetworkManager(secrets.COUNTRY, status_handler=status_handler)
uasyncio.get_event_loop().run_until_complete(network_manager.client(secrets.WIFI_SSID, secrets.WIFI_PASSWORD))


graphics = PicoGraphics(DISPLAY)

WIDTH, HEIGHT = graphics.get_bounds()
FILENAME = "/sd/result.jpg"
ENDPOINT = "https://lindsayevanslee.github.io/inky-frame/belcourt/result.jpg"

sd_spi = machine.SPI(0, sck=machine.Pin(18, machine.Pin.OUT), mosi=machine.Pin(19, machine.Pin.OUT), miso=machine.Pin(16, machine.Pin.OUT))
sd = sdcard.SDCard(sd_spi, machine.Pin(22))
uos.mount(sd, "/sd")
gc.collect()  # Claw back some RAM!


url = ENDPOINT


socket = urequest.urlopen(url)

# Stream the image data from the socket onto disk in 1024 byte chunks
# the 600x448-ish jpeg will be roughly ~24k, we really don't have the RAM!
data = bytearray(1024)
with open(FILENAME, "wb") as f:
    while True:
        if socket.readinto(data) == 0:
            break
        f.write(data)
socket.close()
gc.collect()  # We really are tight on RAM!


jpeg = jpegdec.JPEG(graphics)
gc.collect()  # For good measure...

graphics.set_pen(1)
graphics.clear()

jpeg.open_file(FILENAME)
jpeg.decode() 


graphics.update()
