#!/usr/bin/env sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
output=gitops/apps/shop/base/shop.yaml
rendered=$(mktemp)
trap 'rm -f "$rendered"' EXIT
trap 'exit 1' INT TERM
helm template shop charts/shop --namespace shop >"$rendered"
case "${1:-}" in
  --check)
    if ! diff -u "$output" "$rendered"; then
      echo 'Rendered base is stale. Run make render-shop and commit the result.' >&2
      exit 1
    fi
    ;;
  '') cp "$rendered" "$output" ;;
  *) echo 'Usage: render-shop.sh [--check]' >&2; exit 2 ;;
esac
