import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare = load("prepare_delivery", "prepare-delivery.py")
checker = load("check_delivery", "check-delivery.py")


class PromotionValidation(unittest.TestCase):
    def test_other_changes_do_not_contact_registry(self):
        self.assertFalse(checker.verify(["README.md"], "", "a" * 40, self.fail))

    def test_mixed_scope_is_rejected(self):
        with self.assertRaises(ValueError):
            checker.verify([checker.OVERLAY, "README.md"], "", "a" * 40, self.fail)

    def test_exact_current_base_is_required(self):
        base = "a" * 40
        current = f"source={base}"
        def render(sha):
            return f"source={sha}"
        self.assertTrue(checker.verify([checker.OVERLAY], current, base, render))
        with self.assertRaises(ValueError):
            checker.verify([checker.OVERLAY], "source=" + "b" * 40, base, render)


class DeliveryBranches(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.remote = self.root / "origin.git"
        self.work = self.root / "work"
        self.run_git(self.root, "init", "--bare", "--initial-branch=main", str(self.remote))
        self.run_git(self.root, "clone", str(self.remote), str(self.work))
        self.run_git(self.work, "config", "user.name", "Delivery test")
        self.run_git(self.work, "config", "user.email", "delivery@example.invalid")
        overlay = self.work / prepare.OVERLAY
        overlay.parent.mkdir(parents=True)
        overlay.write_text("old\n")
        self.run_git(self.work, "add", ".")
        self.run_git(self.work, "commit", "-m", "Initial main")
        self.run_git(self.work, "push", "origin", "main")
        self.revision = self.run_git(self.work, "rev-parse", "HEAD")
        self.real_git = prepare.git
        def scoped_git(*args):
            return self.run_git(self.work, *args)
        self.patcher = patch.object(prepare, "git", scoped_git)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def run_git(self, cwd, *args):
        return subprocess.check_output(["git", "-C", str(cwd), *args],
                                       text=True, stderr=subprocess.DEVNULL).strip()

    def update_overlay(self):
        (self.work / prepare.OVERLAY).write_text("new verified digests\n")

    def test_branch_publication_keeps_main_unchanged_and_retry_reuses_tree(self):
        self.update_overlay()
        branch = prepare.prepare(self.revision)
        self.assertEqual(self.run_git(self.remote, "rev-parse", "main"), self.revision)
        original = self.run_git(self.remote, "rev-parse", branch)
        # A retry starts from a fresh runner checkout, not the prior delivery branch.
        self.run_git(self.work, "checkout", "main")
        retry = self.root / "retry"
        self.run_git(self.root, "clone", str(self.remote), str(retry))
        self.run_git(retry, "config", "user.name", "Delivery test")
        self.run_git(retry, "config", "user.email", "delivery@example.invalid")
        self.work = retry
        self.update_overlay()
        self.assertEqual(prepare.prepare(self.revision), branch)
        self.assertEqual(self.run_git(self.remote, "rev-parse", branch), original)

    def test_no_change_creates_no_branch(self):
        self.assertIsNone(prepare.prepare(self.revision))
        self.assertEqual(self.run_git(self.remote, "branch", "--list", "delivery/*"), "")

    def test_retry_does_not_overwrite_different_branch_content(self):
        branch = f"delivery/dev-{self.revision}"
        self.run_git(self.work, "checkout", "-b", branch)
        (self.work / prepare.OVERLAY).write_text("different delivery\n")
        self.run_git(self.work, "add", ".")
        self.run_git(self.work, "commit", "-m", "Existing promotion")
        self.run_git(self.work, "push", "origin", branch)
        original = self.run_git(self.remote, "rev-parse", branch)
        retry = self.root / "retry"
        self.run_git(self.root, "clone", str(self.remote), str(retry))
        self.run_git(retry, "config", "user.name", "Delivery test")
        self.run_git(retry, "config", "user.email", "delivery@example.invalid")
        self.work = retry
        self.update_overlay()
        with self.assertRaisesRegex(ValueError, "differs"):
            prepare.prepare(self.revision)
        self.assertEqual(self.run_git(self.remote, "rev-parse", branch), original)

    def test_stale_main_is_rejected(self):
        (self.work / "README.md").write_text("advanced\n")
        self.run_git(self.work, "add", ".")
        self.run_git(self.work, "commit", "-m", "Advance main")
        self.run_git(self.work, "push", "origin", "main")
        with self.assertRaisesRegex(ValueError, "Main advanced"):
            prepare.prepare(self.revision)

    def test_main_advance_between_preparation_and_push_is_rejected(self):
        self.update_overlay()
        with patch.object(prepare, "require_current", side_effect=[None, ValueError("Main advanced")]):
            with self.assertRaisesRegex(ValueError, "Main advanced"):
                prepare.prepare(self.revision)
        self.assertEqual(self.run_git(self.remote, "branch", "--list", "delivery/*"), "")

    def test_other_tracked_change_is_rejected(self):
        self.run_git(self.work, "config", "core.autocrlf", "false")
        (self.work / "README.md").write_text("tracked\n")
        self.run_git(self.work, "add", ".")
        self.run_git(self.work, "commit", "-m", "Track README")
        self.run_git(self.work, "push", "origin", "main")
        revision = self.run_git(self.work, "rev-parse", "HEAD")
        (self.work / "README.md").write_text("modified\n")
        self.update_overlay()
        with self.assertRaisesRegex(ValueError, "only"):
            prepare.prepare(revision)


if __name__ == "__main__":
    unittest.main()
