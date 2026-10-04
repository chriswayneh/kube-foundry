"""Reject stale or mixed-scope image promotion pull requests."""

import argparse
import importlib.util
from pathlib import Path
import re
import subprocess


OVERLAY = "gitops/apps/shop/phase8/dev/kustomization.yaml"
spec = importlib.util.spec_from_file_location("delivery_updater", Path(__file__).with_name("update-images.py"))
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


def verify(paths, content, base, render=updater.render):
    if OVERLAY not in paths:
        return False
    if paths != [OVERLAY]:
        raise ValueError("Image promotion must be a separate PR changing only the dev image overlay")
    if content != render(base):
        raise ValueError("Promotion must contain the anonymously verified images for the current PR base")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args()
    if not all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in (args.base, args.head)):
        raise SystemExit("Expected full Git commit SHAs")
    paths = subprocess.check_output(
        ["git", "diff", "--name-only", args.base, args.head], text=True).splitlines()
    content = ""
    if OVERLAY in paths:
        content = subprocess.check_output(["git", "show", f"{args.head}:{OVERLAY}"], text=True)
    try:
        changed = verify(paths, content, args.base)
    except (ValueError, OSError) as error:
        raise SystemExit(f"Delivery validation failed: {error}") from None
    print("PASS: current-base image promotion verified" if changed else "PASS: no image promotion in this PR")


if __name__ == "__main__":
    main()
