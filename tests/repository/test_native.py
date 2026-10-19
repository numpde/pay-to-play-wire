"""Exercise the actual native owner when public output cannot be drained."""

from tools.ops.container_guard import require_container

require_container()

import os
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


class NativeRetirementTests(unittest.TestCase):
    def test_success_and_failure_status_are_reachable(self):
        for status in (0, 23):
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    'source tools/ops/inference_native.sh; inference_native probe 5 stdio bash -c "exit $1"',
                    "bash",
                    str(status),
                ],
                cwd=Path.cwd(),
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(status, result.returncode, msg=result.stderr.decode())

    def test_cancellation_retires_child_with_undrained_stdout_and_stderr(self):
        for stream in ("stdout", "stderr"):
            with self.subTest(stream=stream), tempfile.TemporaryDirectory() as temporary:
                ready = Path(temporary) / "child.pid"
                script = """source tools/ops/inference_native.sh
inference_native blocked untimed stdio bash -c '
    printf "%s" "$$" > "$1"
    if [[ "$2" == stderr ]]; then exec 1>&2; fi
    while :; do printf "%010000d" 1; done
' bash "$1" "$2"
"""
                process = subprocess.Popen(
                    ["bash", "-c", script, "bash", str(ready), stream],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                try:
                    deadline = time.monotonic() + 5
                    while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertTrue(ready.is_file(), msg="The intended blocked writer was never reached.")
                    child = int(ready.read_text())
                    time.sleep(0.05)
                    process.send_signal(signal.SIGTERM)
                    self.assertEqual(143, process.wait(timeout=5))
                    process.communicate(timeout=5)
                    with self.assertRaises(ProcessLookupError):
                        os.kill(child, 0)
                finally:
                    if process.poll() is None:
                        process.send_signal(signal.SIGTERM)
                    process.communicate(timeout=5)
