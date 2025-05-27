"""
Script loaded onto inky frame that pulls the jpg from github pages, loads onto the SD card, and displays on the screen. 

Run this script as main.py on the inky frame to run on screen start up

Adapted from: https://github.com/pimoroni/pimoroni-pico/blob/main/micropython/examples/inky_frame/inky_frame_xkcd_daily.py

"""

import gc
import uos
import machine
import jpegdec
import uasyncio
import sdcard
import secrets
import time
from urllib import urequest
from network_manager import NetworkManager
from picographics import PicoGraphics, DISPLAY_INKY_FRAME_7 as DISPLAY  # 7.3"

gc.collect()  # We're really gonna need that RAM!

def safe_urlopen(url, max_retries=3, timeout=10):
    """Safely open a URL with retries and proper cleanup"""
    for attempt in range(max_retries):
        try:
            print_log(f"Attempt {attempt + 1} of {max_retries} to fetch {url}")
            socket = urequest.urlopen(url)
            return socket
        except Exception as e:
            print_log(f"Attempt {attempt + 1} failed: {str(e)}")
            if attempt < max_retries - 1:
                print_log("Waiting before retry...")
                time.sleep(2)  # Wait 2 seconds between retries
            else:
                raise  # Re-raise the last exception if all retries failed

def download_file(url, filename, chunk_size=1024):
    """Download a file with proper error handling and cleanup"""
    socket = None
    try:
        socket = safe_urlopen(url)
        
        # Stream the image data from the socket onto disk in chunks
        data = bytearray(chunk_size)
        with open(filename, "wb") as f:
            while True:
                if socket.readinto(data) == 0:
                    break
                f.write(data)
        return True
    except Exception as e:
        print_log(f"Download failed: {str(e)}")
        return False
    finally:
        if socket:
            try:
                socket.close()
            except:
                pass

def status_handler(mode, status, ip):
    print_log(f"Network status: {mode} - {status} - {ip}")

print_log("Connecting to WiFi...")
network_manager = NetworkManager(secrets.COUNTRY, status_handler=status_handler)
uasyncio.get_event_loop().run_until_complete(network_manager.client(secrets.WIFI_SSID, secrets.WIFI_PASSWORD))

print_log("Connected to WiFi!")
print_log("Connecting to SD card...")
graphics = PicoGraphics(DISPLAY)

WIDTH, HEIGHT = graphics.get_bounds()
FILENAME = "/sd/result.jpg"
ENDPOINT = "https://lindsayevanslee.github.io/inky-frame/belcourt/result.jpg"

# Initialize SD card
try:
    sd_spi = machine.SPI(0, sck=machine.Pin(18, machine.Pin.OUT), mosi=machine.Pin(19, machine.Pin.OUT), miso=machine.Pin(16, machine.Pin.OUT))
    sd = sdcard.SDCard(sd_spi, machine.Pin(22))
    uos.mount(sd, "/sd")
    print_log("SD card mounted successfully")
except Exception as e:
    print_log(f"SD card mount failed: {str(e)}")
    raise

gc.collect()  # Claw back some RAM!

print_log("Downloading image...")
if not download_file(ENDPOINT, FILENAME):
    print_log("Failed to download image")
    raise Exception("Image download failed")

print_log("Image downloaded!")

print_log("Decoding image...")
jpeg = jpegdec.JPEG(graphics)
gc.collect()  # For good measure...

try:
    graphics.set_pen(1)
    graphics.clear()

    print_log("Drawing image...")
    jpeg.open_file(FILENAME)
    jpeg.decode() 

    graphics.update()
    print_log("Image drawn!")
except Exception as e:
    print_log(f"Error drawing image: {str(e)}")
    raise
finally:
    # Clean up
    try:
        if os.path.exists(FILENAME):
            os.remove(FILENAME)
    except:
        pass
    gc.collect()