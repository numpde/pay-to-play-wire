"""Packaging must preserve pre-build source inputs, including ordinary additions."""

from tools.ops.container_guard import require_container

require_container()

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.ops.package import _source_payload, _wheel_payload


class PackageCompletenessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.inventory = {}
        self.add_input("pyproject.toml", b'[project]\nname = "wire"\nversion = "0.4.0"\n')
        self.add_input("README.md", b"Package documentation\n")
        self.add_input("MANIFEST.in", b"recursive-include src *.py *.json\n")
        self.add_input("src/wire/__init__.py", b'"""Wire formats."""\n')
        self.add_input("src/wire/invoice/__init__.py", b'"""Invoices."""\n')
        self.add_input("src/wire/vectors/invoice.json", b'{"cases": []}\n')
        self.add_input("docs/index.md", b"Consumer guide\n")
        for name in (
            "PKG-INFO",
            "setup.cfg",
            "src/wire.egg-info/PKG-INFO",
            "src/wire.egg-info/SOURCES.txt",
            "src/wire.egg-info/dependency_links.txt",
            "src/wire.egg-info/requires.txt",
            "src/wire.egg-info/top_level.txt",
        ):
            self.write(name, b"synthetic setuptools metadata\n")

    def write(self, name, data):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def add_input(self, name, data):
        self.write(name, data)
        self.inventory[name] = hashlib.sha256(data).hexdigest()

    def wheel(self, payload):
        wheel = self.root / "wire-0.4.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            for name, data in payload.items():
                archive.writestr(name, data)
            archive.writestr("wire-0.4.0.dist-info/METADATA", b"Name: wire\nVersion: 0.4.0\n")
        return wheel

    def test_new_module_and_vector_flow_from_source_without_an_inventory_edit(self):
        self.add_input("src/wire/authorization.py", b"PROFILE = 1\n")
        self.add_input("src/wire/vectors/authorization.json", b'{"profile": 1}\n')
        project, expected = _source_payload(self.source, self.inventory)
        self.assertEqual("wire", project["name"])
        payload = {
            name.removeprefix("src/"): (self.source / name).read_bytes()
            for name in self.inventory
            if name.startswith("src/wire/")
        }
        self.assertEqual(set(payload), expected)
        self.assertEqual(payload, _wheel_payload(self.wheel(payload), expected))

    def test_common_wheel_and_sdist_omission_cannot_hide_a_source_module(self):
        _, expected = _source_payload(self.source, self.inventory)
        (self.source / "src/wire/invoice/__init__.py").unlink()
        payload = {"wire/__init__.py": b'"""Wire formats."""\n', "wire/vectors/invoice.json": b'{"cases": []}\n'}
        with self.assertRaisesRegex(ValueError, "sdist source inventory"):
            _source_payload(self.source, self.inventory)
        with self.assertRaisesRegex(ValueError, "wheel runtime inventory"):
            _wheel_payload(self.wheel(payload), expected)

    def test_self_declared_forbidden_sdist_member_is_rejected(self):
        self.write("tests/private.txt", b"must not ship\n")
        self.write("src/wire.egg-info/SOURCES.txt", b"tests/private.txt\n")
        with self.assertRaisesRegex(ValueError, "sdist source inventory"):
            _source_payload(self.source, self.inventory)

    def test_source_byte_change_cannot_reuse_pre_build_inventory(self):
        self.write("src/wire/__init__.py", b"changed after capture\n")
        with self.assertRaisesRegex(ValueError, "sdist source bytes"):
            _source_payload(self.source, self.inventory)

    def test_unsafe_inventory_path_is_rejected(self):
        self.inventory["src/wire/../../escape.py"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "unsafe path"):
            _source_payload(self.source, self.inventory)


if __name__ == "__main__":
    unittest.main()
