"""
Refresh the stored spider run archive WITHOUT losing history.

Why this exists
---------------
GitHub only serves workflow runs it still retains (~90 days to ~13 months).
A naive `gh api > spider_runs_raw.json` therefore OVERWRITES the file and
silently drops any older runs GitHub has since purged -- the exact data-loss
we're trying to avoid. This script instead does a lossless **merge by run id**:

  archive  = existing spider_runs_raw.json   (may contain purged-from-API runs)
  live     = current GitHub API pull         (freshest data, may add new runs)
  result   = union by `id`; on conflict the LIVE record wins (status/conclusion
             can change as a run finishes); records only in the archive are kept.

Run ids are globally unique and immutable, so this is safe and idempotent:
re-running never duplicates and never drops. A sidecar manifest.json records
provenance (when pulled, how far back coverage reaches, counts).

Usage
-----
    # Pull live from GitHub, merge into the archive, update the manifest:
    uv run python3 analysis/refresh_data.py --pull

    # Merge a live pull you captured yourself (e.g. offline) instead of calling gh:
    gh api --paginate \
      "repos/lindsayevanslee/inky-frame/actions/workflows/actions.yml/runs?per_page=100" \
      --jq '.workflow_runs[] | {id,name,event,status,conclusion,created_at,run_started_at,updated_at,html_url,head_branch,head_sha,run_attempt}' \
      > /tmp/live.ndjson
    uv run python3 analysis/refresh_data.py --merge-file /tmp/live.ndjson

    # Just rebuild the manifest from the current archive (no network):
    uv run python3 analysis/refresh_data.py

Note: this script does NOT have Date.now()-style access in the harness, but as a
normal `uv run` invocation it does -- we read the wall clock for `last_refreshed`.
That timestamp is provenance only; no analysis math depends on it.
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
ARCHIVE = os.path.join(DATA, "spider_runs_raw.json")
MANIFEST = os.path.join(DATA, "manifest.json")

OWNER_REPO = "lindsayevanslee/inky-frame"
WORKFLOW = "actions.yml"
FIELDS = ["id", "name", "event", "status", "conclusion", "created_at",
          "run_started_at", "updated_at", "html_url", "head_branch",
          "head_sha", "run_attempt"]


def load_archive() -> dict:
    """Return {id: record} from the existing archive (empty if none)."""
    if not os.path.exists(ARCHIVE):
        return {}
    with open(ARCHIVE) as f:
        return {r["id"]: r for r in json.load(f)}


def pull_live() -> list[dict]:
    """Pull current runs from the GitHub API via gh. Raises on failure."""
    jq = (".workflow_runs[] | {"
          + ", ".join(f"{k}" for k in FIELDS) + "}")
    cmd = ["gh", "api", "--paginate",
           f"repos/{OWNER_REPO}/actions/workflows/{WORKFLOW}/runs?per_page=100",
           "--jq", jq]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"gh api failed:\n{out.stderr}")
    return [json.loads(l) for l in out.stdout.splitlines() if l.strip()]


def load_ndjson(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def merge(archive: dict, live: list[dict]) -> tuple[dict, int, int]:
    """Union by id; live wins on conflict. Returns (merged, n_new, n_updated)."""
    n_new = n_updated = 0
    for rec in live:
        rid = rec["id"]
        if rid not in archive:
            n_new += 1
        elif archive[rid] != rec:
            n_updated += 1
        archive[rid] = rec  # live wins
    return archive, n_new, n_updated


def write_archive(merged: dict) -> list[dict]:
    """Write archive sorted by run_started_at (stable, diff-friendly)."""
    records = sorted(merged.values(),
                     key=lambda r: (r.get("run_started_at") or "", r["id"]))
    with open(ARCHIVE, "w") as f:
        json.dump(records, f, indent=2)
    return records


def write_manifest(records: list[dict], pulled_live: bool):
    sched = [r for r in records if r.get("event") == "schedule"]
    starts = sorted(r["run_started_at"] for r in records if r.get("run_started_at"))
    manifest = {
        # Provenance of THIS snapshot of the archive.
        "last_refreshed_utc": datetime.now(timezone.utc).isoformat(),
        "pulled_from_live_api": pulled_live,
        "source": f"github.com/{OWNER_REPO} workflow {WORKFLOW}",
        "record_count": len(records),
        "scheduled_run_count": len(sched),
        # Coverage window the archive actually holds (self-dating via run times).
        "earliest_run_started_utc": starts[0] if starts else None,
        "latest_run_started_utc": starts[-1] if starts else None,
        "note": ("Archive is append-only via merge-by-id; it may reach FURTHER "
                 "back than GitHub's live API still retains, because purged runs "
                 "captured in earlier refreshes are preserved here."),
    }
    with open(MANIFEST, "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--pull", action="store_true",
                   help="pull live from GitHub via gh, then merge")
    g.add_argument("--merge-file", metavar="NDJSON",
                   help="merge a live pull from a local NDJSON file instead")
    args = ap.parse_args()

    archive = load_archive()
    before = len(archive)

    pulled_live = False
    if args.pull:
        live = pull_live()
        pulled_live = True
    elif args.merge_file:
        live = load_ndjson(args.merge_file)
    else:
        live = []  # manifest-only rebuild

    merged, n_new, n_updated = merge(archive, live)
    records = write_archive(merged)
    manifest = write_manifest(records, pulled_live)

    print(f"Archive: {before} -> {len(records)} records "
          f"(+{n_new} new, {n_updated} updated in place)")
    print(f"Coverage: {manifest['earliest_run_started_utc']} -> "
          f"{manifest['latest_run_started_utc']}")
    print(f"Wrote {ARCHIVE}")
    print(f"Wrote {MANIFEST}")


if __name__ == "__main__":
    main()
