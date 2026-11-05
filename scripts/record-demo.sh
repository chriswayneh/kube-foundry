#!/usr/bin/env bash
# Re-record docs/assets/demo.gif from offline kube-foundry validate (no kind cluster).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/kube-foundry-demo-XXXXXX")"
WORK="$STAGE/work"

cleanup() { rm -rf "$STAGE"; }
trap cleanup EXIT

command -v vhs >/dev/null || { echo "vhs is required" >&2; exit 1; }
command -v ttyd >/dev/null || { echo "ttyd is required by vhs" >&2; exit 1; }
command -v make >/dev/null || { echo "make is required" >&2; exit 1; }
command -v helm >/dev/null || { echo "helm is required" >&2; exit 1; }
command -v kubectl >/dev/null || { echo "kubectl is required" >&2; exit 1; }

mkdir -p "$WORK"
cp "$ROOT/scripts/demo.tape" "$WORK/demo.tape"

BIN="$STAGE/bin"
mkdir -p "$BIN"
ln -sf "$(command -v make)" "$BIN/make"
ln -sf "$(command -v helm)" "$BIN/helm"
ln -sf "$(command -v kubectl)" "$BIN/kubectl"
ln -sf "$(command -v git)" "$BIN/git"
ln -sf "$(command -v python3)" "$BIN/python3"
ln -sf "$(command -v python3)" "$BIN/python"

export KF_BIN_DIR="$BIN"
export KF_DEMO_HOME="$ROOT"
export PATH="$KF_BIN_DIR:$PATH"

# Offline sanity: chart lint + kustomize render only. Never create a kind cluster.
unset KUBECONFIG AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY GOOGLE_APPLICATION_CREDENTIALS || true
make -C "$ROOT" validate >/dev/null

( cd "$WORK" && vhs demo.tape )

mkdir -p "$ROOT/docs/assets"
cp "$WORK/demo.gif" "$ROOT/docs/assets/demo.gif"
echo "Wrote $ROOT/docs/assets/demo.gif"
