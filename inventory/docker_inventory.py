#!/usr/bin/env python3
"""Ansible dynamic inventory for the simulated fleet.

Ansible runs this script with `--list` and expects a JSON document on stdout.
The script asks Docker for every running container labelled `fleet.audit=true`,
reads its `fleet.role` label, and builds these groups:

    web, app, db   one group per role, holding that role's hosts
    fleet          parent group whose children are the role groups

Each host is reachable at 127.0.0.1 on the SSH port Docker published for it.
With a real fleet you would swap `list_containers()` for a cloud API call
(for example the EC2 API) and keep everything else the same.
"""
import argparse
import json
import subprocess
import sys

FLEET_LABEL = "fleet.audit=true"
ROLE_LABEL = "fleet.role"


def docker(*args):
    """Run a docker command and return its stdout, raising on failure."""
    result = subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=True
    )
    return result.stdout


def list_containers():
    """Return `docker inspect` data for every running fleet container."""
    ids = docker("ps", "--quiet", "--filter", f"label={FLEET_LABEL}").split()
    if not ids:
        return []
    return json.loads(docker("inspect", *ids))


def ssh_port(container):
    """Return the host port Docker published for the container's port 22, or None."""
    bindings = container["NetworkSettings"]["Ports"].get("22/tcp") or []
    return int(bindings[0]["HostPort"]) if bindings else None


def build_inventory(containers):
    """Turn container metadata into Ansible's dynamic inventory JSON structure."""
    inventory = {"_meta": {"hostvars": {}}, "fleet": {"children": []}}

    for container in sorted(containers, key=lambda c: c["Config"]["Hostname"]):
        name = container["Config"]["Hostname"]
        role = container["Config"]["Labels"].get(ROLE_LABEL, "unknown")
        port = ssh_port(container)
        if port is None:
            continue  # no published SSH port, so Ansible could never reach it

        inventory.setdefault(role, {"hosts": []})["hosts"].append(name)
        inventory["_meta"]["hostvars"][name] = {
            "ansible_host": "127.0.0.1",
            "ansible_port": port,
        }

    inventory["fleet"]["children"] = sorted(
        group for group in inventory if group not in ("_meta", "fleet")
    )
    return inventory


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true", help="print the full inventory")
    mode.add_argument("--host", help="print variables for one host")
    args = parser.parse_args(argv)

    if args.host:
        # `_meta` already carries every host's variables, so Ansible does not
        # need per-host calls. Returning an empty object is the documented answer.
        print(json.dumps({}))
        return 0

    try:
        inventory = build_inventory(list_containers())
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"docker_inventory: cannot query Docker: {error}", file=sys.stderr)
        return 1
    print(json.dumps(inventory, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
