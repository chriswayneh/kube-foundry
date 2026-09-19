"""Prove backup/restore equality on the disposable release cluster."""

import argparse
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess
import sys

from database import command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", choices=["kind-kube-foundry-release"], required=True)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    output = Path("backups") / f"acceptance-{stamp}.dump"
    restored = f"restore_acceptance_{stamp}"

    def fingerprints(database=""):
        result = []
        for table in ("items", "jobs"):
            sql = f"COPY (SELECT row_to_json(t) FROM {table} t ORDER BY id) TO STDOUT"
            rows = subprocess.check_output(command(
                args.context, 'exec psql -U "$POSTGRES_USER" -d "${1:-$POSTGRES_DB}" -qAt -c "$2"',
                database, sql))
            assert rows.strip(), f"Seed {table} with the smoke test before this exercise"
            result.append(hashlib.sha256(rows).hexdigest())
        return result

    before = fingerprints()
    tool = str(Path(__file__).with_name("database.py"))
    subprocess.run([sys.executable, tool, "--context", args.context, "backup", "--output", str(output)], check=True)
    subprocess.run([sys.executable, tool, "--context", args.context, "restore", "--input", str(output),
                    "--database", restored], check=True)
    assert before == fingerprints() == fingerprints(restored), "Source or restored rows differ"
    print("PASS: all item/job rows match after restore; original database unchanged", flush=True)
    print("The local dump and separate restore database were retained for inspection.", flush=True)


if __name__ == "__main__":
    main()
