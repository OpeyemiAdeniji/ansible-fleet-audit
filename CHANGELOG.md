# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Ansible roles: `audit_host` (collect and judge one host) and `audit_report` (build the reports).
- Example inventories for AWS, Azure and GCP using short-lived identity, clearly marked as not exercised here.
- ADR 0004: no long-lived cloud credentials.

### Changed
- `playbooks/audit.yml` is now two short plays that call the roles.
- Variables are prefixed with their role name (`audit_host_*`, `audit_report_*`). For example `disk_warn_pct` is now `audit_host_disk_warn_pct`, and `fail_on_critical` is now `audit_report_fail_on_critical`.
- Report templates moved to `playbooks/roles/audit_report/templates/`.

## [0.1.0] - 2026-10-15

### Added
- Simulated 50-host fleet (20 web, 20 app, 10 db) as Docker containers with SSH, with seeded incidents.
- Dynamic inventory script that groups hosts by role from container labels.
- Audit playbook: disk, memory, load, uptime, OS, running processes and listening ports, with thresholds.
- Handling for unreachable hosts and hosts whose audit failed.
- CSV, HTML and JSON reports, worst hosts first.
- Runbook, architecture decision records, CI, and unit and end-to-end tests.
