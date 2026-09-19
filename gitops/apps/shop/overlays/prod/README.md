# Production overlay

Three API/web replicas, 100m CPU and 128Mi memory requested by each API Pod, and `shop.prod.localhost`. Deploy with `make deploy-phase5 ENVIRONMENT=prod`. It targets `shop` in a separate cluster. Test with `SHOP_HOST=shop.prod.localhost make smoke-traffic`.

This is a production-shaped configuration example. PostgreSQL and Redis remain single replicas, TLS is self-signed, and application authentication is not implemented. It is not ready for public production traffic.
