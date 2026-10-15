# 0003. Collect on each host, aggregate on the control node

- Status: accepted
- Date: 2026-10-15

## Context

Each host's data must end up in one report, including hosts that could not be reached. The run must survive dead hosts without aborting or stalling.

## Options considered

1. **One play that appends every host's result to a file** (for example with `lineinfile` or `delegate_to: localhost`): parallel hosts writing one file need locking and give inconsistent ordering.
2. **Collect in one play, aggregate in a second play on localhost**: each host stores a result in its own variable, and a single task later reads all of them from `hostvars`.
3. **Write a custom callback plugin** that builds the report: powerful but hides the logic from readers.

## Decision

Two plays. The first runs on every host and builds an `audit` record per host. The second runs on `localhost`, reads `hostvars`, and renders the CSV, HTML and JSON from templates. The ping task uses `ignore_unreachable`, and the collection tasks are skipped for hosts that did not answer.

## Consequences

- No concurrent writes: the report is built once, by one task.
- Unreachable hosts and hosts with failed tasks still appear in the report, with a clear status.
- Thresholds and report layout are plain Jinja and YAML, readable without Ansible internals.
- Records only live in memory for the run, so history means keeping the timestamped report files.
