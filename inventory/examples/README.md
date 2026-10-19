# Cloud inventory examples

**Not exercised in this repository.** These files show how the audit would find hosts in real clouds. They have never been run here, because no cloud account is attached to this project yet. Treat them as a design sketch, and check each plugin's documentation before use.

Every example does the same three things:

1. Authenticates with a **short-lived identity** (assumed role, managed identity, service account), never a stored access key. See [ADR 0004](../../docs/adr/0004-no-long-lived-cloud-credentials.md).
2. Puts every host in the `fleet` group.
3. Puts each host in a `web`, `app` or `db` group, taken from a `Role` tag or label, so the audit roles work unchanged.

| File | Cloud | Plugin |
|---|---|---|
| [`aws_ec2.yml`](aws_ec2.yml) | AWS | [`amazon.aws.aws_ec2`](https://docs.ansible.com/ansible/latest/collections/amazon/aws/aws_ec2_inventory.html) |
| [`azure_rm.yml`](azure_rm.yml) | Azure | [`azure.azcollection.azure_rm`](https://docs.ansible.com/ansible/latest/collections/azure/azcollection/azure_rm_inventory.html) |
| [`gcp_compute.yml`](gcp_compute.yml) | GCP | [`google.cloud.gcp_compute`](https://docs.ansible.com/ansible/latest/collections/google/cloud/gcp_compute_inventory.html) |

Try one with `ansible-inventory -i inventory/examples/aws_ec2.yml --graph` after installing the collection and signing in with a role.
