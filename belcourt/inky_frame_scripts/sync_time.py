"""
Module for synchronizing time on Inky Frame via NTP
"""
import time
import machine
import ntptime
import uasyncio
import inky_frame
from network_manager import NetworkManager
import secrets

def print_log(*args, **kwargs):
    """Forward declaration for print_log to avoid circular imports"""
    # This will be replaced by main.py's print_log function
    print(*args, **kwargs)

def sync_time_via_ntp(print_log_func=None):
    """
    Synchronize time via NTP and update both Pico and Inky Frame RTC clocks
    
    Args:
        print_log_func: Function to use for logging (defaults to regular print)
    
    Returns:
        bool: True if time sync was successful, False otherwise
    """
    global print_log
    
    # Use the provided print_log function if available
    if print_log_func:
        print_log = print_log_func
    
    print_log("Attempting to sync time via NTP...")
    try:
        # Define a simple status handler for the network manager
        def status_handler(mode, status, ip):
            print_log(f"Network: {mode} {status} {ip}")
        
        # Connect to WiFi
        print_log("Connecting to WiFi for time sync...")
        network_manager = NetworkManager(secrets.COUNTRY, status_handler=status_handler)
        uasyncio.get_event_loop().run_until_complete(
            network_manager.client(secrets.WIFI_SSID, secrets.WIFI_PASSWORD)
        )
        
        # Set the NTP server (optional, uses pool.ntp.org by default)
        ntptime.host = "pool.ntp.org"
        
        # Sync time using NTP
        for attempt in range(3):  # Try up to 3 times
            try:
                print_log(f"Getting time from NTP server (attempt {attempt+1}/3)...")
                ntptime.settime()
                break
            except Exception as e:
                print_log(f"NTP sync attempt failed: {e}")
                time.sleep(1)
                if attempt == 2:  # Last attempt failed
                    raise
        
        # Get the current time
        current_time = time.localtime()
        print_log(f"Current time set to: {format_time(current_time)}")
        
        # Sync the Inky Frame RTC with the current time
        print_log("Syncing Inky Frame RTC...")
        
        # First, set the Pico's RTC
        rtc = machine.RTC()
        year, month, day, hour, minute, second = current_time[0:6]
        weekday = current_time[6]
        rtc.datetime((year, month, day, weekday, hour, minute, second, 0))
        
        # Then use inky_frame functions to sync the Inky's PCF RTC with Pico's RTC
        inky_frame.set_time()
        
        # Verify the times
        pico_time = time.localtime()
        inky_time = inky_frame.rtc.datetime()
        
        print_log(f"Pico RTC time: {format_time(pico_time)}")
        print_log(f"Inky PCF RTC time: {format_inky_time(inky_time)}")
        
        # Disconnect WiFi to save power
        network_manager.disconnect()
        print_log("WiFi disconnected after time sync")
        
        return True
    except Exception as e:
        print_log(f"ERROR during time sync: {type(e).__name__}: {str(e)}")
        return False

def format_time(t):
    """Format a time tuple into a readable string"""
    return '{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}'.format(t[0], t[1], t[2], t[3], t[4], t[5])

def format_inky_time(t):
    """Format Inky Frame RTC time tuple into a readable string"""
    # Inky Frame PCF RTC returns: (year, month, day, weekday, hour, minute, second)
    return '{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}'.format(t[0], t[1], t[2], t[4], t[5], t[6])

# This allows the module to be run directly for testing
if __name__ == "__main__":
    print("Running sync_time.py directly")
    sync_time_via_ntp()