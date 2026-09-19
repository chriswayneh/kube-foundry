#!/usr/bin/env sh
set -eu

work_dir=$(mktemp -d)
port_forward_pid=''
cleanup() {
  if [ -n "$port_forward_pid" ]; then kill "$port_forward_pid" 2>/dev/null || true; fi
  rm -f "$work_dir/cert.pem" "$work_dir/port-forward.log"
  rmdir "$work_dir"
}
trap cleanup EXIT
trap 'exit 1' INT TERM

kubectl -n shop wait --for=condition=Ready certificate/shop-local --timeout=180s
kubectl -n shop wait --for=condition=Programmed gateway/shop --timeout=180s
# Export only the public certificate, never the private key.
kubectl -n shop get secret shop-local-tls -o 'jsonpath={.data.tls\.crt}' |
  python -c 'import base64,sys; sys.stdout.buffer.write(base64.b64decode(sys.stdin.read()))' >"$work_dir/cert.pem"
service=$(kubectl -n envoy-gateway-system get service \
  -l gateway.envoyproxy.io/owning-gateway-namespace=shop,gateway.envoyproxy.io/owning-gateway-name=shop \
  -o 'jsonpath={.items[0].metadata.name}')
test -n "$service"
kubectl -n envoy-gateway-system port-forward --address 127.0.0.1 \
  "service/$service" 18080:80 18443:443 >"$work_dir/port-forward.log" 2>&1 &
port_forward_pid=$!

http() {
  curl --noproxy '*' --connect-timeout 3 --max-time 10 --fail --silent --show-error \
    --resolve shop.localhost:18080:127.0.0.1 "http://shop.localhost:18080$1"
}
https() {
  curl --noproxy '*' --connect-timeout 3 --max-time 10 --fail --silent --show-error \
    --cacert "$work_dir/cert.pem" --resolve shop.localhost:18443:127.0.0.1 "$@"
}

attempt=0
until http / >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then cat "$work_dir/port-forward.log"; exit 1; fi
  sleep 1
done

http / | grep -q 'id="item-form"'
http /api/items | python -c 'import json,sys; assert isinstance(json.load(sys.stdin), list)'
https https://shop.localhost:18443/ | grep -q 'id="item-form"'
https https://shop.localhost:18443/app.js | grep -q '/api/items'
https -X POST -H 'Content-Type: application/json' -d '{"name":"traffic-smoke-item"}' \
  https://shop.localhost:18443/api/items |
  python -c 'import json,sys; assert json.load(sys.stdin)["name"] == "traffic-smoke-item"'
https https://shop.localhost:18443/api/items |
  python -c 'import json,sys; assert any(i["name"] == "traffic-smoke-item" for i in json.load(sys.stdin))'

# An unknown API path must remain an API 404, not fall through to the SPA.
code=$(curl --noproxy '*' --silent --show-error --max-time 10 --output /dev/null --write-out '%{http_code}' \
  --resolve shop.localhost:18080:127.0.0.1 http://shop.localhost:18080/api/not-found)
test "$code" = 404
# A different Host must not reach the app.
code=$(curl --noproxy '*' --silent --show-error --max-time 10 --output /dev/null --write-out '%{http_code}' \
  -H 'Host: unknown.localhost' http://127.0.0.1:18080/)
test "$code" = 404

job_id=$(https -X POST https://shop.localhost:18443/api/jobs |
  python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
attempt=0
while [ "$attempt" -lt 20 ]; do
  state=$(https "https://shop.localhost:18443/api/jobs/$job_id" |
    python -c 'import json,sys; print(json.load(sys.stdin)["status"])')
  if [ "$state" = complete ]; then
    echo 'PASS: HTTP/HTTPS web and API routing, certificate trust, item creation, job completion, and unmatched routes.'
    exit 0
  fi
  attempt=$((attempt + 1))
  sleep 1
done
echo "Job $job_id did not complete" >&2
exit 1
