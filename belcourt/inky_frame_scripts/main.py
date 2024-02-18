import time
import machine
import gc
import builtins
import inky_frame

# Functions needed to log messages to a file error_log.txt
# adapted from Pimoroni forum thread: https://forums.pimoroni.com/t/inky-frame-not-refreshing-screen-on-battery-power-using-inky-frame-sleep-for/23174/7 
def get_timestamp():
    now = time.localtime()
    return '{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}'.format(now[0], now[1], now[2], now[3], now[4], now[5])

def log(message):
    timestamp = get_timestamp()
    with open('error_log.txt', 'a') as f:
        f.write(f"{timestamp} - {message}\n")

def print_log(*args, **kwargs):
    message = " ".join(str(arg) for arg in args)
    log(message)
    builtins.print(*args, **kwargs)

"""

#If you are getting weird errors after sleep_for(), 
#there may be an issue with the clocks being out of sync.
#Try running this code in console to sync the clocks while the inky frame is plugged in to USB

inky_frame.pcf_to_pico_rtc()  # Sync Inky RTC time to Pico's RTC

year, month, day, dow, hour, minute, second, _ = machine.RTC().datetime()

inky_frame.set_time()  # Sets both the Inky and Pico RTC

print(time.localtime())
print(inky_frame.rtc.datetime())

"""


print_log("entering while loop")

#run showtimes_from_web.py on start-up
while True:
    print_log("starting showtimes script")
    with open("showtimes_from_web.py") as f:
        exec(f.read())
    
    print_log("finished showtimes script")
    print_log("going to sleep now")
    #import showtimes_from_web
    #showtimes_from_web.main()

    #import inky_helper as ih
    #import inky_frame
    #ih.clear_state()
    #ih.launch_app("showtimes_from_web")
    #ih.clear_state()
    inky_frame.sleep_for(60)

