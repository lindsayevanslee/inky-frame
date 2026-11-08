"""Host-side (CPython) tests for main.py's sleep guarantee and boot log.

These do NOT run on the Inky Frame. They stub out the MicroPython hardware
modules (machine, inky_frame, network, sdcard, sync_time) and execute main.py
in a temp directory, so we can check the control flow:

  * a failing showtimes script still ends in inky_frame.sleep_for(RETRY)
  * a successful one ends in inky_frame.sleep_for(SLEEP)
  * the SD boot log counts boots and flags a run that never reached sleep

Run from the repo root:
    python3 -m unittest discover -s belcourt/inky_frame_scripts/tests
Do not copy this folder to the device.
"""
import os
import shutil
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN_PY = os.path.join(HERE, "..", "main.py")


class StopTest(BaseException):
    """Raised by the fake sleep_for to break main.py's infinite loop.
    BaseException, so main.py's `except Exception` blocks can't swallow it."""


def make_stubs(sleep_calls, sd_root):
    machine = types.ModuleType("machine")

    class Pin:
        OUT = IN = ALT = PULL_DOWN = 0
        def __init__(self, *a, **k): pass

    class ADC:
        def __init__(self, *a): pass
        def read_u16(self): return 27000   # ~4.08 V after the x3 divider

    machine.Pin, machine.ADC = Pin, ADC
    machine.SPI = lambda *a, **k: None
    machine.reset_cause = lambda: 1
    machine.PWRON_RESET, machine.WDT_RESET = 1, 3

    class FakeRTC:
        def datetime(self): return (2026, 11, 7, 12, 0, 0, 5)

    inky = types.ModuleType("inky_frame")
    inky.rtc = FakeRTC()
    inky.woken_by_rtc = lambda: True
    inky.woken_by_button = lambda: False

    def sleep_for(minutes):
        sleep_calls.append(minutes)
        raise StopTest()
    inky.sleep_for = sleep_for

    network = types.ModuleType("network")
    network.STA_IF = 0
    class WLAN:
        def __init__(self, *a): pass
        def active(self, *a): return False
        def disconnect(self): pass
    network.WLAN = WLAN

    sdcard = types.ModuleType("sdcard")
    sdcard.SDCard = lambda *a, **k: None

    sync_time = types.ModuleType("sync_time")
    sync_time.sync_time_via_ntp = lambda log: False

    return {"machine": machine, "inky_frame": inky, "network": network,
            "sdcard": sdcard, "sync_time": sync_time}


class MainSleepTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.sd = os.path.join(self.tmp, "sd")
        os.mkdir(self.sd)
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)
        self.saved_modules = {}

    def tearDown(self):
        os.chdir(self.old_cwd)
        for name, mod in self.saved_modules.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod
        shutil.rmtree(self.tmp)

    def run_main(self, showtimes_source):
        with open("showtimes_from_web.py", "w") as f:
            f.write(showtimes_source)
        sleep_calls = []
        for name, mod in make_stubs(sleep_calls, self.sd).items():
            self.saved_modules.setdefault(name, sys.modules.get(name))
            sys.modules[name] = mod
        with open(MAIN_PY) as f:
            src = f.read()
        # Map the device's absolute /sd paths into the temp dir, and give
        # CPython MicroPython's sys.print_exception.
        src = src.replace('SD_MOUNT = "/sd"', f'SD_MOUNT = {self.sd!r}')
        sys.print_exception = lambda e, f: f.write(repr(e))
        os.mount = lambda dev, path: None   # MicroPython-only; temp dir stands in for /sd
        g = {"__name__": "__main__"}
        try:
            with self.assertRaises(StopTest):
                exec(compile(src, "main.py", "exec"), g)
        finally:
            del os.mount
        return sleep_calls

    def read_sd(self, name):
        with open(os.path.join(self.sd, name)) as f:
            return f.read()

    def test_failure_still_sleeps_with_retry_interval(self):
        calls = self.run_main('raise Exception("Image download failed")\n')
        self.assertEqual(calls, [60])
        self.assertIn("ERROR in cycle", open("error_log.txt").read())

    def test_success_sleeps_full_interval(self):
        calls = self.run_main('print_log("drawn")\n')
        self.assertEqual(calls, [720])
        self.assertEqual(self.read_sd("boot_state.txt"), "1 sleeping")

    def test_boot_log_flags_run_that_never_slept(self):
        with open(os.path.join(self.sd, "boot_state.txt"), "w") as f:
            f.write("41 awake")   # previous boot died before sleep_for()
        self.run_main('print_log("drawn")\n')
        log = self.read_sd("boot_log.txt")
        self.assertIn("boot#42", log)
        self.assertIn("vsys=4.08V", log)
        self.assertIn("PREVIOUS RUN DID NOT REACH SLEEP", log)


if __name__ == "__main__":
    unittest.main()
