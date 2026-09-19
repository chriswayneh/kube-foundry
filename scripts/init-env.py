"""Create local runtime credentials without replacing an existing file."""

import argparse
import os
import secrets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=".env")
    args = parser.parse_args()
    contents = ("POSTGRES_DB=kube_foundry\nPOSTGRES_USER=kube_foundry\n"
                f"POSTGRES_PASSWORD={secrets.token_hex(24)}\n"
                f"REDIS_PASSWORD={secrets.token_hex(24)}\n")
    try:
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise SystemExit("Credentials file already exists; it was not changed.") from None
    with os.fdopen(descriptor, "w", newline="\n") as handle:
        handle.write(contents)
    print("Created local credentials. Keep the file private and outside Git.")


if __name__ == "__main__":
    main()
