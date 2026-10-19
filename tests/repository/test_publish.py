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

    def run_publisher(self, scenario):
        return subprocess.run(
            ["bash", str(self.root / "tools/ops/publish.sh"), "publish/release"],
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
