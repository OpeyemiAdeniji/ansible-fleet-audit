# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Simulated 50-host fleet (20 web, 20 app, 10 db) as Docker containers with SSH, with seeded incidents.
- Dynamic inventory script that groups hosts by role from container labels.
- Audit playbook: disk, memory, load, uptime, OS, running processes and listening ports, with thresholds.
- Handling for unreachable hosts and hosts whose audit failed.
- CSV, HTML and JSON reports, worst hosts first.
- Runbook, architecture decision records, CI, and unit and end-to-end tests.
