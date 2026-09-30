import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from proof import CONTEXT, evidence
from test_release import module


class OperationalProof(unittest.TestCase):
    def test_evidence_success_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory, patch("proof.get", return_value={"metadata": {"uid": "test"}}):
            path = Path(directory) / "proof.json"
            with evidence(path, "test", CONTEXT) as report:
                report["verified"] = True
            self.assertEqual(json.loads(path.read_text())["status"], "passed")
            with self.assertRaises(FileExistsError):
                with evidence(path, "test", CONTEXT):
                    self.fail("Overwrote evidence")

    def test_failure_and_secret_sanitization(self):
        with tempfile.TemporaryDirectory() as directory, patch("proof.get", return_value={"metadata": {"uid": "test"}}):
            path = Path(directory) / "proof.json"
            with self.assertRaises(RuntimeError):
                with evidence(path, "test", CONTEXT):
                    raise RuntimeError("private-token")
            self.assertEqual(json.loads(path.read_text())["status"], "failed")
            self.assertNotIn("private-token", path.read_text())

    def test_non_disposable_context_rejected(self):
        with self.assertRaises(RuntimeError):
            with evidence("unused.json", "test", "kind-kube-foundry"):
                self.fail("Accepted original cluster")

    def test_interruption_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory, patch("proof.get", return_value={"metadata": {"uid": "test"}}):
            path = Path(directory) / "proof.json"
            with self.assertRaises(KeyboardInterrupt):
                with evidence(path, "test", CONTEXT):
                    raise KeyboardInterrupt()
            self.assertEqual(json.loads(path.read_text())["status"], "failed")

    def test_cluster_connection_failure_records_failure(self):
        with tempfile.TemporaryDirectory() as directory, patch("proof.get", side_effect=RuntimeError("offline")):
            path = Path(directory) / "proof.json"
            with self.assertRaises(RuntimeError):
                with evidence(path, "test", CONTEXT):
                    self.fail("Continued without cluster identity")
            self.assertEqual(json.loads(path.read_text())["status"], "failed")

    def test_checksum_mismatch_and_rewind(self):
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.dump"
            content = b"PGDMPtest"
            path.write_bytes(content)
            with self.assertRaises(ValueError):
                module("database").open_archive(path, "0" * 64)
            with module("database").open_archive(path, hashlib.sha256(content).hexdigest()) as handle:
                self.assertEqual(handle.read(), content)

    def test_empty_and_changed_tables_fail(self):
        backup = module("check-backup")
        with self.assertRaises(RuntimeError):
            backup.summarize(b"")
        rows = backup.summarize(b'{"id":1}\n')
        self.assertEqual(rows["rows"], 1)
        with self.assertRaises(RuntimeError):
            backup.verify_tables(rows, rows, {"rows": 0})
        with self.assertRaises(RuntimeError):
            backup.verify_tables(rows, {"rows": 0}, rows)

    def test_stale_revision_and_partial_multi_source_rejected(self):
        check = module("check-promotion").app_matches
        app = {"spec": {"sources": [{"targetRevision": "new"}] * 3},
               "status": {"health": {"status": "Healthy"},
                          "sync": {"status": "Synced", "revisions": ["new", "new", "old"]}}}
        self.assertFalse(check(app, "new"))
        app["status"]["sync"]["revisions"] = ["new"]
        self.assertFalse(check(app, "new"))
        app["status"]["sync"]["revisions"] = ["new"] * 3
        self.assertTrue(check(app, "new"))

    def test_stale_rollout_and_old_replicas_rejected(self):
        check = module("check-promotion").rollout_matches
        deploy = {"metadata": {"generation": 2}, "spec": {"replicas": 2,
                  "template": {"spec": {"containers": [{"image": "expected"}]}}},
                  "status": {"observedGeneration": 1, "replicas": 2, "updatedReplicas": 2,
                             "readyReplicas": 2, "availableReplicas": 2}}
        self.assertFalse(check(deploy, "expected"))
        deploy["status"]["observedGeneration"] = 2
        self.assertTrue(check(deploy, "expected"))
        deploy["status"]["replicas"] = 3
        self.assertFalse(check(deploy, "expected"))


if __name__ == "__main__":
    unittest.main()
