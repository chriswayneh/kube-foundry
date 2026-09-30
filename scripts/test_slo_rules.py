import json
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).parents[1]


class SloRules(unittest.TestCase):
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
