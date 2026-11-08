import time
import machine
import gc
import builtins
import inky_frame   # importing this turns on the battery power-hold pin (GPIO2)
import network
import sdcard
from sync_time import sync_time_via_ntp
import sys
import os


# Functions needed to log messages to a file error_log.txt
# adapted from Pimoroni forum thread: https://forums.pimoroni.com/t/inky-frame-not-refreshing-screen-on-battery-power-using-inky-frame-sleep-for/23174/7

# Logging is size-capped so it can never fill the Pico's flash and crash the
# boot (the original unbounded log filled the filesystem -> OSError 28 ENOSPC).
LOG_FILE = 'error_log.txt'
LOG_MAX_BYTES = 50 * 1024   # rotate when the log grows past ~50 KB

def get_timestamp():
    now = time.localtime()
    return '{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}'.format(now[0], now[1], now[2], now[3], now[4], now[5])

def _notice(message):
    """Emit a logging-system notice (rotation / log errors) to the console.

    Used by the low-level log machinery, which runs before print_log is
    defined and must never recurse back into log(). Console-only and wrapped
    so it can never itself crash the program. The fresh log file gets its own
    marker line written directly by the caller.
    """
    try:
        builtins.print(f"[log] {message}")
    except Exception:
        pass

def _rotate_log_if_needed():
    """If the log is over the size cap, keep one previous copy and start fresh.

    Keeping a single .1 backup bounds total log usage at ~2x LOG_MAX_BYTES
    while preserving recent history for debugging. Returns a marker string to
    record at the top of the new log, or None if no rotation happened.
    """
    try:
        size = os.stat(LOG_FILE)[6]   # index 6 = st_size on MicroPython
    except OSError:
        return None  # file doesn't exist yet; nothing to rotate
    if size <= LOG_MAX_BYTES:
        return None
    backup = LOG_FILE + '.1'
    try:
        os.remove(backup)             # remove old backup if present
    except OSError:
        pass
    try:
        os.rename(LOG_FILE, backup)   # current log becomes the backup
        _notice(f"rotated {LOG_FILE} ({size} bytes) -> {backup}")
        return f"log rotated: previous {size} bytes saved to {backup}"
    except OSError as e:
        # Rename failed (e.g. disk full): fall back to deleting so we
        # always reclaim space rather than crash.
        try:
            os.remove(LOG_FILE)
            _notice(f"rotate rename failed ({e}); deleted {LOG_FILE} ({size} bytes) to reclaim space")
            return f"log rotated: rename failed, previous {size} bytes deleted to reclaim space"
        except OSError as e2:
            _notice(f"rotate failed entirely: rename={e} remove={e2}")
            return None

def log(message):
    # Never let a logging failure crash the program. A dead log is fine;
    # a Pico that won't boot because it can't write its own log is not.
    try:
        rotation_note = _rotate_log_if_needed()
        timestamp = get_timestamp()
        with open(LOG_FILE, 'a') as f:
            # If we just rotated, record why at the top of the fresh log.
            if rotation_note:
                f.write(f"{timestamp} - [log] {rotation_note}\n")
            f.write(f"{timestamp} - {message}\n")
    except Exception as e:
        # Surface the failure on the console so a broken log isn't silent,
        # but still never crash the caller.
        _notice(f"write failed: {type(e).__name__}: {e}")

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

def wifi_off():
    """Disconnect and power down the Wi-Fi radio. Safe to call any time."""
    try:
        wlan = network.WLAN(network.STA_IF)
        if wlan.active():
            wlan.disconnect()
            wlan.active(False)
    except Exception as e:
        _notice(f"wifi_off failed: {e}")

