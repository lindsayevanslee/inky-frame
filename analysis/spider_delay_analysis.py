"""
Analyze how delayed the 'run belcourt spider' GitHub Actions scheduled runs
have been, comparing each run's actual UTC start to the cron fire time that was
*configured at that moment* (reconstructed from git history).

Robust to:
  - schedule changes over time (instant-based, not date-based, boundaries)
  - runs delayed PAST UTC MIDNIGHT (each run is matched to the nearest
    PRECEDING expected fire instant, not to "the cron time on the run's date")
  - skipped fires (an expected fire with no run) and doubled runs (2+ runs for
    one fire) -- both detected and reported rather than silently mishandled

Data sources (stored, so this re-runs without hitting the live API/git):
  analysis/data/spider_runs_raw.json      -- raw GitHub API run records
  analysis/data/schedule_history.json     -- per-commit cron, with UTC instants

Outputs:
  analysis/data/spider_delays.csv         -- per-run derived table
  analysis/spider_delay.png               -- chart
  printed summary stats + anomaly report

Run with:  uv run --with matplotlib python3 analysis/spider_delay_analysis.py
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone, timedelta
from collections import deque

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


# --------------------------------------------------------------------------
# Load stored data
# --------------------------------------------------------------------------
def load_json(name):
    with open(os.path.join(DATA, name)) as f:
        return json.load(f)


def parse_utc(s: str) -> datetime:
    """Parse an ISO8601 instant to an aware UTC datetime."""
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc)


runs_raw = load_json("spider_runs_raw.json")
sched_raw = load_json("schedule_history.json")


# --------------------------------------------------------------------------
# Build the schedule timeline: collapse consecutive same-cron commits into
# distinct periods. Each period = (effective_from_utc, cron_or_None).
# cron None means "no schedule" (e.g. after the cron-job.org switch).
# --------------------------------------------------------------------------
periods = []  # (effective_from: datetime, cron: str|None)
for rec in sorted(sched_raw, key=lambda r: r["committed_utc"]):
    cron = rec["cron"]
    eff = parse_utc(rec["committed_utc"])
    if periods and periods[-1][1] == cron:
        continue  # same schedule as previous period -> not a real change
    periods.append((eff, cron))


def parse_cron(cron: str):
    """Return (minute_field, hour_field) as parsed cron fields.

    Supports the forms this repo has actually used: 'M H * * *' and '*/N * * * *'.
    Returns a callable that, given a UTC date, yields the fire datetimes on that
    UTC day. We keep it minimal and explicit rather than pulling a cron library,
    so the matching logic is fully auditable.
    """
    minute_f, hour_f, *_ = cron.split()

    def fires_on(day: datetime):
        """Yield all fire instants on the UTC calendar day of `day`."""
        base = day.replace(hour=0, minute=0, second=0, microsecond=0)
        # Determine candidate minutes and hours.
        if minute_f.startswith("*/"):
            step = int(minute_f[2:])
            minutes = range(0, 60, step)
        elif minute_f == "*":
            minutes = range(0, 60)
        else:
            minutes = [int(minute_f)]
        if hour_f.startswith("*/"):
            step = int(hour_f[2:])
            hours = range(0, 24, step)
        elif hour_f == "*":
            hours = range(0, 24)
        else:
            hours = [int(hour_f)]
        for h in hours:
            for m in minutes:
                yield base + timedelta(hours=h, minutes=m)

    return fires_on


# --------------------------------------------------------------------------
# Generate the full sequence of EXPECTED fire instants across the data window,
# honoring which schedule was active at each instant.
# --------------------------------------------------------------------------
sched_runs = [r for r in runs_raw if r["event"] == "schedule"]
starts = sorted(parse_utc(r["run_started_at"]) for r in sched_runs)
window_start = starts[0] - timedelta(days=1)
window_end = starts[-1] + timedelta(days=1)


def cron_active_at(ts: datetime):
    """The cron string in effect at instant ts (None if no schedule)."""
    active = None
    for eff, cron in periods:
        if eff <= ts:
            active = cron
        else:
            break
    return active


expected_fires = []  # list of datetimes (UTC) the scheduler *should* have fired
day = window_start.replace(hour=0, minute=0, second=0, microsecond=0)
while day <= window_end:
    cron = cron_active_at(day)
    if cron:
        for fire in parse_cron(cron)(day):
            # Only count a fire if THAT cron was active at the fire instant
            # (guards day-boundary cases where the schedule changed mid-day).
            if cron_active_at(fire) == cron and window_start <= fire <= window_end:
                expected_fires.append(fire)
    day += timedelta(days=1)
expected_fires.sort()


# --------------------------------------------------------------------------
# Match each ACTUAL run to the latest expected fire <= its start.
# This is the midnight-safe core: a run at 00:30 UTC matches yesterday's fire.
# --------------------------------------------------------------------------
def latest_fire_at_or_before(ts: datetime):
    """Binary search: largest expected fire <= ts, or None."""
    lo, hi, ans = 0, len(expected_fires) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if expected_fires[mid] <= ts:
            ans = expected_fires[mid]
            lo = mid + 1
        else:
            hi = mid - 1
    return ans


rows = []  # per-run derived records
fire_to_runs = {}  # fire instant -> list of run starts (to detect doubles/skips)
for r in sched_runs:
    start = parse_utc(r["run_started_at"])
    fire = latest_fire_at_or_before(start)
    if fire is None:
        # No expected fire precedes this run (shouldn't happen given window pad).
        delay_min = None
    else:
        delay_min = (start - fire).total_seconds() / 60.0
        fire_to_runs.setdefault(fire, []).append(start)
    rows.append({
        "run_id": r["id"],
        "run_started_utc": start.isoformat(),
        "matched_fire_utc": fire.isoformat() if fire else "",
        "delay_minutes": round(delay_min, 2) if delay_min is not None else "",
        "crossed_utc_midnight": (fire is not None and start.date() != fire.date()),
        "conclusion": r.get("conclusion") or "",
    })

rows.sort(key=lambda x: x["run_started_utc"])


# --------------------------------------------------------------------------
# Anomaly detection: skipped fires (no run) and doubled fires (2+ runs).
# We only judge fires up to the last actual run (later "missing" fires are just
# the future / post-switch period, not real skips).
# --------------------------------------------------------------------------
last_run = starts[-1]
judged_fires = [f for f in expected_fires if f <= last_run]
skipped = [f for f in judged_fires if f not in fire_to_runs]
doubled = {f: v for f, v in fire_to_runs.items() if len(v) > 1}
midnight_crossers = [r for r in rows if r["crossed_utc_midnight"]]


# --------------------------------------------------------------------------
# Write derived CSV
# --------------------------------------------------------------------------
csv_path = os.path.join(DATA, "spider_delays.csv")
with open(csv_path, "w") as f:
    cols = ["run_id", "run_started_utc", "matched_fire_utc", "delay_minutes",
            "crossed_utc_midnight", "conclusion"]
    f.write(",".join(cols) + "\n")
    for row in rows:
        f.write(",".join(str(row[c]) for c in cols) + "\n")


# --------------------------------------------------------------------------
# Summary stats
# --------------------------------------------------------------------------
ys = [row["delay_minutes"] for row in rows if isinstance(row["delay_minutes"], (int, float))]


def pct(vals, p):
    vals = sorted(vals)
    k = (len(vals) - 1) * p / 100
    lo = int(k)
    hi = min(lo + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)


print(f"Scheduled runs analyzed: {len(ys)}")
print(f"Date range: {rows[0]['run_started_utc'][:10]} -> {rows[-1]['run_started_utc'][:10]}")
print(f"Expected fires in window (up to last run): {len(judged_fires)}")
print(f"Mean delay:   {sum(ys)/len(ys):6.1f} min")
print(f"Median (p50): {pct(ys,50):6.1f} min")
print(f"p90:          {pct(ys,90):6.1f} min")
print(f"p99:          {pct(ys,99):6.1f} min")
print(f"Min / Max:    {min(ys):.1f} / {max(ys):.1f} min")
print(f"Within 5 min: {sum(1 for y in ys if y <= 5)}/{len(ys)}")
print(f"Delayed >30m: {sum(1 for y in ys if y > 30)}/{len(ys)}")
print(f"Delayed >60m: {sum(1 for y in ys if y > 60)}/{len(ys)}")
print()
print("--- Anomalies ---")
print(f"Runs crossing UTC midnight: {len(midnight_crossers)}")
for r in midnight_crossers:
    print(f"   run {r['run_id']} started {r['run_started_utc']} "
          f"for fire {r['matched_fire_utc']} (delay {r['delay_minutes']}m)")
print(f"Skipped fires (no run): {len(skipped)}")
for f in skipped[:20]:
    print(f"   no run for expected fire {f.isoformat()}")
if len(skipped) > 20:
    print(f"   ... and {len(skipped)-20} more")
print(f"Doubled fires (2+ runs): {len(doubled)}")
for f, v in sorted(doubled.items()):
    print(f"   fire {f.isoformat()} had {len(v)} runs: "
          f"{', '.join(s.isoformat() for s in sorted(v))}")
print(f"\nWrote {csv_path}")


# --------------------------------------------------------------------------
# Plot
# --------------------------------------------------------------------------
xs = [parse_utc(row["run_started_utc"]) for row in rows if isinstance(row["delay_minutes"], (int, float))]
fig, ax = plt.subplots(figsize=(13, 6))

ok = [(x, y) for x, row in zip(xs, [r for r in rows if isinstance(r["delay_minutes"], (int, float))])
      for y in [row["delay_minutes"]] if row["conclusion"] == "success"]
bad = [(x, y) for x, row in zip(xs, [r for r in rows if isinstance(r["delay_minutes"], (int, float))])
       for y in [row["delay_minutes"]] if row["conclusion"] != "success"]
if ok:
    ax.scatter([p[0] for p in ok], [p[1] for p in ok], s=14, alpha=0.55,
               color="#2a7", label="run succeeded", zorder=3)
if bad:
    ax.scatter([p[0] for p in bad], [p[1] for p in bad], s=22, alpha=0.8,
               color="#c33", marker="x", label="run failed / other", zorder=4)

# 7-day rolling median trend
pts = sorted(zip(xs, ys))
if len(pts) >= 7:
    dq = deque()
    rx, ry = [], []
    for x, y in pts:
        dq.append((x, y))
        while dq and (x - dq[0][0]) > timedelta(days=7):
            dq.popleft()
        vals = sorted(v for _, v in dq)
        rx.append(x)
        ry.append(vals[len(vals) // 2])
    ax.plot(rx, ry, color="#06c", lw=2, label="7-day rolling median", zorder=5)

# Mark schedule changes that fall in the window
for eff, cron in periods:
    if xs[0] <= eff <= xs[-1]:
        ax.axvline(eff, color="#888", ls="--", lw=1, zorder=2)
        label = cron if cron else "cron-job.org"
        ax.text(eff, ax.get_ylim()[1], f" schedule -> {label}",
                rotation=90, va="top", ha="right", fontsize=8, color="#555")

ax.axhline(5, color="#999", ls=":", lw=1)
ax.text(xs[0], 5, " 5-min on-time threshold", fontsize=8, color="#777", va="bottom")
ax.set_title("GitHub Actions 'run belcourt spider' — scheduled-run delay\n"
             "(actual start minus the cron fire time configured at that moment)")
ax.set_ylabel("Delay after scheduled time (minutes)")
ax.set_xlabel("Run date (UTC)")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
fig.autofmt_xdate()
ax.grid(True, alpha=0.25)
ax.legend(loc="upper left", framealpha=0.9)
ax.set_ylim(bottom=min(0, min(ys) - 2))
fig.tight_layout()
png_path = os.path.join(HERE, "spider_delay.png")
fig.savefig(png_path, dpi=130)
print(f"Wrote {png_path}")
