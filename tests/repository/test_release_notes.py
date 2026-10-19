"""Release prose uses one source line per paragraph or list item."""

from tools.ops.container_guard import require_container

require_container()

import re
import tempfile
import unittest
from pathlib import Path

FENCE = re.compile(r" {0,3}(`{3,}|~{3,})(.*)")
HEADING = re.compile(r" {0,3}#{1,6}(?:\s|$)")
LIST_ITEM = re.compile(r"\s*(?:[-+*]|[0-9]{1,9}[.)])\s+\S")


def formatting_problems(text):
    """Locate wrapped prose and explicit Markdown breaks outside fenced code.

    Headings and new list markers start blocks. A following prose line without
    a blank separator continues the preceding paragraph or list item.
    """
    problems = []
    fence = None
    previous_prose = False
    for number, line in enumerate(text.splitlines(), 1):
        marker = FENCE.fullmatch(line)
        if fence is not None:
            opening, _ = fence
            if marker and marker[1][0] == opening[0] and len(marker[1]) >= len(opening) and not marker[2].strip():
                fence = None
            continue
        if marker and (marker[1][0] != "`" or "`" not in marker[2]):
            fence = (marker[1], number)
            previous_prose = False
            continue
        if not line.strip() or HEADING.match(line):
            previous_prose = False
            continue
        if previous_prose and not LIST_ITEM.match(line):
            problems.append((number, "Manual line wrap: keep each paragraph or list item on one source line."))
        if line.endswith("  ") or (len(line) - len(line.rstrip("\\"))) % 2:
            problems.append((number, "Explicit Markdown line break: remove trailing double spaces or the break backslash."))
        previous_prose = True
    if fence is not None:
        problems.append((fence[1], "Unclosed code fence: close the block so following prose can be checked."))
    return problems


def release_note_problems(directory):
    paths = sorted(directory.glob("*_release_v*.md"))
    if not paths:
        return [f"Cannot check release notes: no *_release_v*.md files found in {directory}."]
    return [
        f"{path}:{number}: {problem}"
        for path in paths
        for number, problem in formatting_problems(path.read_text(encoding="utf-8"))
    ]


class ReleaseNoteTests(unittest.TestCase):
    def test_repository_release_notes_have_no_manual_line_breaks(self):
        problems = release_note_problems(Path("notes"))
        self.assertEqual([], problems, msg="\n".join(problems))

    def test_discovers_future_release_notes_and_reports_path_and_line(self):
        with tempfile.TemporaryDirectory() as temporary:
            notes = Path(temporary)
            (notes / "001_extraction.txt").write_text("Unrelated\nwrapped notes.\n")
            (notes / "002_release_v0.1.0.md").write_text("One paragraph.\n")
            future = notes / "999_release_v9.2.3.md"
            future.write_text("A manually wrapped\nrelease paragraph.\n")
            problems = release_note_problems(notes)
            self.assertEqual(1, len(problems))
            self.assertIn(f"{future}:2:", problems[0])
            self.assertIn("one source line", problems[0])

    def test_missing_release_notes_cannot_pass_vacuously(self):
        with tempfile.TemporaryDirectory() as temporary:
            problems = release_note_problems(Path(temporary))
        self.assertEqual(1, len(problems))
        self.assertIn("no *_release_v*.md files", problems[0])

    def test_rejects_wrapped_paragraphs_and_list_continuations(self):
        for text in (
            "First part\nsecond part.\n",
            "- First part\n  second part.\n",
            "1. First part\nsecond part.\n",
            "  - Nested item\n    continued.\n",
        ):
            with self.subTest(text=text):
                self.assertEqual([2], [number for number, _ in formatting_problems(text)])

    def test_allows_single_line_blocks_and_fenced_code(self):
        text = (
            "# Release\n## Changes\n" + "One long paragraph. " * 50 + "\n\nAnother paragraph.\n\n"
            "- First item.\n+ Second item.\n* Third item.\n  - Nested item.\n1. Ordered item.\n2) Another item.\n\n"
            "```text\ncode can have\nmultiple lines.  \n```\n\n"
            "~~~text\nMore code.\\\nStill code.\n~~~\n"
        )
        self.assertEqual([], formatting_problems(text))

    def test_fences_require_matching_marker_and_sufficient_length(self):
        text = "````text\n```\n~~~\ncode\n````\nParagraph\ncontinued.\n"
        self.assertEqual([7], [number for number, _ in formatting_problems(text)])

    def test_unclosed_fence_cannot_hide_unchecked_prose(self):
        problems = formatting_problems("~~~text\nUnclosed block.\n")
        self.assertEqual([1], [number for number, _ in problems])
        self.assertIn("Unclosed code fence", problems[0][1])

    def test_rejects_explicit_breaks_but_allows_escaped_backslash(self):
        for text in ("Paragraph.  \n", "Paragraph.\\\n"):
            with self.subTest(text=text):
                self.assertEqual([1], [number for number, _ in formatting_problems(text)])
        self.assertEqual([], formatting_problems("Literal backslash.\\\\\n"))
