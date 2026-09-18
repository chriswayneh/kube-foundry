# Failure exercises

## Forced readiness failure (phase 2)

Purpose: demonstrate that a bad configuration makes the Pod unready instead of serving traffic.

```bash
kubectl -n shop patch configmap shop-config --type merge -p '{"data":{"APP_CONFIGURED":"false"}}'
kubectl -n shop rollout restart deployment/api
kubectl -n shop get pods -w
kubectl -n shop describe pod -l app.kubernetes.io/component=api
```

Expected observation: the container starts and remains live, `/readyz` returns 503 with `configuration: failed`, the readiness probe reports failure, and the Pod is removed from Service endpoints. Recover with:

```bash
kubectl apply -k clusters/kind/manifests/phase2
kubectl -n shop rollout restart deployment/api
kubectl -n shop rollout status deployment/api
```

**Observed 2026-09-17:** the replacement Pod remained `0/1 Running` with zero restarts, proving liveness was unaffected while readiness failed. A direct port-forward to that Pod returned HTTP 503 and `{"detail":{"configuration":"failed"}}`. Reapplying the phase-2 ConfigMap and restarting the Deployment produced a `1/1 Running` replacement with a successful rollout.

## Persistent data restart (phase 3)

```bash
make smoke
kubectl -n shop delete pod postgres-0
kubectl -n shop rollout status statefulset/postgres
make smoke
```

Expected observation: the original item remains because the replacement Pod mounts the same PVC. The exercise proves Pod replacement persistence, not backup or disaster recovery; deleting the PVC destroys the local data.

**Observed 2026-09-17:** item `1` (`smoke-test-item`) was created, `postgres-0` was deleted, and the StatefulSet replacement became Ready on the same bound PVC. `/readyz` returned ready and `GET /api/items` returned the original item after replacement.
