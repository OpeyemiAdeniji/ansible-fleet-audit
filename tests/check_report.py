#!/usr/bin/env python3
"""Check that reports/latest.{csv,json,html} exist and are well formed."""
import csv
import json
import sys
from pathlib import Path

REPORTS = Path(__file__).resolve().parent.parent / "reports"
COLUMNS = [
    "host", "role", "status", "os", "cpus", "uptime_days", "load1", "mem_total_mb",
    "mem_avail_pct", "max_disk_pct", "disks", "listening_ports", "issues", "disk_full_hours", "disk_trend",
]
VALID_STATUSES = {"OK", "WARN", "CRIT", "UNREACHABLE", "ERROR"}
VALID_TRENDS = {"estimated", "not growing", "not enough history", "no disk data"}


def main():
    expected_hosts = int(sys.argv[1]) if len(sys.argv) > 1 else 1

    with open(REPORTS / "latest.csv", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == COLUMNS, f"unexpected CSV columns: {reader.fieldnames}"
        rows = list(reader)
    assert len(rows) == expected_hosts, f"expected {expected_hosts} rows, got {len(rows)}"
    for row in rows:
        assert row["status"] in VALID_STATUSES, f"bad status: {row['status']}"
        assert row["disk_trend"] in VALID_TRENDS, f"bad disk_trend: {row['disk_trend']}"

    records = json.loads((REPORTS / "latest.json").read_text())
    assert len(records) == expected_hosts, "JSON and CSV disagree on host count"
    for record in records:
        assert record["disk_trend"] in VALID_TRENDS, f"bad disk_trend: {record['disk_trend']}"
        assert "disk_full_hours" in record, "record has no disk_full_hours"

    html = (REPORTS / "latest.html").read_text()
    assert "<table>" in html and rows[0]["host"] in html, "HTML report is missing the table or hosts"

    print(f"report check passed: {len(rows)} host(s), statuses {sorted({r['status'] for r in rows})}")


if __name__ == "__main__":
    main()
