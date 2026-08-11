import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).parents[1]
    / "skills"
    / "soft-wrap"
    / "scripts"
    / "soft_wrap.py"
)
SPEC = importlib.util.spec_from_file_location("soft_wrap", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
SOFT_WRAP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SOFT_WRAP
SPEC.loader.exec_module(SOFT_WRAP)


class ProseTest(unittest.TestCase):
    def test_finds_and_fixes_a_wrapped_sentence(self):
        source = "A report without events needs an explicit\nzero rather than an empty object.\n"

        violations = SOFT_WRAP.analyze_text(source, "prose")
        corrected, count = SOFT_WRAP.apply_safe_fixes(source, "prose")

        self.assertEqual([2], [item.line_index + 1 for item in violations])
        self.assertEqual(1, count)
        self.assertEqual(
            "A report without events needs an explicit zero rather than an empty object.\n",
            corrected,
        )

    def test_allows_complete_sentences_on_separate_lines(self):
        source = "The first sentence is complete.\nThe second sentence is complete.\n"

        self.assertEqual([], SOFT_WRAP.analyze_text(source, "prose"))

    def test_finds_a_wrapped_list_item(self):
        source = "- Keep this entire sentence on\n  one physical line.\n"

        violations = SOFT_WRAP.analyze_text(source, "prose")
        corrected, count = SOFT_WRAP.apply_safe_fixes(source, "prose")

        self.assertEqual([2], [item.line_index + 1 for item in violations])
        self.assertEqual(1, count)
        self.assertEqual("- Keep this entire sentence on one physical line.\n", corrected)

    def test_fixes_every_line_of_a_multiply_wrapped_list_item(self):
        source = "- Keep this entire\n  sentence on one\n  physical line.\n"

        corrected, count = SOFT_WRAP.apply_safe_fixes(source, "prose")

        self.assertEqual(2, count)
        self.assertEqual("- Keep this entire sentence on one physical line.\n", corrected)

    def test_skips_frontmatter_fences_tables_and_explicit_breaks(self):
        source = """---
description: a folded
  value
---
```
code that
wraps
```
| name | long value |
| --- | --- |
This is an intentional Markdown break.\x20\x20
continued after the break.
"""

        self.assertEqual([], SOFT_WRAP.analyze_text(source, "prose"))

    def test_strict_mode_reports_a_capitalized_continuation_without_fixing_it(self):
        source = "Send this request to the\nOpenAI API before continuing.\n"

        normal = SOFT_WRAP.analyze_text(source, "prose")
        strict = SOFT_WRAP.analyze_text(source, "prose", strict=True)
        corrected, count = SOFT_WRAP.apply_safe_fixes(source, "prose")

        self.assertEqual([], normal)
        self.assertEqual(1, len(strict))
        self.assertFalse(strict[0].certain)
        self.assertEqual(0, count)
        self.assertEqual(source, corrected)

    def test_skips_indented_literal_blocks(self):
        source = "    code that looks like\n    wrapped prose to a heuristic\n"

        corrected, count = SOFT_WRAP.apply_safe_fixes(source, "prose")

        self.assertEqual(0, count)
        self.assertEqual(source, corrected)


class CommentTest(unittest.TestCase):
    def test_finds_and_fixes_a_wrapped_source_comment(self):
        source = "# Cache an explicit zero when a report has\n# no qualifying events.\nvalue = 0\n"

        violations = SOFT_WRAP.analyze_text(source, "comments")
        corrected, count = SOFT_WRAP.apply_safe_fixes(source, "comments")

        self.assertEqual([2], [item.line_index + 1 for item in violations])
        self.assertEqual(1, count)
        self.assertEqual(
            "# Cache an explicit zero when a report has no qualifying events.\nvalue = 0\n",
            corrected,
        )

    def test_treats_an_abbreviation_as_mid_sentence(self):
        source = "// Retry transient failures, e.g.\n// network timeouts.\n"

        self.assertEqual(1, len(SOFT_WRAP.analyze_text(source, "comments")))

    def test_skips_commented_code_and_aligned_layout(self):
        source = """# GET /resource/new
# def new
#   super
# end
# key   description that keeps
#       its layout
"""

        self.assertEqual([], SOFT_WRAP.analyze_text(source, "comments"))

    def test_checks_block_comments(self):
        source = "/**\n * Keep the prose sentence on\n * one physical line.\n */\n"

        corrected, count = SOFT_WRAP.apply_safe_fixes(source, "comments")

        self.assertEqual(1, count)
        self.assertEqual(
            "/**\n * Keep the prose sentence on one physical line.\n */\n",
            corrected,
        )

    def test_language_comment_families_do_not_rewrite_c_preprocessor_directives(self):
        source = "#include <alpha.h>\n#include <beta.h>\n"
        families = SOFT_WRAP.comment_families_for(Path("main.c"))

        corrected, count = SOFT_WRAP.apply_safe_fixes(source, "comments", families)

        self.assertEqual(0, count)
        self.assertEqual(source, corrected)

    def test_language_comment_families_do_not_rewrite_css_custom_properties(self):
        source = "  --foreground: black;\n  --background: white;\n"
        families = SOFT_WRAP.comment_families_for(Path("theme.css"))

        corrected, count = SOFT_WRAP.apply_safe_fixes(source, "comments", families)

        self.assertEqual(0, count)
        self.assertEqual(source, corrected)

    def test_block_comment_markers_are_ignored_outside_a_block(self):
        source = "*destination\n*source\n"
        families = SOFT_WRAP.comment_families_for(Path("pointers.c"))

        corrected, count = SOFT_WRAP.apply_safe_fixes(source, "comments", families)

        self.assertEqual(0, count)
        self.assertEqual(source, corrected)


class FileCollectionTest(unittest.TestCase):
    def test_directory_scan_ignores_dependencies(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "README.md").write_text("A wrapped\nsentence.\n", encoding="utf-8")
            dependency = root / "node_modules"
            dependency.mkdir()
            (dependency / "README.md").write_text(
                "Another wrapped\nsentence.\n", encoding="utf-8"
            )

            files, errors = SOFT_WRAP.collect_files([str(root)], "auto", [])

            self.assertEqual([], errors)
            self.assertEqual([root / "README.md"], [path for path, _mode in files])


if __name__ == "__main__":
    unittest.main()
