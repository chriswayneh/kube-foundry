# kind cluster

`cluster.yaml` creates one control-plane and two workers using kind 0.33.0 and a digest-pinned Kubernetes 1.37.0 node image. Helm 3.22.0 installs the CNI. That file publishes host ports 80 and 443 and does not set `listenAddress`, so kind binds them on all interfaces (`0.0.0.0`). The shop Gateway is a ClusterIP Service and is not attached to those ports; they are unused, not a loopback bind. Host access is a loopback port-forward on 8080/8443, so existing clusters do not need to be recreated. `verification.yaml` omits the mappings. See [host access](../../docs/traffic.md).

The default kind CNI is disabled because kindnet does not enforce NetworkPolicy. `make cluster` installs the pinned Cilium 1.20.2 OCI Helm chart before waiting for nodes. If creating manually, install the same chart and then wait:

```bash
kind create cluster --name kube-foundry --config clusters/kind/cluster.yaml
helm upgrade --install cilium oci://quay.io/cilium/charts/cilium --version 1.20.2 \
  --namespace kube-system --set image.pullPolicy=IfNotPresent --set ipam.mode=kubernetes
kubectl wait --for=condition=Ready nodes --all --timeout=180s
```
