#!/usr/bin/env python3
"""Check that reports/latest.{csv,json,html} exist and are well formed."""
import csv
import json
import sys
from pathlib import Path

REPORTS = Path(__file__).resolve().parent.parent / "reports"
COLUMNS = [
    "host", "role", "status", "os", "cpus", "uptime_days", "load1", "mem_total_mb",
    "mem_avail_pct", "max_disk_pct", "disks", "listening_ports", "issues",
]
VALID_STATUSES = {"OK", "WARN", "CRIT", "UNREACHABLE", "ERROR"}


def main():
    expected_hosts = int(sys.argv[1]) if len(sys.argv) > 1 else 1

    with open(REPORTS / "latest.csv", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == COLUMNS, f"unexpected CSV columns: {reader.fieldnames}"
        rows = list(reader)
    assert len(rows) == expected_hosts, f"expected {expected_hosts} rows, got {len(rows)}"
    for row in rows:
        assert row["status"] in VALID_STATUSES, f"bad status: {row['status']}"

    records = json.loads((REPORTS / "latest.json").read_text())
    assert len(records) == expected_hosts, "JSON and CSV disagree on host count"

    html = (REPORTS / "latest.html").read_text()
    assert "<table>" in html and rows[0]["host"] in html, "HTML report is missing the table or hosts"

    print(f"report check passed: {len(rows)} host(s), statuses {sorted({r['status'] for r in rows})}")


if __name__ == "__main__":
    main()
