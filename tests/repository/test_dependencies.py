"""Current artifact bytes, complete membership and closed tool declarations."""

from tools.ops.container_guard import require_container

require_container()

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.dependencies.wheels import check, make_declaration, requirements


class DependencyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.depot = self.root / "dependencies"
        self.depot.mkdir()
        self.wheel = self.depot / "example-1.0-py3-none-any.whl"
        self.wheel.write_bytes(b"synthetic wheel hash subject")
        self.lock = self.root / "runtime.lock"
        self.lock.write_text(f"example==1.0\n    --hash=sha256:{hashlib.sha256(self.wheel.read_bytes()).hexdigest()}\n")
        self.tool_path = self.root / "make.json"
        self.tool = json.loads(Path("requirements/make.json").read_bytes())
        self.tool_file = self.depot / self.tool["file"]
        self.tool_file.write_bytes(b"synthetic Debian hash subject")
        self.tool.update(size=self.tool_file.stat().st_size, sha256=hashlib.sha256(self.tool_file.read_bytes()).hexdigest())
        self.tool_path.write_text(json.dumps(self.tool))

    def test_current_complete_exact_bytes_are_accepted_and_changed_bytes_are_rejected(self):
        check(self.lock, self.depot, self.tool_path)
        for path in (self.wheel, self.tool_file):
            with self.subTest(path=path.name):
                original = path.read_bytes()
                path.write_bytes(original + b"changed")
                with self.assertRaises(ValueError):
                    check(self.lock, self.depot, self.tool_path)
                path.write_bytes(original)

    def test_missing_extra_duplicate_and_symlinked_artifacts_cannot_reuse_admission(self):
        original = self.wheel.read_bytes()
        self.wheel.unlink()
        with self.assertRaises(ValueError):
            check(self.lock, self.depot, self.tool_path)
        self.wheel.write_bytes(original)
        for name in ("extra.whl", "example-1.0-py2-none-any.whl", ".complete"):
            path = self.depot / name
            path.write_bytes(original)
            with self.subTest(name=name), self.assertRaises(ValueError):
                check(self.lock, self.depot, self.tool_path)
            path.unlink()
        self.wheel.unlink()
        self.wheel.symlink_to(self.tool_file)
        with self.assertRaises(OSError):
            check(self.lock, self.depot, self.tool_path)

    def test_lock_rejects_unhashed_duplicate_and_unrecognized_entries(self):
        for text in ("example==1.0\n", self.lock.read_text() * 2, "--hash=sha256:" + "a" * 64, "-r other.lock"):
            self.lock.write_text(text)
            with self.subTest(text=text[:20]), self.assertRaises(ValueError):
                requirements(self.lock)

    def test_tool_declaration_cannot_add_network_authority_or_coerce_types(self):
        for updates in ({"url": "https://example.invalid/make.deb"}, {"size": True}, {"file": "../make.deb"}, {"extra": 1}):
            self.tool_path.write_text(json.dumps(dict(self.tool, **updates)))
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                make_declaration(self.tool_path)
        self.tool_path.write_text(json.dumps(self.tool)[:-1] + ',"name":"make"}')
        with self.assertRaises(ValueError):
            make_declaration(self.tool_path)
