"""Unit tests for the dynamic inventory script. No Docker needed: Docker is mocked."""
import importlib.util
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "inventory" / "docker_inventory.py"
spec = importlib.util.spec_from_file_location("docker_inventory", SCRIPT)
docker_inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docker_inventory)


def fake_container(hostname, role, port):
    """Build the slice of `docker inspect` output the script reads."""
    ports = {"22/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(port)}]} if port else {}
    return {
        "Config": {"Hostname": hostname, "Labels": {"fleet.role": role} if role else {}},
        "NetworkSettings": {"Ports": ports},
    }


class BuildInventoryTests(unittest.TestCase):
    def test_hosts_are_grouped_by_role_label(self):
        inv = docker_inventory.build_inventory(
            [fake_container("web-01", "web", 2201), fake_container("db-01", "db", 2202)]
        )
        self.assertEqual(inv["web"]["hosts"], ["web-01"])
        self.assertEqual(inv["db"]["hosts"], ["db-01"])

    def test_fleet_group_contains_every_role_group(self):
        inv = docker_inventory.build_inventory(
            [fake_container("web-01", "web", 2201), fake_container("app-01", "app", 2202)]
        )
        self.assertEqual(inv["fleet"]["children"], ["app", "web"])

    def test_hostvars_carry_address_and_published_port(self):
        inv = docker_inventory.build_inventory([fake_container("web-01", "web", 2299)])
        self.assertEqual(
            inv["_meta"]["hostvars"]["web-01"],
            {"ansible_host": "127.0.0.1", "ansible_port": 2299},
        )

    def test_hosts_are_sorted_by_name(self):
        inv = docker_inventory.build_inventory(
            [fake_container("web-02", "web", 2202), fake_container("web-01", "web", 2201)]
        )
        self.assertEqual(inv["web"]["hosts"], ["web-01", "web-02"])

    def test_container_without_role_label_goes_to_unknown_group(self):
        inv = docker_inventory.build_inventory([fake_container("x-01", None, 2201)])
        self.assertEqual(inv["unknown"]["hosts"], ["x-01"])

    def test_container_without_published_ssh_port_is_skipped(self):
        inv = docker_inventory.build_inventory([fake_container("web-01", "web", None)])
        self.assertNotIn("web", inv)
        self.assertEqual(inv["_meta"]["hostvars"], {})

    def test_empty_fleet_gives_valid_empty_inventory(self):
        inv = docker_inventory.build_inventory([])
        self.assertEqual(inv["fleet"]["children"], [])
        self.assertEqual(inv["_meta"]["hostvars"], {})


class CommandLineTests(unittest.TestCase):
    def run_main(self, argv, containers=None):
        buffer = io.StringIO()
        with mock.patch.object(docker_inventory, "list_containers", return_value=containers or []):
            with redirect_stdout(buffer):
                code = docker_inventory.main(argv)
        return code, buffer.getvalue()

    def test_list_prints_json(self):
        code, out = self.run_main(["--list"], [fake_container("web-01", "web", 2201)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["web"]["hosts"], ["web-01"])

    def test_host_prints_empty_object(self):
        code, out = self.run_main(["--host", "web-01"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {})

    def test_docker_failure_returns_nonzero(self):
        with mock.patch.object(docker_inventory, "list_containers", side_effect=OSError("no docker")):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(docker_inventory.main(["--list"]), 1)


if __name__ == "__main__":
    unittest.main()
