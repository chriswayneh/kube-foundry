SHELL := /bin/sh

CLUSTER_NAME ?= kube-foundry
CLUSTER_CONFIG ?= clusters/kind/cluster.yaml
ENVIRONMENT ?= dev
ENV_FILE ?= .env
REUSE_SECRET ?= false
IMAGE_TAG ?= 0.1.0
CILIUM_VERSION ?= 1.20.2
ENVOY_GATEWAY_VERSION ?= v1.9.1
CERT_MANAGER_VERSION ?= v1.21.2
KYVERNO_VERSION ?= 3.9.1
MONITORING_VERSION ?= 91.4.1
METRICS_SERVER_VERSION ?= 3.14.0
ARGOCD_VERSION ?= 10.9.2
APPLICATION_OVERLAY ?= gitops/apps/shop/overlays/$(ENVIRONMENT)
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
	kubectl apply -f gitops/apps/shop/base/namespace.yaml
	@if [ "$(REUSE_SECRET)" = true ]; then \
		kubectl -n shop get secret shop-runtime >/dev/null; \
	else \
		test -f "$(ENV_FILE)" || { echo "Missing $(ENV_FILE). Copy .env.example and set local-only values." >&2; exit 1; }; \
		kubectl -n shop create secret generic shop-runtime --from-env-file="$(ENV_FILE)" --dry-run=client -o yaml | kubectl apply -f -; \
	fi

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
	kubectl apply -k $(APPLICATION_OVERLAY)
	kubectl -n shop rollout status statefulset/postgres --timeout=180s
	kubectl -n shop rollout status deployment/redis --timeout=180s
	kubectl -n shop rollout status deployment/api --timeout=180s
	kubectl -n shop rollout status deployment/worker --timeout=180s
	kubectl -n shop rollout status deployment/web --timeout=180s
	kubectl -n shop wait --for=condition=Ready certificate/shop-local --timeout=180s
	kubectl -n shop wait --for=condition=Programmed gateway/shop --timeout=180s

smoke-traffic:
	@sh scripts/smoke-traffic.sh

.PHONY: security-platform deploy-phase6 security-check

security-platform:
	helm upgrade --install kyverno kyverno --repo https://kyverno.github.io/kyverno/ --version $(KYVERNO_VERSION) --namespace kyverno --create-namespace -f gitops/platform/kyverno-values.yaml --wait --timeout 300s

deploy-phase6: deploy-phase5
	$(MAKE) security-platform
	kubectl apply -f policy/shop-workloads.yaml
	kubectl -n shop wait --for=jsonpath='{.status.conditionStatus.ready}'=true namespacedvalidatingpolicy/shop-workloads --timeout=120s
	kubectl -n shop wait --for=jsonpath='{.status.conditionStatus.ready}'=true namespacedvalidatingpolicy/shop-ephemeral-containers --timeout=120s
	$(MAKE) security-check

security-check:
	python scripts/check-security.py

.PHONY: monitoring-platform deploy-phase7 monitoring-check scaling-check grafana-access prometheus-access

monitoring-platform:
	helm upgrade --install metrics-server metrics-server --repo https://kubernetes-sigs.github.io/metrics-server/ --version $(METRICS_SERVER_VERSION) --namespace kube-system -f gitops/platform/monitoring/metrics-server-values.yaml --wait --timeout 300s
	helm upgrade --install monitoring kube-prometheus-stack --repo https://prometheus-community.github.io/helm-charts --version $(MONITORING_VERSION) --namespace monitoring --create-namespace -f gitops/platform/monitoring/values.yaml --wait --timeout 300s
	kubectl apply -k gitops/platform/monitoring
	kubectl wait --for=condition=Available apiservice/v1beta1.metrics.k8s.io --timeout=120s

deploy-phase7: check-environment monitoring-platform
	$(MAKE) deploy-phase6 APPLICATION_OVERLAY=gitops/apps/shop/phase7/$(ENVIRONMENT)
	$(MAKE) monitoring-check

monitoring-check:
	python scripts/check-observability.py

scaling-check:
	python scripts/check-scaling.py

grafana-access:
	kubectl -n monitoring port-forward --address 127.0.0.1 service/monitoring-grafana 3000:80

prometheus-access:
	kubectl -n monitoring port-forward --address 127.0.0.1 service/monitoring-prometheus 9090:9090

.PHONY: gitops-platform deploy-phase8 gitops-check argocd-access

gitops-platform:
	helm upgrade --install argocd argo-cd --repo https://argoproj.github.io/argo-helm --version $(ARGOCD_VERSION) --namespace argocd --create-namespace -f gitops/platform/argocd-values.yaml --wait --timeout 300s
	kubectl apply -f gitops/projects.yaml

# Bootstrap controllers and credentials first with deploy-phase7 on a new cluster.
deploy-phase8: gitops-platform
	kubectl -n shop get secret shop-runtime >/dev/null
	kubectl apply -f gitops/root-app.yaml
	$(MAKE) gitops-check

gitops-check:
	python scripts/check-gitops.py

argocd-access:
	kubectl -n argocd port-forward --address 127.0.0.1 service/argocd-server 8081:443

smoke:
	@sh scripts/smoke.sh

status:
	kubectl get pods,svc,pvc,networkpolicy -n shop -o wide

validate: check-chart
	kubectl kustomize gitops >/dev/null
	kubectl kustomize gitops/apps/shop/phase8/dev >/dev/null
	@for environment in dev staging prod; do kubectl kustomize gitops/apps/shop/phase7/$$environment >/dev/null || exit 1; done
	kubectl kustomize gitops/platform/monitoring >/dev/null
	kubectl kustomize clusters/kind/manifests/phase1 >/dev/null
	kubectl kustomize clusters/kind/manifests/phase2 >/dev/null
	kubectl kustomize clusters/kind/manifests/phase3 >/dev/null
	kubectl kustomize clusters/kind/manifests/phase4 >/dev/null
	python -m compileall -q app/api app/worker scripts
