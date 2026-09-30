"""Prove backup/restore equality on the disposable release cluster."""

import argparse
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess
import sys
import uuid

from database import command
from proof import CONTEXT, evidence, ready, require


def summarize(rows):
    require(bool(rows.strip()), "Seed items and completed jobs with the HTTPS smoke test first")
    return {"rows": len(rows.splitlines()), "sha256": hashlib.sha256(rows).hexdigest()}


def verify_tables(before, current, restored):
    require(before == current == restored, "Source changed or restored rows differ; do not claim recovery success")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", choices=[CONTEXT], required=True)
    parser.add_argument("--evidence", type=Path, help="New JSON report; default: beside the retained dump")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:8]
    output = Path("backups") / f"acceptance-{stamp}.dump"
    restored = f"restore_acceptance_{stamp}"

    def fingerprints(database=""):
        result = {}
        for table in ("items", "jobs"):
            sql = f"COPY (SELECT row_to_json(t) FROM {table} t ORDER BY id) TO STDOUT"
            rows = subprocess.check_output(command(
                args.context, 'exec psql -U "$POSTGRES_USER" -d "${1:-$POSTGRES_DB}" -qAt -c "$2"',
                database, sql), timeout=60)
            result[table] = summarize(rows)
        return result

    report_path = args.evidence or output.with_suffix(".json")
    with evidence(report_path, "database-restore", args.context) as report:
        report.update(archive=str(output), destination_database=restored)
        report["readiness_before"] = ready(args.context)
        before = fingerprints()
        report["source_before"] = before
        tool = str(Path(__file__).with_name("database.py"))
        subprocess.run([sys.executable, tool, "--context", args.context, "backup", "--output", str(output)],
                       check=True, timeout=180)
        with output.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        report["archive_sha256"] = digest
        subprocess.run([sys.executable, tool, "--context", args.context, "restore", "--input", str(output),
                        "--database", restored, "--sha256", digest], check=True, timeout=180)
        report["source_after"] = fingerprints()
        report["restored"] = fingerprints(restored)
        verify_tables(before, report["source_after"], report["restored"])
        report["readiness_after"] = ready(args.context)
        report["application_cutover"] = False
    print(f"PASS: source unchanged and all restored rows match. Evidence: {report_path}", flush=True)
    print("Private dump and separate restore database retained; no application cutover performed.", flush=True)


if __name__ == "__main__":
    main()
