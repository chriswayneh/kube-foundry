# Traffic and local TLS

Phase 4 connects the frontend and API through Envoy Gateway. `shop.localhost` routes `/api` to port 8000 on the API and `/` to port 8080 on web. API paths are not rewritten. An unknown API path returns the API's 404; it does not fall back to the frontend.

## Install and deploy

With the cluster, local images, and `.env` prepared as described in the main README:

```sh
make deploy-phase4
make smoke-traffic
make gateway-access
```

Pinned components:

| Component | Version | Installation |
| --- | --- | --- |
| Envoy Gateway | v1.9.1 | `gateway-helm` OCI chart |
| Gateway API CRDs | v1.6.1 | Bundled in the pinned Envoy Gateway chart |
| cert-manager | v1.21.2 | `cert-manager` OCI chart with CRDs enabled |

`traffic-platform` installs the controllers and CRDs before application resources. `deploy-phase4` includes phase 3 and waits for the web Deployment, Certificate, and programmed Gateway. The Certificate is explicit, so cert-manager's optional Gateway annotation integration is not required.

## Access from the host

Keep `make gateway-access` running while using:

- HTTP: `http://shop.localhost:8080`
- HTTPS: `https://shop.localhost:8443`

The forward binds to `127.0.0.1`. No load balancer or host networking is needed. HTTP remains available for local testing; this phase does not enforce an HTTPS redirect or add application authentication. Do not expose this development stack to the internet.

PowerShell equivalent:

```powershell
$gatewayService = kubectl -n envoy-gateway-system get service -l gateway.envoyproxy.io/owning-gateway-namespace=shop,gateway.envoyproxy.io/owning-gateway-name=shop -o 'jsonpath={.items[0].metadata.name}'
kubectl -n envoy-gateway-system port-forward --address 127.0.0.1 "service/$gatewayService" 8080:80 8443:443
```

If your browser does not resolve `shop.localhost`, add `127.0.0.1 shop.localhost` to your hosts file. Command-line checks can avoid hosts-file changes with `curl --resolve`.

## Certificate trust

The namespaced `local-selfsigned` Issuer creates a 90-day certificate for `shop.localhost`, renewed 15 days before expiry. cert-manager stores it in `shop-local-tls`. Browsers will warn because the certificate is not issued by a trusted public CA. No host trust-store changes are made automatically.

`make smoke-traffic` exports only the public certificate to a temporary directory and uses `curl --cacert` to verify both trust and hostname. It does not bypass verification with `-k`. The temporary file and port-forward are removed on exit. The test creates an item and a job in the local development database.

The earlier kind host mappings for ports 80/443 are not used by this access method. The port-forward avoids cluster recreation and works on the existing Docker Desktop cluster. Restart it after an Envoy Pod replacement.

## Verification and troubleshooting

```sh
kubectl -n shop get gateway,httproute,certificate
kubectl -n shop describe gateway shop
kubectl -n shop describe httproute shop
kubectl -n shop describe certificate shop-local
kubectl -n envoy-gateway-system get pods,svc
make smoke-traffic
```

Both HTTPRoute parents should report `Accepted=True` and `ResolvedRefs=True`. The Gateway should report `Programmed=True` and the Certificate `Ready=True`. A 503 usually indicates a missing ready backend or a NetworkPolicy mismatch; a 404 for the wrong hostname is expected.

Verified on the existing three-node kind cluster on 2026-09-19:

- Frontend HTML and JavaScript served through Envoy.
- HTTP and HTTPS API routing succeeded.
- HTTPS certificate and hostname verification succeeded using the generated public certificate.
- Item creation, item listing, and queued job completion succeeded through HTTPS.
- Unknown hosts and unknown API paths returned 404.
- An unlabeled test Pod timed out connecting to API, web, PostgreSQL, and Redis; it was removed after verification.

## References

- [Envoy Gateway installation](https://gateway.envoyproxy.io/docs/tasks/quickstart/)
- [Envoy proxy customization](https://gateway.envoyproxy.io/docs/tasks/operations/customize-envoyproxy/)
- [cert-manager Helm installation](https://cert-manager.io/docs/installation/helm/)
- [Self-signed issuers](https://cert-manager.io/docs/configuration/selfsigned/)
