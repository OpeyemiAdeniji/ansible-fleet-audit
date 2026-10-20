#!/usr/bin/env python3
"""Estimate how many hours until each host's disks are full, from earlier audit runs.

This is the logic behind ADR 0005 (docs/adr/0005-rank-hosts-by-estimated-time-to-full.md).

Input:
  * the history folder: the `audit-<run id>.json` files that every audit run writes
    (the run id is the UTC time of the run, for example 20261020T103000Z);
  * the current run's host records, as JSON on standard input;
  * the current run id, so the current run counts as the newest sample.

Output (standard output): JSON, one entry per host:
  {"web-01": {"status": "estimated", "hours_to_full": 6.5, "mount": "/var",
              "slope_pct_per_hour": 1.2, "samples": 5}, ...}

`status` is one of:
  estimated          a growing disk, and enough history to estimate when it will be full
  not growing        the disks are flat or falling, so there is nothing to estimate
  not enough history fewer samples than the minimum, or they cover too short a time
  no disk data       the host returned no disk usage (for example, it was unreachable)

Only the Python standard library is used.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RUN_ID_FORMAT = "%Y%m%dT%H%M%SZ"
HISTORY_FILE = re.compile(r"^audit-(\d{8}T\d{6}Z)\.json$")
# A growth rate at or below this many percentage points per hour counts as "not growing".
MIN_SLOPE = 1e-9


def parse_run_id(run_id):
    """Turn a run id such as 20261020T103000Z into a timezone-aware UTC datetime."""
    return datetime.strptime(run_id, RUN_ID_FORMAT).replace(tzinfo=timezone.utc)


def parse_disks(lines):
    """Turn ['/ 42%', '/var 87%'] into {'/': 42, '/var': 87}.

    The percentage is the last word on the line. Everything before it is the mount point,
    which may itself contain spaces. Lines that do not fit are ignored.
    """
    usage = {}
    for line in lines or []:
        parts = str(line).rsplit(None, 1)
        if len(parts) != 2 or not parts[1].endswith("%"):
            continue
        try:
            usage[parts[0]] = int(parts[1][:-1])
        except ValueError:
            continue
    return usage


def load_history(history_dir, now, window_hours):
    """Read the earlier audit files that fall inside the window.

    Returns a list of (time, records), oldest first. Files for the current moment or later are
    skipped, because the current run is passed in separately. Files that cannot be read are
    skipped with a warning on standard error, so one bad file never stops the audit.
    """
    oldest = now - timedelta(hours=window_hours)
    history = []
    folder = Path(history_dir)
    if not folder.is_dir():
        return history
    for path in sorted(folder.iterdir()):
        match = HISTORY_FILE.match(path.name)
        if not match:
            continue
        when = parse_run_id(match.group(1))
        if when >= now or when < oldest:
            continue
        try:
            records = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            print(f"warning: skipping {path.name}: {error}", file=sys.stderr)
            continue
        if not isinstance(records, list):
            print(f"warning: skipping {path.name}: expected a list of records", file=sys.stderr)
            continue
        history.append((when, records))
    return sorted(history, key=lambda item: item[0])


def build_series(samples):
    """Group the samples as {host: {mount: [(time, percent), ...]}}, oldest sample first.

    A host that never reported disk usage still appears, with no mount points.
    """
    series = {}
    for when, records in samples:
        for record in records:
            if not isinstance(record, dict) or "host" not in record:
                continue
            mounts = series.setdefault(record["host"], {})
            for mount, percent in parse_disks(record.get("disks")).items():
                mounts.setdefault(mount, []).append((when, percent))
    for mounts in series.values():
        for points in mounts.values():
            points.sort(key=lambda point: point[0])
    return series


def fit_slope(points):
    """Slope, in percentage points per hour, of the best straight line through the points.

    This is the least squares fit. It uses every sample, so one odd reading moves the result
    less than it would if only the oldest and newest samples were used. Returns None when all
    samples share one time.
    """
    first = points[0][0]
    xs = [(when - first).total_seconds() / 3600 for when, _ in points]
    ys = [percent for _, percent in points]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    spread = sum((x - mean_x) ** 2 for x in xs)
    if spread == 0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / spread


def estimate_mount(points, min_samples, min_span_minutes):
    """Estimate the hours until one mount point is full."""
    span_minutes = (points[-1][0] - points[0][0]).total_seconds() / 60
    if len(points) < min_samples or span_minutes < min_span_minutes:
        return {"status": "not enough history"}
    slope = fit_slope(points)
    if slope is None or slope <= MIN_SLOPE:
        return {"status": "not growing"}
    latest = points[-1][1]
    hours = 0.0 if latest >= 100 else (100 - latest) / slope
    return {
        "status": "estimated",
        "hours_to_full": round(hours, 1),
        "slope_pct_per_hour": round(slope, 2),
        "samples": len(points),
    }


def estimate_hosts(series, min_samples, min_span_minutes):
    """One result per host. The host takes the shortest estimate among its mount points."""
    results = {}
    for host, mounts in series.items():
        per_mount = {
            mount: estimate_mount(points, min_samples, min_span_minutes)
            for mount, points in mounts.items()
        }
        estimated = {m: r for m, r in per_mount.items() if r["status"] == "estimated"}
        if estimated:
            mount = min(estimated, key=lambda m: (estimated[m]["hours_to_full"], m))
            results[host] = dict(estimated[mount], mount=mount)
            continue
        statuses = {r["status"] for r in per_mount.values()}
        if "not enough history" in statuses:
            status = "not enough history"
        elif "not growing" in statuses:
            status = "not growing"
        else:
            status = "no disk data"
        results[host] = {"status": status, "hours_to_full": None}
    return results


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--history-dir", required=True, help="folder with audit-<run id>.json files")
    parser.add_argument("--run-id", required=True, help="run id of the current run, e.g. 20261020T103000Z")
    parser.add_argument("--window-hours", type=float, default=24, help="how far back to look (default 24)")
    parser.add_argument("--min-samples", type=int, default=3, help="samples needed for an estimate (default 3)")
    parser.add_argument(
        "--min-span-minutes", type=float, default=30, help="time the samples must cover (default 30)"
    )
    args = parser.parse_args(argv)
    try:
        args.now = parse_run_id(args.run_id)
    except ValueError:
        parser.error(f"--run-id must look like 20261020T103000Z, got {args.run_id!r}")
    return args


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        current = json.load(sys.stdin)
    except json.JSONDecodeError as error:
        print(f"error: standard input is not valid JSON: {error}", file=sys.stderr)
        return 2
    if not isinstance(current, list):
        print("error: standard input must be a JSON list of host records", file=sys.stderr)
        return 2
    samples = load_history(args.history_dir, args.now, args.window_hours)
    samples.append((args.now, current))
    results = estimate_hosts(build_series(samples), args.min_samples, args.min_span_minutes)
    json.dump(results, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
