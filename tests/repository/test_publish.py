"""Publication must preserve its inspected destination and native lifetime facts."""

from tools.ops.container_guard import require_container

require_container()

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in ("tools/ops/publish.sh", "tools/ops/inference_native.sh"):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(name, target)
        self.trace = self.root / "calls"
        # Executable fixture tools live on the read-only source mount. /tmp
        # remains noexec; private fixture state is written only under self.root.
        self.bin = Path("tests/fixtures/publish-tools").resolve()

    def run_publisher(self, scenario, action="publish/release"):
        return subprocess.run(
            ["bash", str(self.root / "tools/ops/publish.sh"), action],
            cwd=self.root,
            env={
                "PATH": str(self.bin) + os.pathsep + os.defpath,
                "PUBLISH_TAG_INPUT": "v0.1.0",
                "PUBLISH_TEST_MODE": scenario,
                "PUBLISH_TEST_TRACE": str(self.trace),
            },
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    def test_matching_url_rewrite_stops_before_github_or_push(self):
        result = self.run_publisher("matching")
        self.assertEqual(2, result.returncode, msg=result.stderr)
        self.assertIn("Git URL rewrite matches the captured push URL", result.stderr)
        calls = self.trace.read_text()
        self.assertIn("git config --null --get-regexp", calls)
        self.assertNotIn("gh ", calls)
        self.assertNotIn("git push", calls)

    def test_unreadable_routing_configuration_stops_before_github_or_push(self):
        result = self.run_publisher("config-error")
        self.assertEqual(2, result.returncode, msg=result.stderr)
        self.assertIn("Git URL routing configuration could not be inspected", result.stderr)
        calls = self.trace.read_text()
        self.assertIn("git config --null --get-regexp", calls)
        self.assertNotIn("gh ", calls)
        self.assertNotIn("git push", calls)

    def test_absent_and_unrelated_rewrites_reach_existing_release_rejection(self):
        for scenario in ("absent", "unrelated"):
            with self.subTest(scenario=scenario):
                self.trace.unlink(missing_ok=True)
                result = self.run_publisher(scenario)
                self.assertEqual(2, result.returncode, msg=result.stderr)
                self.assertIn("this tag already has a GitHub release", result.stderr)
                calls = self.trace.read_text()
                self.assertIn("gh repo view", calls)
                self.assertIn("gh api --hostname github.com --include", calls)
                self.assertNotIn("git push", calls)

    def test_unknown_retirement_cannot_be_classified_as_missing_release(self):
        (self.root / "tools/ops/inference_native.sh").write_text("""inference_native() {
    local operation=$1 status
    shift 3
    if ! "$inference_retirement_confirmed"; then
        printf 'continued after unknown retirement\\n' >> "$PUBLISH_TEST_TRACE"
        return 97
    fi
    if "$@"; then status=0; else status=$?; fi
    if [[ $operation == 'GitHub resource inspection' ]]; then
        inference_retirement_confirmed=false
        inference_diagnostic='Injected unknown native retirement.'
        return 1
    fi
    return "$status"
}
""")
        result = self.run_publisher("unknown")
        self.assertEqual(1, result.returncode, msg=result.stderr)
        calls = self.trace.read_text()
        self.assertIn("gh api --hostname github.com --include", calls)
        self.assertNotIn("continued after unknown retirement", calls)
        self.assertNotIn("git archive", calls)
        self.assertNotIn("git push", calls)
        self.assertEqual(1, len(list((self.root / ".work").glob("publication.*"))))

    def test_source_inventory_download_is_verified_before_draft_publication(self):
        state = self.root / ".work/wire"
        (state / "wheels").mkdir(parents=True)
        (state / "admission").write_text("publication fixture admission\n")
        result = self.run_publisher("publish")
        self.assertEqual(0, result.returncode, msg=result.stderr)
        uploads = Path(str(self.trace) + ".uploads")
        self.assertEqual(
            {
                "wire-0.1.0-py3-none-any.whl",
                "wire-0.1.0.tar.gz",
                "source.json",
                "sha256.json",
                "release-build.log",
                "release-test.log",
            },
            {path.name for path in uploads.iterdir()},
        )
        calls = self.trace.read_text()
        self.assertLess(calls.index("gh release download"), calls.index("gh release edit"))
        self.assertIn("--draft=false", calls)

    def test_changed_downloaded_source_inventory_keeps_release_draft(self):
        state = self.root / ".work/wire"
        (state / "wheels").mkdir(parents=True)
        (state / "admission").write_text("publication fixture admission\n")
        result = self.run_publisher("corrupt-source")
        self.assertEqual(2, result.returncode, msg=result.stderr)
        self.assertIn("downloaded bytes differ from the qualified artifact", result.stderr)
        calls = self.trace.read_text()
        self.assertIn("gh release create", calls)
        self.assertIn("gh release download", calls)
        self.assertNotIn("gh release edit", calls)
        self.assertEqual(1, len(list((self.root / ".work").glob("publication.*"))))

    def test_first_pages_build_can_be_absent_before_matching_live_revision(self):
        result = self.run_publisher("pages-first", "publish/pages")
        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertIn("( pending)", result.stdout)
        self.assertIn("Published https://numpde.github.io/pay-to-play-wire/ from " + "0" * 39 + "1", result.stdout)
        calls = self.trace.read_text()
        self.assertEqual(1, calls.count("--method POST"))
        self.assertIn("sleep 5", calls)
        self.assertIn("curl ", calls)

    def test_pages_build_server_failure_is_fatal_without_polling_or_live_fetch(self):
        result = self.run_publisher("pages-error", "publish/pages")
        self.assertEqual(2, result.returncode, msg=result.stderr)
        self.assertIn("Cannot inspect GitHub resource repos/numpde/pay-to-play-wire/pages/builds/latest", result.stderr)
        calls = self.trace.read_text()
        self.assertEqual(1, calls.count("repos/numpde/pay-to-play-wire/pages/builds/latest"))
        self.assertEqual(1, calls.count("--method POST"))
        self.assertNotIn("sleep 5", calls)
        self.assertNotIn("curl ", calls)
