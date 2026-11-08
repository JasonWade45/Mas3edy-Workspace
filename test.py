import tempfile
import unittest
from pathlib import Path
from security import resolve_inside, is_sensitive
from filetools import make_proposal, approve_proposal

class SecurityAndApprovalTests(unittest.TestCase):
    def test_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                resolve_inside(d, "../outside.txt")

    def test_env_example_allowed_but_env_rejected(self):
        self.assertFalse(is_sensitive(Path(".env.example")))
        self.assertTrue(is_sensitive(Path(".env")))
        self.assertTrue(is_sensitive(Path("sub/.env")))
        self.assertTrue(is_sensitive(Path(".ssh/config")))

    def test_write_requires_approval_and_creates_backup(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "hello.txt"
            p.write_text("old", encoding="utf-8")
            proposal = make_proposal(d, "write", "hello.txt", content="new")
            self.assertEqual(p.read_text(encoding="utf-8"), "old")
            result = approve_proposal(d, proposal)
            self.assertEqual(p.read_text(encoding="utf-8"), "new")
            self.assertIn("تم حفظ الملف", result)

    def test_stale_proposal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "hello.txt"
            p.write_text("old", encoding="utf-8")
            proposal = make_proposal(d, "write", "hello.txt", content="new")
            p.write_text("changed", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                approve_proposal(d, proposal)

    def test_proposal_bound_to_root(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            Path(a, "hello.txt").write_text("old", encoding="utf-8")
            Path(b, "hello.txt").write_text("other", encoding="utf-8")
            proposal = make_proposal(a, "write", "hello.txt", content="new")
            with self.assertRaises(RuntimeError):
                approve_proposal(b, proposal)
            self.assertEqual(Path(b, "hello.txt").read_text(encoding="utf-8"), "other")

    def test_move_to_new_nested_dir(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "src.txt").write_text("hello", encoding="utf-8")
            proposal = make_proposal(d, "move", "src.txt", destination="sub/deep/dst.txt")
            approve_proposal(d, proposal)
            self.assertTrue(Path(d, "sub", "deep", "dst.txt").exists())
            self.assertFalse(Path(d, "src.txt").exists())

if __name__ == "__main__":
    unittest.main(verbosity=2)