# 0004. No long-lived cloud credentials

- Status: accepted
- Date: 2026-10-18

## Context

The audit is built to run against a simulated fleet today and against real cloud hosts later (AWS, Azure, GCP). Ansible needs two kinds of access in the cloud: to **list** hosts (inventory plugins call the cloud API) and to **reach** hosts (usually SSH). A stored access key or client secret for either one is a secret that can leak from a laptop, a repository or a CI log, and that nobody remembers to rotate.

## Options considered

1. **Access keys or client secrets in environment variables or files**: simple and works everywhere, but the credential is long-lived and valuable if stolen.
2. **Short-lived identity**: Ansible runs as an identity the cloud already trusts (instance profile, managed identity, attached service account) or signs in through workload identity federation (OIDC from CI). The cloud issues credentials that expire in about an hour. Nothing secret is stored.
3. **A secrets manager that hands out the keys**: better storage, but there is still a long-lived key behind it.

## Decision

Option 2. The inventory examples in `inventory/examples/` use an assumed role (AWS `iam_role_arn`), a managed identity (Azure `auth_source: msi`) and the attached service account (GCP `auth_kind: machineaccount`). The identity gets read-only permissions for listing hosts and nothing more. For CI, GitHub Actions signs in over OIDC (the pattern planned for a later project in this portfolio).

For reaching hosts, the preferred order is: cloud-native sessions with no SSH key (AWS Systems Manager Session Manager, GCP OS Login with IAP, Azure Bastion), then short-lived SSH certificates, and only last a key pair. The key baked into the simulated fleet image is a throwaway and is noted as such in the README.

The examples are **not exercised** in this repository yet. Real runs are planned in stages: AWS first, then Azure, then GCP.

## Consequences

- No access key ever needs to exist in the repo, in CI secrets or on a laptop, and gitleaks has nothing to find.
- Setup is harder: the identity, its trust relationship and a minimal policy must be created per cloud.
- The control node must itself run somewhere that has an identity (a cloud VM, or CI with OIDC). Running from a laptop needs a short-lived sign-in such as `aws sso login`.
- The audit roles do not change. Only the inventory file differs per cloud, because the roles only need hosts in `fleet` plus a role group.
