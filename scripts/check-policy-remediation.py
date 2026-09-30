"""Prove admission rejection and corrected admission without persisting workloads."""

import argparse
import copy
import uuid

from proof import CONTEXT, evidence, get, kubectl, require


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", choices=[CONTEXT], required=True)
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args()
    with evidence(args.evidence, "policy-remediation", args.context) as report:
        live = get(args.context, "shop", "deployment", "api")
        name = "policy-proof-" + uuid.uuid4().hex[:10]
        fixed = {"apiVersion": "apps/v1", "kind": "Deployment",
                 "metadata": {"name": name, "namespace": "shop"},
                 "spec": {"selector": {"matchLabels": {"proof": name}},
                          "template": copy.deepcopy(live["spec"]["template"])}}
        fixed["spec"]["template"]["metadata"] = {"labels": {"proof": name}}
        bad = copy.deepcopy(fixed)
        del bad["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]["cpu"]
        rejected = kubectl(args.context, "create", "--dry-run=server", "-f", "-", data=bad)
        require(rejected.returncode != 0 and "require-resources" in rejected.stderr,
                "Expected require-resources policy denial, not a network/authentication failure")
        accepted = kubectl(args.context, "create", "--dry-run=server", "-f", "-", data=fixed)
        accepted.check_returncode()
        report.update(policy="shop-workloads", rule="require-resources",
                      denial=next(line.strip() for line in rejected.stderr.splitlines()
                                  if "require-resources" in line),
                      rejected_field="spec.template.spec.containers[0].resources.limits.cpu",
                      remediation="restore the CPU limit from the compliant API workload",
                      denied=True, corrected_admission=True, dry_run=True)
    print("PASS: missing CPU limit denied; corrected workload admitted by server dry-run; policy unchanged")


if __name__ == "__main__":
    main()
