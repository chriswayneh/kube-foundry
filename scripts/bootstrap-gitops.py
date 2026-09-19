"""Pin the root and both child Applications to one Git revision."""

import argparse
import json
import subprocess


def pinned_root(root, revision):
    root["spec"]["source"]["targetRevision"] = revision
    patches = []
    for name, paths in [("shop-dev", ["/spec/source/targetRevision"]),
                        ("platform", [f"/spec/sources/{i}/targetRevision" for i in range(3)])]:
        patches.append({"target": {"kind": "Application", "name": name},
                        "patch": json.dumps([{"op": "replace", "path": path, "value": revision}
                                             for path in paths])})
    root["spec"]["source"]["kustomize"] = {"patches": patches}
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    root = json.loads(subprocess.check_output(
        ["kubectl", "create", "--dry-run=client", "-f", "gitops/root-app.yaml", "-o", "json"], text=True))
    subprocess.run(["kubectl", "apply", "-f", "-"], input=json.dumps(pinned_root(root, args.revision)),
                   text=True, check=True)


if __name__ == "__main__":
    main()
