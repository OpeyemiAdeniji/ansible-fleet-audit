#!/usr/bin/env bash
# End-to-end test without Docker: run the real playbook against the local machine, then
# check the reports. The local host plays the "web" role, so we clear the role expectations
# (nginx and port 80 will not exist on a CI runner) and only test that the pipeline works.
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf reports
ansible-playbook -i tests/inventory-local.yml playbooks/audit.yml \
    -e '{"audit_host_expected_processes": [], "audit_host_expected_ports": []}'
python3 tests/check_report.py 1