def read_vsys():
    """Return VSYS in volts, read the Pico W-safe way.

    On the Pico W, GPIO29 is BOTH the VSYS/3 ADC input AND the Wi-Fi chip's
    SPI clock, and GPIO25 is the Wi-Fi chip-select. A plain ADC(29) read
    while Wi-Fi is up measures clock traffic, not the battery. So: radio
    off, deselect the chip (GPIO25 high), read GPIO29 as an analog input,
    then hand GPIO29 back to the Wi-Fi driver (alt function 7).
    Averages a few samples to smooth noise. Raises on failure.
    """
    wifi_off()
    try:
        machine.Pin(25, machine.Pin.OUT, value=1)
        machine.Pin(29, machine.Pin.IN, pull=None)
        adc = machine.ADC(29)
        total = 0
        for _ in range(8):
            total += adc.read_u16()
        return (total / 8) * 3.3 / 65535 * 3   # x3 = Pico's on-board divider
    finally:
        try:
            machine.Pin(29, machine.Pin.ALT, pull=machine.Pin.PULL_DOWN, alt=7)
        except Exception:
            pass

def check_battery_voltage(label=""):
    """Log VSYS (Wi-Fi is switched off first, see read_vsys)."""
    try:
        voltage = read_vsys()
        print_log(f"Battery/Vsys voltage {label}: {voltage:.2f}V (idle, Wi-Fi off)")
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

# ---------------------------------------------------------------------------
# Boot-loop detector (written to the SD card, not the Pico's flash)
#
# On battery, inky_frame.sleep_for() doesn't "sleep" the Pico: it arms the
# RTC alarm and then cuts the Pico's power entirely. So every wake is a fresh
# power-on and nothing survives in RAM. To spot crashes and brown-outs we
# persist a tiny state file across boots:
#     /sd/boot_state.txt  ->  "<boot_count> <awake|sleeping>"
# We write "awake" at boot and "sleeping" right before sleep_for(). If a boot
# finds the previous state still "awake", the previous run died (crash,
# brown-out, unplugged) before reaching sleep.
# ---------------------------------------------------------------------------
SD_MOUNT = "/sd"
BOOT_LOG = SD_MOUNT + "/boot_log.txt"
BOOT_STATE = SD_MOUNT + "/boot_state.txt"

SLEEP_MINUTES = 720   # normal refresh interval (12 h)
RETRY_MINUTES = 60    # after a failed cycle: deep-sleep, then try again

def mount_sd():
    """Mount the SD card at /sd if it isn't already. Returns True on success."""
    try:
        sd_spi = machine.SPI(0, sck=machine.Pin(18, machine.Pin.OUT), mosi=machine.Pin(19, machine.Pin.OUT), miso=machine.Pin(16, machine.Pin.OUT))
        os.mount(sdcard.SDCard(sd_spi, machine.Pin(22)), SD_MOUNT)
        return True
    except OSError as e:
        if e.args and e.args[0] == 1:   # EPERM: something is already mounted at /sd
            return True
        print_log(f"SD mount for boot log failed: {e}")
        return False
    except Exception as e:
        print_log(f"SD mount for boot log failed: {e}")
        return False

def pcf_timestamp():
    """Time from the Inky's PCF85063A RTC, which keeps running while the
    Pico is unpowered. Format: (year, month, day, hour, minute, second, dow)."""
    try:
        t = inky_frame.rtc.datetime()
        return '{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}'.format(*t[:6])
    except Exception as e:
        return f"rtc-error({e})"

def write_boot_state(count, state):
    try:
        with open(BOOT_STATE, "w") as f:
            f.write(f"{count} {state}")
    except Exception as e:
        print_log(f"Could not write boot state: {e}")

