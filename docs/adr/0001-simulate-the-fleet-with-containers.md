# 0001. Simulate the fleet with containers

- Status: accepted
- Date: 2026-10-15

## Context

The audit needs a fleet to run against, ideally around 50 hosts, that anyone can recreate for free and that includes realistic failures. The project must be reproducible by a reviewer with a laptop.

## Options considered

1. **Real cloud VMs** (for example EC2): most realistic, but costs money, needs credentials, and cannot be reproduced by a reviewer without an account.
2. **Local VMs** (Vagrant or Multipass): realistic systemd behaviour, but 50 VMs are far too heavy for a laptop.
3. **Docker containers running sshd**: light enough for 50 hosts, free, starts in seconds, and failures are easy to inject.

## Decision

Use Docker containers running sshd, defined by one image whose behaviour is chosen by environment variables, and a generator script that writes the compose file.

## Consequences

- Anyone can run the whole project with `make fleet-up`.
- Faults (full disk, dead service, no SSH) are one line each in `scripts/generate_fleet.py`.
- Containers share the host kernel, so memory, load and root disk values are the host's. Disk variety comes from a small per-container `/data` volume. Documented in the README.
- No systemd, so services are checked by process and port. A real-VM service check can be added later.
- The Ansible code is the same code that would run against real servers: only the inventory source changes.
