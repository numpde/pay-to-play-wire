"""Positive engine dispatch and fail-closed admission for the real codec launcher."""

from tools.ops.container_guard import require_container

require_container()

import hashlib
import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

INPUTS = (
    "containers/invoice/Dockerfile",
    "containers/invoice/Dockerfile.dockerignore",
    "requirements/invoice.lock",
    "requirements/make.json",
    "tools/dependencies/wheels.py",
    "tools/ops/container_guard.py",
)
IMAGE_ID = "sha256:" + "a" * 64


class InvoiceLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in (
            *INPUTS,
            "tools/ops/invoice.sh",
            "tools/ops/docker_client.sh",
            "tools/ops/inference_native.sh",
            "AGENTS.md",
            "README.md",
            "Makefile",
            "pyproject.toml",
            "MANIFEST.in",
            "ruff.toml",
        ):
            destination = self.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(name, destination)
        for name in (".work/invoice", "bin"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        shutil.copytree("src", self.root / "src")
        shutil.copytree("tests", self.root / "tests")
        shutil.copytree("docs", self.root / "docs")
        shutil.copytree("notes", self.root / "notes")
        self.record = self.root / ".work/invoice/admission"
        self.record.write_text(
            IMAGE_ID
            + "\n"
            + "".join(hashlib.sha256((self.root / name).read_bytes()).hexdigest() + "  " + name + "\n" for name in INPUTS)
        )
        # Inject a recording engine at the existing client boundary. Invoke its
        # shell explicitly so the test keeps /tmp mounted noexec.
        (self.root / "tools/ops/docker_client.sh").write_text(
            'docker_client_prepare() { engine=(bash "$repository_root/bin/docker"); }\ndocker_client_cleanup() { :; }\n'
        )
        self.trace = self.root / "engine.trace"
        self.label = hashlib.sha256(self.record.read_bytes().split(b"\n", 1)[1]).hexdigest()
        executable = self.root / "bin/docker"
        executable.write_text("""#!/bin/bash
set -eu
printf '%s\\0' "$@" >> "$CODEC_ENGINE_TRACE"
case "$1" in
    image)
        if [[ -f "$CODEC_ENGINE_TRACE.label" ]]; then label=$(cat "$CODEC_ENGINE_TRACE.label"); else label=$TEST_LABEL; fi
        if [[ -n "${TEST_OBSERVED_RECEIPT:-}" ]]; then cat -- "$TEST_OBSERVED_RECEIPT"
        else printf '%s %s\\n' "$TEST_IMAGE" "$label"; fi
        ;;
    create)
        while [[ $# -gt 0 ]]; do
            if [[ "$1" == --cidfile ]]; then printf '%064d\\n' 1 > "$2"; break; fi
            shift
        done
        printf '%064d\\n' 1
        ;;
    start) exit "${TEST_START_STATUS:-0}" ;;
    rm) exit "${TEST_REMOVE_STATUS:-0}" ;;
    build)
        context=${@: -1}
        if [[ -n "${TEST_MUTATE_INPUT:-}" ]]; then printf '\\n# changed during build\\n' >> "$TEST_MUTATE_INPUT"; fi
        cp -a -- "$context" "$CODEC_ENGINE_TRACE.context"
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --iidfile) cp -- "$CODEC_ENGINE_TRACE.id" "$2"; shift ;;
                --label) printf '%s' "${2#*=}" > "$CODEC_ENGINE_TRACE.label"; shift ;;
            esac
            shift
        done
        ;;
    *) exit 97 ;;
esac
""")
        executable.chmod(0o700)

    def run_launcher(self, operation, *, additions=None):
        return subprocess.run(
            ["bash", str(self.root / "tools/ops/invoice.sh"), operation],
            cwd=self.root,
            env={
                "PATH": str(self.root / "bin") + os.pathsep + os.defpath,
                "CODEC_ENGINE_TRACE": str(self.trace),
                "TEST_IMAGE": IMAGE_ID,
                "TEST_LABEL": self.label,
                **(additions or {}),
            },
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    def test_successful_dispatch_grants_only_offline_readonly_sources(self):
        result = self.run_launcher("test/invoice")
        self.assertEqual(0, result.returncode, msg=result.stderr)
        args = self.trace.read_bytes().decode().split("\0")[:-1]
        self.assertIn(IMAGE_ID, args)
        self.assertEqual("none", args[args.index("--network") + 1])
        self.assertIn("--read-only", args)
        self.assertEqual("never", args[args.index("--pull") + 1])
        self.assertIn("ALL", args)
        mounts = [args[index + 1] for index, value in enumerate(args) if value == "--mount"]
        self.assertTrue(mounts)
        self.assertTrue(all(mount.endswith(",readonly") for mount in mounts))
        self.assertTrue(all("docker.sock" not in mount and ".git" not in mount for mount in mounts))
        self.assertFalse(any("dst=/workspace/notes," in mount for mount in mounts))
        self.assertIn("discover", args)
        self.assertIn("tests/invoice", args)

    def test_repository_checks_receive_readonly_release_notes(self):
        result = self.run_launcher("test/repository")
        self.assertEqual(0, result.returncode, msg=result.stderr)
        args = self.trace.read_bytes().decode().split("\0")[:-1]
        mounts = [args[index + 1] for index, value in enumerate(args) if value == "--mount"]
        self.assertEqual(
            [f"type=bind,src={self.root}/notes,dst=/workspace/notes,readonly"],
            [mount for mount in mounts if "dst=/workspace/notes," in mount],
        )

    def test_missing_or_symlinked_notes_are_rejected_before_engine_dispatch(self):
        notes = self.root / "notes"
        outside = self.root / "outside-notes"
        notes.rename(outside)
        result = self.run_launcher("test/repository")
        self.assertEqual(2, result.returncode, msg=result.stderr)
        self.assertFalse(self.trace.exists())
        notes.symlink_to(outside, target_is_directory=True)
        result = self.run_launcher("test/repository")
        self.assertEqual(2, result.returncode, msg=result.stderr)
        self.assertFalse(self.trace.exists())
        notes.unlink()
        outside.rename(notes)
        (notes / "999_release_v9.2.3.md").symlink_to(self.root / "README.md")
        result = self.run_launcher("test/repository")
        self.assertEqual(2, result.returncode, msg=result.stderr)
        self.assertIn("symlinked source below notes", result.stderr)
        self.assertFalse(self.trace.exists())

    def test_changed_dependency_lock_is_rejected_before_engine_dispatch(self):
        path = self.root / "requirements/invoice.lock"
        path.write_bytes(path.read_bytes() + b"\n# changed\n")
        result = self.run_launcher("test/invoice")
        self.assertEqual(2, result.returncode)
        self.assertIn("build inputs changed", result.stderr)
        self.assertFalse(self.trace.exists())

    def test_missing_or_malformed_image_record_never_dispatches(self):
        for raw in (b"", (IMAGE_ID + "\n").encode(), b"sha256:bad\n", self.record.read_bytes() + b"\0"):
            with self.subTest(raw=raw[:15]):
                self.record.write_bytes(raw)
                result = self.run_launcher("test/invoice")
                self.assertNotEqual(0, result.returncode)
                self.assertFalse(self.trace.exists())
        self.record.unlink()
        self.assertEqual(2, self.run_launcher("test/invoice").returncode)
        self.assertFalse(self.trace.exists())

    def test_symlinked_source_is_rejected_before_engine_dispatch(self):
        path = self.root / "src"
        path.rename(self.root / "elsewhere")
        path.symlink_to(self.root / "elsewhere", target_is_directory=True)
        result = self.run_launcher("test/invoice")
        self.assertEqual(2, result.returncode)
        self.assertIn("without a symlink", result.stderr)
        self.assertFalse(self.trace.exists())

    def test_build_requires_explicitly_acquired_dependencies(self):
        result = self.run_launcher("build")
        self.assertEqual(2, result.returncode)
        self.assertIn("directory without a symlink", result.stderr)
        self.assertFalse(self.trace.exists())

    def test_build_admits_only_exact_engine_image_ids(self):
        (self.root / ".work/invoice/wheels").mkdir()
        previous = self.record.read_bytes()
        for output, expected_status in (
            (IMAGE_ID, 0),
            (IMAGE_ID + "\n", 0),
            (IMAGE_ID + "\n\n", 2),
            ("bad", 2),
            (IMAGE_ID + "\0", 2),
        ):
            with self.subTest(expected_status=expected_status, size=len(output)):
                self.trace.unlink(missing_ok=True)
                # Write the synthetic engine receipt through bash, preserving NULs.
                receipt = self.root / "engine-id"
                receipt.write_bytes(output.encode())
                (self.root / "engine.trace.id").write_bytes(receipt.read_bytes())
                result = self.run_launcher("build")
                self.assertEqual(expected_status, result.returncode, msg=result.stderr)
                self.assertEqual(previous, self.record.read_bytes())

    def test_failed_build_keeps_previous_admission(self):
        (self.root / ".work/invoice/wheels").mkdir()
        previous = self.record.read_bytes()
        (self.root / "bin/docker").write_text("#!/bin/bash\nexit 23\n")
        result = self.run_launcher("build")
        self.assertEqual(23, result.returncode)
        self.assertEqual(previous, self.record.read_bytes())
        self.assertEqual([], list((self.root / ".work/invoice").glob(".build.*")))

    def test_observed_image_metadata_must_match_exactly_before_execution_or_publication(self):
        (self.root / ".work/invoice/wheels").mkdir()
        (self.root / "engine.trace.id").write_text(IMAGE_ID)
        previous = self.record.read_bytes()
        receipt = self.root / "observed-receipt"
        correct = (IMAGE_ID + " " + self.label + "\n").encode()
        for operation in ("test/invoice", "build"):
            for raw in (
                correct[:-1],
                correct + b"\n",
                correct + b"\0",
                b"bad " + correct.split(b" ", 1)[1],
                correct[:-65] + b"0" * 64 + b"\n",
            ):
                with self.subTest(operation=operation, receipt=raw):
                    self.trace.unlink(missing_ok=True)
                    receipt.write_bytes(raw)
                    result = self.run_launcher(operation, additions={"TEST_OBSERVED_RECEIPT": str(receipt)})
                    self.assertEqual(2, result.returncode, msg=result.stderr)
                    self.assertIn("observed image identity or input label differs", result.stderr)
                    self.assertEqual(previous, self.record.read_bytes())
                    if operation == "test/invoice":
                        self.assertNotIn("create", self.trace.read_bytes().decode().split("\0"))

    def test_cleanup_failure_changes_success_but_preserves_primary_failure(self):
        (self.root / "tools/ops/docker_client.sh").write_text(
            'docker_client_prepare() { engine=(bash "$repository_root/bin/docker"); }\ndocker_client_cleanup() { return 17; }\n'
        )
        for engine_status, expected in ((0, 17), (23, 23)):
            with self.subTest(engine_status=engine_status):
                self.assertEqual(
                    expected, self.run_launcher("test/invoice", additions={"TEST_START_STATUS": str(engine_status)}).returncode
                )

    def test_real_make_preserves_literal_network_interface_and_blocks_alias_shadowing(self):
        launcher = self.root / "tools/ops/invoice.sh"
        launcher.write_text('printf "%s\\n" "$1" "${NETWORK_INTERFACE_INPUT-ABSENT}"; [[ ! -v NETWORK_INTERFACE ]]\n')
        sentinel = self.root / "expanded"
        literal = f"$(shell touch {sentinel})"
        result = subprocess.run(
            [
                "make",
                "--no-print-directory",
                "-s",
                "dependencies/download",
                f"NETWORK_INTERFACE={literal}",
                f"NETWORK_INTERFACE_INPUT=$(shell touch {sentinel})",
            ],
            cwd=self.root,
            env={"PATH": os.defpath},
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertEqual(["download", literal], result.stdout.splitlines())
        self.assertFalse(sentinel.exists())
        self.assertFalse(self.trace.exists())
        result = subprocess.run(
            ["make", "--no-print-directory", "-s", "dependencies/download", "NETWORK_INTERFACE=lo"],
            cwd=self.root,
            env={"PATH": os.defpath, "NETWORK_INTERFACE": "ambient"},
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertEqual(["download", "lo"], result.stdout.splitlines())

    def test_printed_package_check_has_artifacts_and_no_source_import_mount(self):
        (self.root / ".work/dist").mkdir()
        (self.root / ".work/invoice/wheels").mkdir()
        shutil.copyfile("tools/ops/package.py", self.root / "tools/ops/package.py")
        shutil.copyfile("requirements/runtime.lock", self.root / "requirements/runtime.lock")
        shutil.copyfile("requirements/pydantic.lock", self.root / "requirements/pydantic.lock")
        result = subprocess.run(
            ["bash", str(self.root / "tools/ops/invoice.sh"), "--print", "test/package"],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(0, result.returncode, msg=result.stderr)
        args = shlex.split(result.stdout)
        self.assertNotIn("PYTHONPATH=/workspace/src", args)
        mounts = [args[index + 1] for index, value in enumerate(args) if value == "--mount"]
        self.assertTrue(all(mount.endswith(",readonly") for mount in mounts))
        self.assertTrue(any("dst=/artifacts," in mount for mount in mounts))
        self.assertFalse(any("dst=/workspace/src," in mount for mount in mounts))
        self.assertFalse(self.trace.exists())

    def test_build_captures_complete_declared_inputs_and_excludes_private_canary(self):
        (self.root / ".work/invoice/wheels").mkdir()
        (self.root / "engine.trace.id").write_text(IMAGE_ID)
        private = self.root / ".codex/private-canary"
        private.parent.mkdir()
        private.write_text("must not reach builder")
        result = self.run_launcher("build")
        self.assertEqual(0, result.returncode, msg=result.stderr)
        captured = self.root / "engine.trace.context"
        self.assertEqual(set(INPUTS), {str(path.relative_to(captured)) for path in captured.rglob("*") if path.is_file()})
        for name in INPUTS:
            self.assertEqual((self.root / name).read_bytes(), (captured / name).read_bytes())

    def test_changed_copied_helper_invalidates_image_admission(self):
        for name in ("tools/dependencies/wheels.py", "tools/ops/container_guard.py"):
            with self.subTest(name=name):
                path = self.root / name
                original = path.read_bytes()
                path.write_bytes(original + b"\n# changed\n")
                result = self.run_launcher("test/invoice")
                self.assertEqual(2, result.returncode)
                self.assertIn("build inputs changed", result.stderr)
                self.assertFalse(self.trace.exists())
                path.write_bytes(original)

    def test_build_uses_captured_bytes_when_live_input_changes(self):
        (self.root / ".work/invoice/wheels").mkdir()
        (self.root / "engine.trace.id").write_text(IMAGE_ID)
        name = "tools/dependencies/wheels.py"
        live = self.root / name
        original = live.read_bytes()
        result = self.run_launcher("build", additions={"TEST_MUTATE_INPUT": str(live)})
        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertEqual(original, (self.root / "engine.trace.context" / name).read_bytes())
        self.assertNotEqual(original, live.read_bytes())
        self.trace.unlink()
        result = self.run_launcher("test/invoice")
        self.assertEqual(2, result.returncode)
        self.assertIn("build inputs changed", result.stderr)
        self.assertFalse(self.trace.exists())
