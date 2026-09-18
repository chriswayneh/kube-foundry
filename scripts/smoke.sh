#!/usr/bin/env sh
set -eu

log_file="${TMPDIR:-/tmp}/kube-foundry-port-forward.log"
kubectl -n shop port-forward service/api 18000:8000 >"$log_file" 2>&1 &
port_forward_pid=$!
trap 'kill "$port_forward_pid" 2>/dev/null || true' EXIT INT TERM

attempt=0
until curl --fail --silent http://127.0.0.1:18000/healthz >/dev/null; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 20 ]; then
    cat "$log_file"
    exit 1
  fi
  sleep 1
done

curl --fail --silent http://127.0.0.1:18000/healthz
printf '\n'
curl --fail --silent http://127.0.0.1:18000/readyz
printf '\n'
curl --fail --silent -X POST -H 'Content-Type: application/json' \
  -d '{"name":"smoke-test-item"}' http://127.0.0.1:18000/api/items
printf '\n'
curl --fail --silent http://127.0.0.1:18000/api/items
printf '\n'
job_json=$(curl --fail --silent -X POST http://127.0.0.1:18000/api/jobs)
printf '%s\n' "$job_json"
job_id=$(printf '%s' "$job_json" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')

attempt=0
while [ "$attempt" -lt 20 ]; do
  status_json=$(curl --fail --silent "http://127.0.0.1:18000/api/jobs/$job_id")
  printf '%s\n' "$status_json"
  printf '%s' "$status_json" | grep -q '"status":"complete"' && exit 0
  attempt=$((attempt + 1))
  sleep 1
done

echo "Worker did not complete job $job_id" >&2
exit 1

