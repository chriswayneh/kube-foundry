"""Evaluate the deployed rule specification with promtool using synthetic time series."""

import argparse
from pathlib import Path
import subprocess
import tempfile

import yaml


ROOT = Path(__file__).resolve().parents[1]
ALERTS = ("ShopApiTargetUnavailable", "ShopApiErrorBudgetBurning", "ShopApiLatencyHigh")
LABELS = 'namespace="shop",service="api",path="/api/items",method="GET"'


def counter(status, values):
    return {"series": f'http_requests_total{{{LABELS},status="{status}"}}', "values": values}


def target(values="1+0x20", instance="api-1"):
    return {"series": f'up{{namespace="shop",service="api",instance="{instance}"}}', "values": values}


def histogram(slow=False):
    return [{"series": f'http_request_duration_seconds_bucket{{{LABELS},le="{bound}"}}',
             "values": f"0+{increment}x20"}
            for bound, increment in [("0.5", 60 if slow else 120), ("1", 120), ("+Inf", 120)]]


def sample(expr, value, at="10m", labels="{}"):
    return {"expr": expr, "eval_time": at,
            "exp_samples": [] if value is None else [{"labels": labels, "value": value}]}


def scenario(name, series, ratio, alerts=(), at="10m"):
    checks = [sample("shop:api_success_ratio:rate5m", ratio, at,
                     '{__name__="shop:api_success_ratio:rate5m"}')]
    for alert in ALERTS:
        checks.append(sample(f'count(ALERTS{{alertname="{alert}",alertstate="firing"}}) or vector(0)',
                             int(alert in alerts), at))
    return {"name": name, "interval": "1m", "input_series": series, "promql_expr_test": checks}


def cases():
    healthy = [target(), counter("200", "0+12x20")]
    errors = [target(), counter("200", "0+60x20"), counter("503", "0+60x20")]
    slow = [target(), counter("200", "0+120x20"), *histogram(slow=True)]
    tests = [
        scenario("Healthy 0.2 requests per second", healthy, 1),
        scenario("Healthy below alert traffic floor", [target(), counter("200", "0+3x20")], 1),
        scenario("Idle counters are not failed requests", [target(), counter("200", "10+0x20")], None),
        scenario("New API has no request series", [target()], None),
        scenario("404 and 422 are not server failures",
                 [target(), counter("404", "0+60x20"), counter("422", "0+60x20")], 1),
        scenario("Redirects are not server failures", [target(), counter("307", "0+120x20")], 1),
        scenario("5xx waits for hold interval", errors, 0.5, at="5m"),
        scenario("5xx fires after hold interval", errors, 0.5, (ALERTS[1],), at="6m"),
        scenario("All requests fail", [target(), counter("503", "0+120x20")], 0, (ALERTS[1],)),
        scenario("Sparse errors stay below traffic floor", [target(), counter("503", "0+3x20")], 0),
        scenario("Exactly 0.1 requests per second stays below gate", [target(), counter("503", "0+6x20")], 0),
        scenario("Exactly 2 percent errors does not fire",
                 [target(), counter("200", "0+98x20"), counter("500", "0+2x20")], 0.98),
        scenario("More than 2 percent errors fires",
                 [target(), counter("200", "0+97x20"), counter("500", "0+3x20")], 0.97, (ALERTS[1],)),
        scenario("High latency waits for hold interval", slow, 1, at="5m"),
        scenario("High latency fires after hold interval", slow, 1, (ALERTS[2],), at="6m"),
        scenario("Healthy latency", [*healthy, *histogram()], 1),
        scenario("One failed target waits", [target("0+0x20"), target(instance="api-2")], None, at="1m"),
        scenario("One failed target fires", [target("0+0x20"), target(instance="api-2")],
                 None, (ALERTS[0],), at="2m"),
        scenario("Missing targets wait", [], None, at="1m"),
        scenario("Missing targets fire", [], None, (ALERTS[0],), at="2m"),
        scenario("Discovered targets disappear", [target("1+0x3 stale _x16")],
                 None, (ALERTS[0],), at="6m"),
        scenario("Target recovery clears alert", [target("0+0x3 1+0x16")], None, at="4m"),
        scenario("Counter reset preserves healthy ratio",
                 [target(), counter("200", "0 12 24 36 0 12 24 36 48 60 72")], 1, at="6m"),
        scenario("Old server errors age out",
                 [target(), counter("200", "0+60x5 420+120x14"), counter("503", "0+60x5 300+0x14")],
                 1, at="12m"),
    ]
    noise = [{"series": f'http_requests_total{{namespace="{namespace}",service="{service}",'
                        f'path="{path}",method="GET",status="503"}}', "values": "0+600x20"}
             for namespace, service, path in [("other", "api", "/api/items"),
                                               ("shop", "other", "/api/items"),
                                               ("shop", "api", "/readyz")]]
    tests.append(scenario("Other namespaces services and probes are excluded", [*healthy, *noise], 1))
    tests[2]["promql_expr_test"].append(sample("shop:api_requests:rate5m", 0,
                                               labels='{__name__="shop:api_requests:rate5m"}'))
    tests[3]["promql_expr_test"].append(sample("shop:api_requests:rate5m", None))
    return tests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--promtool", default="promtool", help="Path to promtool (CI uses 3.5.0)")
    args = parser.parse_args()
    resource = yaml.safe_load((ROOT / "gitops/platform/monitoring/slo-rules.yaml").read_text())
    with tempfile.TemporaryDirectory(prefix="kube-foundry-rules-") as directory:
        directory = Path(directory)
        # Use the actual deployed expressions, not a second maintained copy of the rules.
        (directory / "rules.yaml").write_text(yaml.safe_dump(resource["spec"]), encoding="utf-8")
        tests = cases()
        (directory / "tests.yaml").write_text(yaml.safe_dump({
            "rule_files": ["rules.yaml"], "evaluation_interval": "1m", "tests": tests,
        }), encoding="utf-8")
        subprocess.run([args.promtool, "check", "rules", "rules.yaml"], cwd=directory, check=True)
        subprocess.run([args.promtool, "test", "rules", "tests.yaml"], cwd=directory, check=True)
        print(f"PASS: {len(tests)} Prometheus behavior scenarios")


if __name__ == "__main__":
    main()
