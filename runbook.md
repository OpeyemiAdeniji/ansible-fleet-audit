# Fleet audit runbook

How to run the audit, read the report, and respond to each kind of finding.

## 1. Run the audit

```bash
make ping      # optional: quick connectivity check across the fleet
make audit     # full audit, writes reports/latest.{html,csv,json}
```

To make a scheduler or pipeline fail when something is wrong:

```bash
make audit-strict    # exits non-zero if any host is CRIT, UNREACHABLE or ERROR
```

Useful variations:

| Goal | Command |
|---|---|
| Audit one role | `ansible-playbook playbooks/audit.yml --limit web` |
| Audit one host | `ansible-playbook playbooks/audit.yml --limit web-07` |
| Run with fewer parallel hosts | `ansible-playbook playbooks/audit.yml -f 5` |
| Stricter disk threshold for this run | `ansible-playbook playbooks/audit.yml -e disk_warn_pct=70` |

When you use `--limit`, the report only contains the hosts you selected.

## 2. Read the report

Open `reports/latest.html`. Hosts are sorted worst first.

| Status | Meaning | Urgency |
|---|---|---|
| UNREACHABLE | Ansible could not open an SSH connection | Investigate now: this host is unmonitored |
| ERROR | Connected, but one of the audit commands failed | Investigate: the host is monitored blind |
| CRIT | A critical threshold or expectation is breached | Act now |
| WARN | A warning threshold is breached | Act soon, before it becomes CRIT |
| OK | Everything within limits | None |

The `Issues` column says exactly what tripped. The CSV has the same data for sorting in a spreadsheet.

## 3. What to do for each finding

### UNREACHABLE

1. Run `ansible <host> -m ansible.builtin.ping -vvv` and read the connection error.
2. Is the machine up? Check the hypervisor, cloud console, or `docker ps` for the simulated fleet.
3. Is sshd running? Is the SSH port open (firewall, security group)?
4. Is the key accepted? Look for "Permission denied (publickey)".
5. Restore access, re-run the audit for that host: `--limit <host>`.

### ERROR

1. Run the playbook with `--limit <host> -vv` and find the failing task.
2. The usual cause is a missing tool (`ss`, `ps`) or a full disk stopping commands from running.

### CRIT: disk

1. Find what is using the space: `du -xh --max-depth=1 <mount> | sort -h | tail`.
2. Typical culprits: logs, old releases, package caches, core dumps.
3. Free space or grow the volume. Rotate or ship logs so it does not recur.
4. Re-audit that host.

### CRIT: process not running

1. Check the service state and its recent logs (`systemctl status <name>`, `journalctl -u <name>`).
2. Restart it. If it dies again, read the last error before restarting repeatedly.
3. Find out why it stopped: out of memory, bad config, dependency down.

### CRIT: port not listening

1. The process may be running but bound to the wrong address or port. Check with `ss -ltnp`.
2. Check the service configuration for the expected port.

### WARN: disk

Treat it as the early warning for the CRIT steps above. Decide now whether to clean up or expand.

### WARN: available memory low

1. `ps aux --sort=-%mem | head` to find the biggest users.
2. Look for a leak (memory growing since the last restart) versus an under-sized host.

### WARN: high load per CPU

1. `top` or `uptime` to see whether load is rising or already falling.
2. Sustained load above 1 per CPU means the host is saturated. Find the busy process, then scale or tune.

## 4. Change what counts as a problem

Edit `playbooks/group_vars/all.yml` for thresholds and `web.yml`, `app.yml` or `db.yml` for what each role must be running. Commit the change through a pull request.

## 5. Add a new check

1. Add a command task in `playbooks/audit.yml` that registers its output.
2. Turn the output into a number or list in the "Turn raw command output" step.
3. Add a threshold to `group_vars/all.yml` and a rule in the "List critical problems" or "List warnings" step.
4. Add a column to `report.csv.j2` and `report.html.j2` if it should be visible.

## 6. Troubleshooting the tool itself

| Symptom | Likely cause and fix |
|---|---|
| `No hosts in group 'fleet'` | The fleet is not running. `make fleet-up`. |
| `docker_inventory: cannot query Docker` | Docker is not running or your user cannot use it. |
| Every host UNREACHABLE | Missing or wrong SSH key. Run `make keys`, then `make fleet-up` to rebuild the image. |
| `Permission denied` running the inventory script | Lost the executable bit: `chmod +x inventory/docker_inventory.py`. |
| Run is slow | Raise `forks` in `ansible.cfg`, or check for many dead hosts (each costs up to the 10 s timeout). |
