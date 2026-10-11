"""Publish a reviewed-delivery branch without writing protected main."""

import argparse
import os
from pathlib import Path
import re
import subprocess


OVERLAY = "gitops/apps/shop/phase8/dev/kustomization.yaml"


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def require_current(revision):
    git("fetch", "--no-tags", "origin", "main")
    if git("rev-parse", "FETCH_HEAD") != revision:
        raise ValueError("Main advanced; leave the previous deployment unchanged and publish current main.")


def prepare(revision):
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Expected a full lowercase Git commit SHA")
    require_current(revision)
    if git("rev-parse", "HEAD") != revision:
        raise ValueError("Checkout must match the published source revision")
    if git("diff", "--cached", "--name-only"):
        raise ValueError("Unexpected staged changes")
    changes = git("diff", "--name-only").splitlines()
    if not changes:
        return None
    if changes != [OVERLAY]:
        raise ValueError("Delivery must change only the development image overlay")
    branch = f"delivery/dev-{revision}"
    git("checkout", "-b", branch)
    git("add", "--", OVERLAY)
    git("commit", "-m", f"Promote scanned development images from {revision}")
    require_current(revision)
    reference = f"refs/heads/{branch}"
    if git("ls-remote", "--heads", "origin", reference):
        git("fetch", "--no-tags", "origin", reference)
        if (git("rev-parse", "FETCH_HEAD^@") != revision
                or git("rev-parse", "FETCH_HEAD^{tree}") != git("rev-parse", "HEAD^{tree}")):
            raise ValueError("Existing delivery branch differs; do not overwrite it")
    else:
        git("push", "origin", f"HEAD:{reference}")
    return branch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    repository = os.environ.get("GITHUB_REPOSITORY", "chriswayneh/kube-foundry")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise SystemExit("Invalid repository name")
    try:
        branch = prepare(args.revision)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    message = "Development image digests already match; no promotion is needed."
    if branch:
        url = f"https://github.com/{repository}/compare/main...{branch}?expand=1"
        message = (f"Delivery branch: {branch}\nOpen a reviewed promotion PR: {url}\n"
                   "A maintainer must open the PR so required CI runs. Do not push directly to main.")
    print(message)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write(message + "\n")


if __name__ == "__main__":
    main()
