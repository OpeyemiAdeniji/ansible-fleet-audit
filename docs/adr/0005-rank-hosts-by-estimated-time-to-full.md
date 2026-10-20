# 0005. Rank hosts by estimated time until a disk is full

- Status: accepted
- Date: 2026-10-20

## Context

The report sorts hosts by level (UNREACHABLE or ERROR, then CRIT, WARN and OK) and, inside a level, alphabetically by host name. A reader pointed out that this ranks by severity label, not by how soon someone has to act (the time to page). A stopped process is a problem now. A disk at 92 percent is not a problem yet, but it becomes the same outage when it reaches 100 percent, and how soon that happens depends on how fast the disk is filling.

One audit run is a snapshot. It shows how full a disk is, but not how fast it is filling, so it cannot tell a stable 92 percent from a 92 percent that gains 4 points an hour.

What already exists:

- Every run writes `reports/audit-<run id>.json` next to `latest.json`. The run id is the UTC time of the run, in the form `20261020T103000Z`. These files are already a history, and `reports/` is ignored by git.
- Each host record stores the usage of every audited filesystem in `disks`, as text lines such as `/ 42%`, and the highest value in `max_disk_pct`.
- `df` reports whole percentages only.
- The run time is in the file name. It is not inside the records.

## Options considered

1. **Keep alphabetical order inside a level**: predictable, but it ignores urgency completely.
2. **Rank inside a level by the current numbers only** (fullest disk first): needs no history and is simple, but it cannot tell a stable disk from a filling one.
3. **Estimate time-to-full from the saved history, with the logic in Jinja inside the role**: no extra language, but reading many files, parsing times and doing arithmetic in Jinja is hard to read and hard to test.
4. **Estimate time-to-full from the saved history, with the logic in a small Python helper that the role calls**: the logic can be unit tested with fake history files, and it needs only the Python standard library.
5. **Store history in a database or a monitoring system such as Prometheus**: more accurate and the right tool for production, but it is a different project. Project 8 (observability and SLOs) covers it with `predict_linear`.

## Decision

Option 4, with option 2 as the fallback when there is not enough history.

- **History source.** The existing `audit-<run id>.json` files in the reports folder. The run time is read from the file name. Only files from the last `audit_report_trend_window_hours` (default 24) are used, and the current run counts as the newest sample.
- **Growth rate.** For each host and mount point, fit the best straight line through the samples in the window (least squares) and take its slope in percentage points per hour. A single odd sample, such as a one-off cleanup, then moves the result less than it would if only the oldest and newest samples were used.
- **Minimum evidence.** An estimate needs at least `audit_report_trend_min_samples` (default 3) samples that span at least `audit_report_trend_min_span_minutes` (default 30). Otherwise the host gets no estimate.
- **Estimate.** Only when the slope is above zero: hours until full = (100 minus the newest usage) divided by the slope. A flat or falling disk gets no estimate. A host's estimate is the smallest one among its mount points.
- **Ranking inside a level.** In this order:
  1. hosts with a stopped required process or a closed required port first, because their time to page is already zero;
  2. then the shortest estimated time-to-full, with hosts that have no estimate after the hosts that have one;
  3. then the fullest disk, highest first;
  4. then the host name.

  UNREACHABLE and ERROR hosts have no disk data, so they stay together at the top and are sorted by host name.
- **Where the logic lives.** `scripts/estimate_disk_fill.py` reads the history folder and prints the estimates as JSON. The `audit_report` role runs it on the control node, merges the result into the records and then sorts. It uses only the Python standard library, so there is no new dependency.
- **Reports.** The HTML, CSV and JSON reports get an "estimated full in" value for each host. It is labelled as an estimate everywhere.

## Consequences

- No new storage and no new service: the history is the set of report files the tool already writes.
- The ranking logic can be tested with fake history files, without any real servers.
- The estimate only appears after several runs. The runbook has to tell the operator to run the audit on a schedule, for example every hour. The first runs show no estimate and use the fallback ranking.
- The estimate is linear and the data are whole percentages, so it is coarse over short windows. It assumes the recent growth rate continues. It is a guide for ranking, not a prediction.
- The window limits which files are read, not which files are kept. The folder still grows, so the runbook has to describe cleaning up old files. A retention setting can be added later.
- The simulated fleet shares one kernel, so every container reports the same disk. Tests use fake history, and a small demo script can generate it.
- The helper has to parse the text lines in `disks`. A structured list of mount points and percentages in the record would be cleaner, and is worth revisiting.
- A required-process or required-port failure needs a structured flag in the record. Today it exists only inside the text of `issues`.
- The CSV gains a column, so the report check in `tests/check_report.py` has to change with it.
- This covers disks only. Memory, error rates and other signals are out of scope. Revisit with Prometheus in Project 8.
