import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class ReleaseSafety(unittest.TestCase):
    def test_healthy_old_revision_does_not_complete_upgrade(self):
        check = module("check-gitops").at_revision
        app = {"spec": {"source": {"targetRevision": "v1.0.0"}},
               "status": {"sync": {"comparedTo": {"source": {"targetRevision": "main"}}}}}
        self.assertFalse(check(app, "v1.0.0"))
        app["status"]["sync"]["comparedTo"]["source"]["targetRevision"] = "v1.0.0"
        self.assertTrue(check(app, "v1.0.0"))
        self.assertFalse(check({}, "v1.0.0"))

    def test_every_platform_source_must_match(self):
        check = module("check-gitops").at_revision
        sources = [{"targetRevision": "v1.0.0"}, {"targetRevision": "main"}]
        app = {"spec": {"sources": sources}, "status": {"sync": {"comparedTo": {"sources": sources}}}}
        self.assertFalse(check(app, "v1.0.0"))
        sources[1]["targetRevision"] = "v1.0.0"
        self.assertTrue(check(app, "v1.0.0"))

    def test_root_and_all_children_share_release_revision(self):
        root = module("bootstrap-gitops").pinned_root({"spec": {"source": {}}}, "v1.0.0")
        self.assertEqual(root["spec"]["source"]["targetRevision"], "v1.0.0")
        patches = root["spec"]["source"]["kustomize"]["patches"]
        self.assertEqual(len(patches), 2)
        self.assertEqual(sum(p["patch"].count('"value": "v1.0.0"') for p in patches), 4)

    def test_restore_refuses_application_database_and_sql(self):
        validate = module("database").restore_name
        for name in ["kube_foundry", "postgres", "restore_bad; DROP DATABASE postgres", "restore_", "../restore_x"]:
            with self.assertRaises(argparse.ArgumentTypeError):
                validate(name)
        self.assertEqual(validate("restore_acceptance"), "restore_acceptance")

    def test_credentials_never_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "private.env"
            destination.write_text("existing-data")
            result = subprocess.run([sys.executable, str(Path(__file__).with_name("init-env.py")),
                                     "--output", str(destination)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(destination.read_text(), "existing-data")

    def test_validated_archive_can_be_streamed_from_start(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "test.dump"
            archive.write_bytes(b"PGDMPexample")
            with module("database").open_archive(archive) as handle:
                result = subprocess.check_output(
                    [sys.executable, "-c", "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"],
                    stdin=handle)
            self.assertEqual(result, b"PGDMPexample")

    def test_invalid_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "test.dump"
            archive.write_bytes(b"not a dump")
            with self.assertRaises(ValueError):
                module("database").open_archive(archive)


if __name__ == "__main__":
    unittest.main()
