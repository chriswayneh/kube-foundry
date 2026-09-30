"""Back up shop, or restore a trusted dump into a new, isolated database."""

import argparse
import hashlib
from pathlib import Path
import re
import subprocess


def restore_name(value):
    if not re.fullmatch(r"restore_[a-z0-9_]{1,48}", value):
        raise argparse.ArgumentTypeError("Use restore_<lowercase_name>; existing application databases are forbidden")
    return value


def command(context, script, *args, stdin=False):
    return ["kubectl", "--context", context, "-n", "shop", "exec", *(["-i"] if stdin else []),
            "postgres-0", "--", "sh", "-c", script, "--", *args]


def open_archive(path, expected_sha256=None):
    # Keep the inherited OS file offset aligned after header validation.
    handle = path.open("rb", buffering=0)
    if handle.read(5) != b"PGDMP":
        handle.close()
        raise ValueError("Not a PostgreSQL custom-format archive")
    handle.seek(0)
    if expected_sha256 is not None:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
        if digest != expected_sha256:
            handle.close()
            raise ValueError("Archive checksum mismatch; destination database was not created")
        handle.seek(0)
    return handle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True, help="Explicit destination cluster context")
    commands = parser.add_subparsers(dest="operation", required=True)
    backup = commands.add_parser("backup")
    backup.add_argument("--output", type=Path, required=True)
    restore = commands.add_parser("restore")
    restore.add_argument("--input", type=Path, required=True)
    restore.add_argument("--database", type=restore_name, required=True)
    restore.add_argument("--sha256", help="Verify against a trusted backup checksum before creating the database")
    args = parser.parse_args()
    if args.operation == "backup":
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive create avoids accidentally replacing another backup.
        with args.output.open("xb") as handle:
            subprocess.run(command(args.context,
                                   'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-acl'),
                           stdout=handle, check=True)
        with args.output.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        print(f"Backup complete: {args.output}; SHA256 {digest}. Contains private application data.")
    else:
        with open_archive(args.input, args.sha256) as handle:
            subprocess.run(command(args.context, 'exec createdb -U "$POSTGRES_USER" "$1"', args.database),
                           check=True)
            subprocess.run(command(args.context,
                                   'exec pg_restore -U "$POSTGRES_USER" -d "$1" --no-owner --no-acl '
                                   '--exit-on-error --single-transaction', args.database, stdin=True),
                           stdin=handle, check=True)
        print(f"Restored into new database {args.database}; the application database was not changed.")


if __name__ == "__main__":
    main()
