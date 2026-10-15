# 0002. A dynamic inventory script instead of a static file

- Status: accepted
- Date: 2026-10-15

## Context

Ansible needs to know which hosts exist and how to reach them. In the simulated fleet each container has its own published SSH port, and containers can be added or removed by editing `INCIDENTS` or `FLEET`.

## Options considered

1. **Static INI or YAML inventory**: simple and readable, but 50 hosts with ports would be written by hand or generated and kept in sync with the compose file.
2. **The `community.docker.docker_containers` inventory plugin**: no custom code, but adds a collection dependency and gives less control over grouping and connection variables.
3. **A small executable script** that reads container labels and prints JSON.

## Decision

Write `inventory/docker_inventory.py`. Groups come from the `fleet.role` label and connection details from the published port, so the compose file stays the single source of truth.

## Consequences

- Inventory always matches what is actually running. No second list to maintain.
- It demonstrates the dynamic inventory contract (`--list`, `--host`, `_meta`), which is the same contract cloud inventories use.
- It is unit tested with Docker mocked.
- Real fleets would replace `list_containers()` with a cloud API call, or use the provider's inventory plugin.
