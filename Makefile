SHELL := /bin/sh

CLUSTER_NAME ?= kube-foundry
CLUSTER_CONFIG ?= clusters/kind/cluster.yaml
ENVIRONMENT ?= dev
ENV_FILE ?= .env
IMAGE_TAG ?= 0.1.0
CILIUM_VERSION ?= 1.20.2
ENVOY_GATEWAY_VERSION ?= v1.9.1
CERT_MANAGER_VERSION ?= v1.21.2
API_IMAGE := kube-foundry-api:$(IMAGE_TAG)
WORKER_IMAGE := kube-foundry-worker:$(IMAGE_TAG)
WEB_IMAGE := kube-foundry-web:$(IMAGE_TAG)

.PHONY: cluster cluster-delete build load secret deploy-phase1 deploy-phase2 deploy-phase3 traffic-platform deploy-phase4 gateway-access smoke smoke-traffic status validate

cluster:
	kind create cluster --name $(CLUSTER_NAME) --config $(CLUSTER_CONFIG)
	helm upgrade --install cilium oci://quay.io/cilium/charts/cilium --version $(CILIUM_VERSION) --namespace kube-system --set image.pullPolicy=IfNotPresent --set ipam.mode=kubernetes
	kubectl -n kube-system rollout status daemonset/cilium --timeout=300s
	kubectl -n kube-system rollout status deployment/cilium-operator --timeout=300s
	kubectl wait --for=condition=Ready nodes --all --timeout=300s

cluster-delete:
	kind delete cluster --name $(CLUSTER_NAME)

build:
	docker build --pull -t $(API_IMAGE) app/api
	docker build --pull -t $(WORKER_IMAGE) app/worker
	docker build --pull -t $(WEB_IMAGE) app/web

load:
	kind load docker-image --name $(CLUSTER_NAME) $(API_IMAGE) $(WORKER_IMAGE) $(WEB_IMAGE)

secret:
	@test -f "$(ENV_FILE)" || (echo "Missing $(ENV_FILE). Copy .env.example and set local-only values." && exit 1)
	kubectl apply -f clusters/kind/manifests/phase1/namespace.yaml
	kubectl -n shop create secret generic shop-runtime --from-env-file="$(ENV_FILE)" --dry-run=client -o yaml | kubectl apply -f -

deploy-phase1:
	kubectl apply -k clusters/kind/manifests/phase1
	kubectl -n shop rollout status deployment/api --timeout=120s

deploy-phase2: secret
	kubectl apply -k clusters/kind/manifests/phase2
	kubectl -n shop rollout status deployment/api --timeout=120s

deploy-phase3: secret
	kubectl apply -k clusters/kind/manifests/phase3
	kubectl -n shop rollout status statefulset/postgres --timeout=180s
	kubectl -n shop rollout status deployment/redis --timeout=120s
	kubectl -n shop rollout status deployment/api --timeout=180s
	kubectl -n shop rollout status deployment/worker --timeout=180s

traffic-platform:
	helm upgrade --install eg oci://docker.io/envoyproxy/gateway-helm --version $(ENVOY_GATEWAY_VERSION) --namespace envoy-gateway-system --create-namespace --wait --timeout 300s
	helm upgrade --install cert-manager oci://quay.io/jetstack/charts/cert-manager --version $(CERT_MANAGER_VERSION) --namespace cert-manager --create-namespace --set crds.enabled=true --wait --timeout 300s

deploy-phase4: deploy-phase3 traffic-platform
	kubectl apply -k clusters/kind/manifests/phase4
	kubectl -n shop rollout status deployment/web --timeout=180s
	kubectl -n shop wait --for=condition=Ready certificate/shop-local --timeout=180s
	kubectl -n shop wait --for=condition=Programmed gateway/shop --timeout=180s

gateway-access:
	@service=$$(kubectl -n envoy-gateway-system get service -l gateway.envoyproxy.io/owning-gateway-namespace=shop,gateway.envoyproxy.io/owning-gateway-name=shop -o jsonpath='{.items[0].metadata.name}'); \
	test -n "$$service" && kubectl -n envoy-gateway-system port-forward --address 127.0.0.1 service/$$service 8080:80 8443:443

.PHONY: render-shop check-chart deploy-phase5 check-environment

render-shop:
	@sh scripts/render-shop.sh

check-chart:
	helm lint charts/shop --strict
	@sh scripts/render-shop.sh --check
	@for environment in dev staging prod; do kubectl kustomize gitops/apps/shop/overlays/$$environment >/dev/null || exit 1; done

check-environment:
	@case "$(ENVIRONMENT)" in dev|staging|prod) ;; *) echo "ENVIRONMENT must be dev, staging, or prod" >&2; exit 1 ;; esac

deploy-phase5: check-environment check-chart
	$(MAKE) secret traffic-platform
	kubectl apply -f gitops/platform/gatewayclass.yaml
	kubectl apply -k gitops/apps/shop/overlays/$(ENVIRONMENT)
	kubectl -n shop rollout status statefulset/postgres --timeout=180s
	kubectl -n shop rollout status deployment/redis --timeout=180s
	kubectl -n shop rollout status deployment/api --timeout=180s
	kubectl -n shop rollout status deployment/worker --timeout=180s
	kubectl -n shop rollout status deployment/web --timeout=180s
	kubectl -n shop wait --for=condition=Ready certificate/shop-local --timeout=180s
	kubectl -n shop wait --for=condition=Programmed gateway/shop --timeout=180s

smoke-traffic:
	@sh scripts/smoke-traffic.sh

smoke:
	@sh scripts/smoke.sh

status:
	kubectl get pods,svc,pvc,networkpolicy -n shop -o wide

validate: check-chart
	kubectl kustomize clusters/kind/manifests/phase1 >/dev/null
	kubectl kustomize clusters/kind/manifests/phase2 >/dev/null
	kubectl kustomize clusters/kind/manifests/phase3 >/dev/null
	kubectl kustomize clusters/kind/manifests/phase4 >/dev/null
	python -m compileall -q app/api app/worker
