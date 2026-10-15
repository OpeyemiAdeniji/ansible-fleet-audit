.DEFAULT_GOAL := help
FLEET_COMPOSE := fleet/docker-compose.yml

.PHONY: help setup keys fleet-up fleet-status fleet-down inventory ping audit audit-strict test unit lint clean

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

setup: ## Install Ansible, ansible-lint, pre-commit and git hooks (inside a virtualenv)
	@test -n "$$VIRTUAL_ENV" || (echo 'Activate the virtualenv first: python3 -m venv .venv && source .venv/bin/activate'; exit 1)
	pip install -r requirements.txt pre-commit
	pre-commit install --install-hooks
	pre-commit install --hook-type commit-msg

keys: ## Create the SSH key pair used by the simulated fleet (once)
	@test -f fleet/ssh/id_fleet || (mkdir -p fleet/ssh && ssh-keygen -q -t ed25519 -N "" -C fleet-audit -f fleet/ssh/id_fleet && echo "created fleet/ssh/id_fleet")

fleet-up: keys ## Build the image and start the 50-host simulated fleet
	python3 scripts/generate_fleet.py
	docker build -t fleet-node:latest fleet
	docker compose -f $(FLEET_COMPOSE) up -d

fleet-status: ## Show how many fleet containers are running
	@docker ps --filter label=fleet.audit=true --format '{{.Names}}' | wc -l | xargs echo "running containers:"

fleet-down: ## Stop and remove the simulated fleet
	docker compose -f $(FLEET_COMPOSE) down

inventory: ## Print the dynamic inventory as a group tree
	ansible-inventory --graph

ping: ## Check SSH connectivity to every host (unreachable hosts show up here)
	ansible fleet -m ansible.builtin.ping

audit: ## Run the fleet audit and write reports/latest.{html,csv,json}
	ansible-playbook playbooks/audit.yml

audit-strict: ## Same as audit, but exit non-zero if any host is CRIT/UNREACHABLE/ERROR
	ansible-playbook playbooks/audit.yml -e fail_on_critical=true

unit: ## Run the inventory unit tests (no Docker needed)
	python3 -m unittest discover -s tests -v

test: unit ## Run lint, syntax check, unit tests and a local end-to-end audit
	ansible-lint
	ansible-playbook -i tests/inventory-local.yml playbooks/audit.yml --syntax-check
	bash tests/run_local_audit.sh

lint: ## Run every pre-commit hook against all files
	pre-commit run --all-files

clean: ## Remove generated reports
	rm -rf reports
