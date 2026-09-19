# Staging overlay

Two API/web replicas, 75m CPU and 96Mi memory requested by each API Pod, and `shop.staging.localhost`. Deploy with `make deploy-phase5 ENVIRONMENT=staging`. It targets `shop` in a separate staging cluster. Test with `SHOP_HOST=shop.staging.localhost make smoke-traffic`.
