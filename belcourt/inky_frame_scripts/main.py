import time
import machine
import gc
import builtins
import inky_frame
from sync_time import sync_time_via_ntp
import sys


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

# Diagnostic functions
def check_wake_reason():
    """Try to determine why we woke up"""
    try:
        # Check reset cause
        reset_cause = machine.reset_cause()
        causes = {
            machine.PWRON_RESET: "PWRON_RESET (power on)",
            machine.WDT_RESET: "WDT_RESET (watchdog)",
            #machine.SOFT_RESET: "SOFT_RESET (software)",
            #machine.DEEPSLEEP_RESET: "DEEPSLEEP_RESET (deep sleep wake)",
        }
        cause_str = causes.get(reset_cause, f"UNKNOWN ({reset_cause})")
        print_log(f"Wake reason: {cause_str}")
    except Exception as e:
        print_log(f"Could not determine wake reason: {e}")

def check_battery_voltage():
    """Check battery voltage if possible"""
    try:
        # Vsys pin on Pico W
        adc = machine.ADC(29)
        reading = adc.read_u16()
        voltage = (reading * 3.3) / 65535 * 3  # Convert to volts
        print_log(f"Battery/Vsys voltage: {voltage:.2f}V (raw ADC: {reading})")
        
        if voltage < 3.0:
            print_log("WARNING: Low voltage detected!")
        return voltage
    except Exception as e:
        print_log(f"Could not read battery voltage: {e}")
        return 0

def check_rtc_status():
    """Check RTC status"""
    try:
        rtc = inky_frame.rtc
        current = rtc.datetime()
        print_log(f"Inky RTC datetime: {current}")
        
        # Check if RTC has valid time (not default)
        if current[0] < 2020:  # Year before 2020 means RTC lost time
            print_log("WARNING: RTC has lost time (battery dead?)")
    except Exception as e:
        print_log(f"Could not read RTC: {e}")

def log_memory_status():
    """Log memory usage"""
    try:
        gc.collect()
        free = gc.mem_free()
        allocated = gc.mem_alloc()
        total = free + allocated
        percent = (allocated / total) * 100
        print_log(f"Memory: {allocated}/{total} bytes used ({percent:.1f}%)")
    except Exception as e:
        print_log(f"Could not check memory: {e}")

print_log("=== STARTING MAIN PROGRAM ===")
print_log(f"MicroPython version: {sys.version}")

# Check diagnostic info on startup
check_wake_reason()
check_battery_voltage()
check_rtc_status()
log_memory_status()

print_log("Try to sync time on startup")
sync_time_via_ntp(print_log)

print_log("entering while loop")

# Add error recovery
max_errors = 3
error_count = 0
cycle_count = 0

try:
    while True:
        try:
            cycle_count += 1
            print_log(f"=== Starting cycle #{cycle_count} ===")
            
            print_log("starting showtimes script")
            with open("showtimes_from_web.py") as f:
                exec(f.read())
            
            print_log("finished showtimes script")
            error_count = 0  # Reset on success
            
            # Check status before sleep
            print_log("Pre-sleep status check:")
            check_battery_voltage()
            check_rtc_status()
            log_memory_status()
            
            print_log("going to sleep now")
            
            # Modified sleep with more logging
            try:
                print_log("Attempting inky_frame.sleep_for(720 minutes)")
                print_log("If this is the last message, deep sleep worked!")
                inky_frame.sleep_for(720)
                
                # If we get here, sleep didn't actually sleep
                print_log("WARNING: sleep_for() returned immediately - sleep didn't happen!")
                
            except Exception as e:
                print_log(f"Sleep error: {e}, using fallback sleep")
                print_log(f"Error type: {type(e).__name__}")
                print_log(f"Starting fallback: 72 x 10-minute sleeps")
                
                # Fallback: lighter sleep that's more reliable
                for i in range(72):
                    if i % 6 == 0:  # Log every hour
                        print_log(f"Fallback sleep progress: {i}/72 cycles ({i*10} minutes elapsed)")
                        check_battery_voltage()
                        log_memory_status()
                    time.sleep(600)  # 10 minutes
                    gc.collect()
                
                print_log("Fallback sleep completed - continuing loop")
                    
        except Exception as e:
            error_count += 1
            print_log(f"ERROR in main loop (attempt {error_count}): {type(e).__name__}: {str(e)}")
            
            # Log full traceback if possible
            try:
                import sys
                import io
                import traceback
                s = io.StringIO()
                traceback.print_exc(file=s)
                print_log(f"Traceback: {s.getvalue()}")
            except:
                pass
            
            if error_count >= max_errors:
                print_log("Max errors reached, attempting recovery sleep")
                time.sleep(3600)  # Sleep 1 hour then retry
                error_count = 0
            else:
                print_log(f"Waiting 30 seconds before retry...")
                time.sleep(30)  # Brief pause before retry
                
except Exception as e:
    print_log(f"FATAL ERROR: {type(e).__name__}: {str(e)}")
    print_log("Program terminating")
