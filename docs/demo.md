# Terminal demo

The README GIF was recorded on **main after v1.1.0** on 2026-11-05
(America/Chicago). It runs only offline validation: Helm chart metadata, chart
lint, rendered shop manifests, and `kubectl kustomize` over the GitOps overlays.
No kind cluster is created, no images are pulled, and no cloud credentials or
real hostnames are used. Timing is adjusted for README readability.

## What it shows

1. `helm show chart charts/shop` — real chart metadata from the checkout.
2. `make check-chart` — `helm lint charts/shop` and render checks.
3. `make validate` — kustomize render of GitOps/phase overlays plus `compileall`
   for the sample app and scripts.

## Run it yourself

Needs GNU Make, Helm, kubectl, and Python 3 (no Docker daemon required for this
path):

```bash
git clone --branch v1.1.0 --depth 1 https://github.com/chriswayneh/kube-foundry.git
cd kube-foundry
make check-chart
make validate
```

Do not run `make cluster` or `make install` for this demo. Those need Docker,
kind, and roughly 16 GB of memory; they are covered in the [Quick start](../README.md#quick-start).

## Re-record the GIF

Requires [vhs](https://github.com/charmbracelet/vhs) (and `ttyd`), Make, Helm,
and kubectl:

```bash
./scripts/record-demo.sh
```

The script stages a throwaway directory with `mktemp -d`, records
`docs/assets/demo.gif` from `scripts/demo.tape`, and never starts kind or other
containers.

## Text alternative

The [Quick start](../README.md#quick-start) and [Run v1.1](../README.md#run-v11)
sections describe the full local platform path.
