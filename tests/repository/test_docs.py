"""The public guide's Python examples run in their documented order."""

from tools.ops.container_guard import require_container

require_container()

import re
import unittest
from pathlib import Path


class DocumentationTests(unittest.TestCase):
    def test_user_guide_python_examples_execute_in_order(self):
        guide = Path("docs/index.md")
        text = guide.read_text(encoding="utf-8")
        examples = list(re.finditer(r"^```python\n(.*?)^```$", text, re.MULTILINE | re.DOTALL))
        self.assertGreater(len(examples), 0, msg="The user guide must contain runnable Python examples.")
        namespace = {"__name__": "__documentation__"}
        for example in examples:
            line = text.count("\n", 0, example.start()) + 1
            with self.subTest(path=str(guide), line=line):
                exec(compile(example[1], f"{guide}:{line}", "exec"), namespace)
