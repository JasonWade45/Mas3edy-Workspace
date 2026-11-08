import tempfile
import unittest
from pathlib import Path
from security import resolve_inside
from filetools import make_proposal, approve_proposal

class SecurityAndApprovalTests(unittest.TestCase):
    def test_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                resolve_inside(d, "../outside.txt")

    def test_write_requires_approval_and_creates_backup(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "hello.txt"
            p.write_text("old", encoding="utf-8")
            proposal = make_proposal(d, "write", "hello.txt", content="new")
            self.assertEqual(p.read_text(), "old")
            result = approve_proposal(d, proposal)
            self.assertEqual(p.read_text(), "new")
            self.assertIn("تم حفظ الملف", result)

    def test_stale_proposal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "hello.txt"
            p.write_text("old", encoding="utf-8")
            proposal = make_proposal(d, "write", "hello.txt", content="new")
            p.write_text("changed", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                approve_proposal(d, proposal)

if __name__ == "__main__":
    unittest.main(verbosity=2)