def record_boot(vsys):
    """Bump the boot counter and append one line to /sd/boot_log.txt.
    Returns the new boot count (0 if the SD card isn't usable)."""
    if not mount_sd():
        return 0
    count, prev_state = 0, "none"
    try:
        with open(BOOT_STATE) as f:
            parts = f.read().split()
        count, prev_state = int(parts[0]), parts[1]
    except Exception:
        pass   # first boot with this feature, or unreadable file: start over
    count += 1

    def woke(fn_name):
        fn = getattr(inky_frame, fn_name, None)   # absent in older firmware
        try:
            return int(fn()) if fn else "?"
        except Exception:
            return "?"

    flag = "" if prev_state in ("sleeping", "none") else "  <-- PREVIOUS RUN DID NOT REACH SLEEP"
    line = (f"{pcf_timestamp()} boot#{count} vsys={vsys:.2f}V "
            f"reset={machine.reset_cause()} rtc_wake={woke('woken_by_rtc')} "
            f"button={woke('woken_by_button')} prev={prev_state}{flag}\n")
    try:
        with open(BOOT_LOG, "a") as f:
            f.write(line)
    except Exception as e:
        print_log(f"Could not write boot log: {e}")
    write_boot_state(count, "awake")
    print_log("Boot record: " + line.strip())
    return count

def go_to_sleep(minutes, boot_count):
    """The single exit point of every cycle. Never raises."""
    wifi_off()   # also matters for the awake fallback below
    check_battery_voltage("(pre-sleep)")
    if boot_count:
        write_boot_state(boot_count, "sleeping")
    try:
        print_log(f"Attempting inky_frame.sleep_for({minutes} minutes)")
        print_log("If this is the last message, deep sleep worked!")
        inky_frame.sleep_for(minutes)
        # On battery we never get here (power is cut). On USB, sleep_for()
        # can't cut power, so it simulates the sleep with time.sleep() and
        # returns afterwards; that's expected.
        print_log("sleep_for() returned (expected on USB power)")
    except Exception as e:
        # Couldn't arm the RTC alarm. Stay awake as a last resort so we at
        # least retry later, but log loudly; this path drains batteries.
        print_log(f"Sleep error: {type(e).__name__}: {e}; awake fallback for {minutes} min")
        try:
            time.sleep(minutes * 60)
        except Exception:
            pass

# ---------------------------------------------------------------------------
# Boot
# ---------------------------------------------------------------------------
# On battery the Pico's own clock restarts from a default date at every
# power-on; copy the Inky's battery-backed RTC into it so log timestamps are
# real before NTP runs. (Helper exists in recent Pimoroni firmware only.)
try:
    if hasattr(inky_frame, "pcf_to_pico_rtc"):
        inky_frame.pcf_to_pico_rtc()
except Exception as e:
    _notice(f"pcf_to_pico_rtc failed: {e}")

print_log("=== STARTING MAIN PROGRAM ===")
print_log(f"MicroPython version: {sys.version}")

# Read VSYS FIRST, before anything turns Wi-Fi on.
vsys_at_boot = check_battery_voltage("(boot)")
boot_count = record_boot(vsys_at_boot)

check_wake_reason()
check_rtc_status()
log_memory_status()

print_log("Try to sync time on startup")
sync_time_via_ntp(print_log)   # catches its own errors

print_log("entering while loop")
cycle_count = 0

while True:
    cycle_count += 1
    sleep_minutes = RETRY_MINUTES   # assume failure until the cycle succeeds
    interrupted = False
    try:
        print_log(f"=== Starting cycle #{cycle_count} ===")
        print_log("starting showtimes script")
        with open("showtimes_from_web.py") as f:
            exec(f.read())
        print_log("finished showtimes script")
        sleep_minutes = SLEEP_MINUTES
        check_rtc_status()
        log_memory_status()
    except KeyboardInterrupt:
        # Ctrl-C from Thonny/mpremote: let the developer get a prompt.
        interrupted = True
        raise
    except Exception as e:
        print_log(f"ERROR in cycle: {type(e).__name__}: {e}")
        try:
            import io
            s = io.StringIO()
            sys.print_exception(e, s)   # MicroPython's traceback printer
            print_log(f"Traceback: {s.getvalue()}")
        except Exception:
            pass
        print_log(f"Will deep-sleep {RETRY_MINUTES} min and retry")
    finally:
        # Whatever happened above (success, failed Wi-Fi, failed download,
        # failed draw, unexpected bug), we always end in sleep_for().
        if not interrupted:
            go_to_sleep(sleep_minutes, boot_count)
