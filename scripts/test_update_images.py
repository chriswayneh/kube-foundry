import importlib.util
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location("update_images", Path(__file__).with_name("update-images.py"))
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


class ImageUpdates(unittest.TestCase):
    def test_complete_digest_render(self):
        calls = []

        def resolve(component, revision):
            calls.append((component, revision))
            return "sha256:" + "b" * 64

        result = updater.render("a" * 40, resolve)
        self.assertEqual(len(calls), 3)
        self.assertEqual(result.count("digest: sha256:"), 3)
        self.assertNotIn("newTag:", result)
        self.assertIn("../../phase7/dev", result)

    def test_invalid_revision_never_calls_registry(self):
        with self.assertRaises(ValueError):
            updater.render("main", lambda *_: self.fail("Registry should not be called"))

    def test_invalid_digest_is_rejected(self):
        with self.assertRaises(ValueError):
            updater.render("a" * 40, lambda *_: "latest")

    def test_registry_failure_returns_no_partial_render(self):
        def resolve(component, _revision):
            if component == "web":
                raise OSError("Registry unavailable")
            return "sha256:" + "b" * 64

        with self.assertRaises(OSError):
            updater.render("a" * 40, resolve)


if __name__ == "__main__":
    unittest.main()
