import json
from pathlib import Path
import unittest

import yaml

from test_release import module

ROOT = Path(__file__).parents[1]


class SloRules(unittest.TestCase):
    def test_rule_resource_is_allowed_by_owning_argocd_project(self):
        child = yaml.safe_load((ROOT / "gitops/children/platform.yaml").read_text())
        projects = list(yaml.safe_load_all((ROOT / "gitops/projects.yaml").read_text()))
        project = next(p["spec"] for p in projects if p["metadata"]["name"] == child["spec"]["project"])
        rule = yaml.safe_load((ROOT / "gitops/platform/monitoring/slo-rules.yaml").read_text())
        self.assertIn({"group": rule["apiVersion"].split("/")[0], "kind": rule["kind"]},
                      project["namespaceResourceWhitelist"])
        self.assertIn({"server": child["spec"]["destination"]["server"],
                       "namespace": rule["metadata"]["namespace"]}, project["destinations"])

    def test_live_rule_verification_rejects_missing_or_failed_evaluations(self):
        check = module("check-observability").verify_rules
        resource = yaml.safe_load((ROOT / "gitops/platform/monitoring/slo-rules.yaml").read_text())
        rules = [{"name": rule.get("record") or rule.get("alert"), "health": "ok",
                  "lastEvaluation": "2026-09-30T10:00:00Z"}
                 for rule in resource["spec"]["groups"][0]["rules"]]
        payload = {"status": "success", "data": {"groups": [
            {"name": "kube-foundry-shop-slo", "rules": rules}]}}
        check(payload)
        for field, value in [("health", "err"), ("lastError", "evaluation failed"),
                             ("lastEvaluation", "0001-01-01T00:00:00Z")]:
            with self.subTest(field=field):
                previous = rules[0].get(field)
                rules[0][field] = value
                with self.assertRaises(AssertionError):
                    check(payload)
                if previous is None:
                    rules[0].pop(field)
                else:
                    rules[0][field] = previous
        rules.pop(2)  # The latency recording rule is required too.
        with self.assertRaises(AssertionError):
            check(payload)

    def test_rules_are_local_diagnostic_signals(self):
        rule = yaml.safe_load((ROOT / "gitops/platform/monitoring/slo-rules.yaml").read_text())
        self.assertEqual(rule["kind"], "PrometheusRule")
        self.assertEqual(rule["metadata"]["namespace"], "monitoring")
        rules = rule["spec"]["groups"][0]["rules"]
        names = {item.get("record") or item.get("alert") for item in rules}
        self.assertEqual(names, {
            "shop:api_requests:rate5m",
            "shop:api_success_ratio:rate5m",
            "shop:api_p95_latency_seconds:rate5m",
            "ShopApiTargetUnavailable",
            "ShopApiErrorBudgetBurning",
            "ShopApiLatencyHigh",
        })
        alerts = [item for item in rules if "alert" in item]
        self.assertTrue(all(item["labels"]["scope"] == "local" for item in alerts))
        self.assertTrue(all(item["labels"]["severity"] == "warning" for item in alerts))

    def test_dashboard_uses_recording_rules_and_alert_state(self):
        dashboard = json.loads((ROOT / "gitops/platform/monitoring/shop.json").read_text())
        panels = {panel["title"]: panel for panel in dashboard["panels"]}
        self.assertEqual(len(panels), 10)
        self.assertEqual(
            panels["API 5m success ratio"]["targets"][0]["expr"],
            "shop:api_success_ratio:rate5m",
        )
        self.assertIn("ALERTS", panels["Active local reliability alerts"]["targets"][0]["expr"])


if __name__ == "__main__":
    unittest.main()
