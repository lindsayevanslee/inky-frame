import time
import machine
import gc
import builtins
import inky_frame
from sync_time import sync_time_via_ntp


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

print_log("=== STARTING MAIN PROGRAM ===")
print_log("Try to sync time on startup")

sync_time_via_ntp(print_log)

print_log("entering while loop")

# Add error recovery
max_errors = 3
error_count = 0

try:
    while True:
        try:
            print_log("starting showtimes script")
            with open("showtimes_from_web.py") as f:
                exec(f.read())
            
            print_log("finished showtimes script")
            error_count = 0  # Reset on success
            
            print_log("going to sleep now")
            
            # Modified sleep
            try:
                inky_frame.sleep_for(720)
            except Exception as e:
                print_log(f"Sleep error: {e}, using fallback sleep")
                # Fallback: lighter sleep that's more reliable
                for i in range(72):
                    time.sleep(600)  # 10 minutes
                    gc.collect()
                    
        except Exception as e:
            error_count += 1
            print_log(f"ERROR in main loop (attempt {error_count}): {type(e).__name__}: {str(e)}")
            
            if error_count >= max_errors:
                print_log("Max errors reached, attempting recovery sleep")
                time.sleep(3600)  # Sleep 1 hour then retry
                error_count = 0
            else:
                time.sleep(30)  # Brief pause before retry
                
except Exception as e:
    print_log(f"FATAL ERROR: {type(e).__name__}: {str(e)}")
