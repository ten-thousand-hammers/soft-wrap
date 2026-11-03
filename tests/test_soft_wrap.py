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

    def test_ignore_directive_keeps_the_next_line_apart(self):
        source = "<!-- soft-wrap: ignore-next-line -->\nthis line stays\nby itself\n"

        corrected, count = SOFT_WRAP.apply_safe_fixes(source, "prose")

        self.assertEqual(0, count)
        self.assertEqual(source, corrected)

    def test_strict_mode_allows_a_new_sentence_after_a_url(self):
        source = "Read more at https://example.com/guide\nThe guide covers setup.\n"

        self.assertEqual([], SOFT_WRAP.analyze_text(source, "prose", strict=True))


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

    def test_does_not_join_commented_out_commands(self):
        source = """# docker run --rm app bin/rails db:prepare
# docker run -d app
#   bin/rails admin:grant EMAIL
#   bin/rails admin:revoke EMAIL
"""

        corrected, count = SOFT_WRAP.apply_safe_fixes(source, "comments")

        self.assertEqual(0, count)
        self.assertEqual(source, corrected)

    def test_does_not_join_commented_out_yaml_config(self):
        source = """# Use bin/rails credentials:edit to set the AWS secrets (as aws:access_key_id)
# amazon:
#   service: S3
#   access_key_id: <%= Rails.application.credentials.dig(:aws, :access_key_id) %>
#   region: us-east-1
"""
        families = SOFT_WRAP.comment_families_for(Path("storage.yml"))

        corrected, count = SOFT_WRAP.apply_safe_fixes(
            source, "comments", families, config_keys=True
        )

        self.assertEqual(0, count)
        self.assertEqual(source, corrected)

    def test_does_not_join_a_comment_containing_erb(self):
        source = "# Cap age of oldest cache entry to fulfill retention policies\n# max_age: <%= 60.days.to_i %>\n"

        corrected, count = SOFT_WRAP.apply_safe_fixes(source, "comments")

        self.assertEqual(0, count)
        self.assertEqual(source, corrected)

    def test_does_not_join_a_commented_out_method_call_with_a_literal(self):
        source = '# Configure Using Gemfile\n# gem "pg"\n'

        corrected, count = SOFT_WRAP.apply_safe_fixes(source, "comments")

        self.assertEqual(0, count)
        self.assertEqual(source, corrected)

    def test_strict_mode_allows_a_new_sentence_after_a_command_or_url(self):
        source = """# Run explicitly: bin/rails runner script/backfill.rb
# Only synthetic cases are written.
# Check spelling with https://github.com/crate-ci/typos
# If the spelling is incorrect, fix it.
"""

        self.assertEqual([], SOFT_WRAP.analyze_text(source, "comments", strict=True))

    def test_joins_list_item_continuations_onto_the_item(self):
        source = (
            "# 3. An existing account is matched by the verified email, so the\n"
            "#    authority for that address decides\n"
            "#    who signs in.\n"
            "# 4. Nothing else changes.\n"
        )

        corrected, count = SOFT_WRAP.apply_safe_fixes(source, "comments")

        self.assertEqual(2, count)
        self.assertEqual(
            "# 3. An existing account is matched by the verified email, so the authority for that address decides who signs in.\n"
            "# 4. Nothing else changes.\n",
            corrected,
        )

    def test_joins_a_lowercase_continuation_after_a_colon(self):
        source = "# The limit protects the one person who reached it:\n# who keeps running into limits.\n"

        corrected, count = SOFT_WRAP.apply_safe_fixes(source, "comments")

        self.assertEqual(1, count)
        self.assertEqual(
            "# The limit protects the one person who reached it: who keeps running into limits.\n",
            corrected,
        )

    def test_joins_a_longer_continuation_after_a_colon(self):
        source = "# The limit protects the one person:\n# who keeps running\n# into limits.\n"

        corrected, count = SOFT_WRAP.apply_safe_fixes(source, "comments")

        self.assertEqual(2, count)
        self.assertEqual("# The limit protects the one person: who keeps running into limits.\n", corrected)

    def test_does_not_join_a_command_example_after_a_colon(self):
        source = "# Run this:\n# echo hello\n# 1. Or this:\n#    echo goodbye\n"

        corrected, count = SOFT_WRAP.apply_safe_fixes(source, "comments")

        self.assertEqual(0, count)
        self.assertEqual(source, corrected)

    def test_strict_mode_allows_a_capitalized_line_after_a_colon(self):
        source = "# Two steps follow:\n# Install the gems first.\n"

        self.assertEqual([], SOFT_WRAP.analyze_text(source, "comments", strict=True))

    def test_ignore_directive_keeps_the_next_line_apart(self):
        source = "# The hosts are\n# soft-wrap: ignore-next-line\n# alpha beta gamma\n# delta epsilon\n"

        corrected, count = SOFT_WRAP.apply_safe_fixes(source, "comments")

        self.assertEqual(0, count)
        self.assertEqual(source, corrected)

    def test_skips_preserved_license_blocks(self):
        source = "/*! @preserve\n * Library v1.0 is distributed under\n * the MIT license\n */\n"
        families = SOFT_WRAP.comment_families_for(Path("library.js"))

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

    def test_scans_extensionless_scripts_by_their_shebang(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "setup").write_text(
                "#!/usr/bin/env ruby\n# Prepare the app by installing gems and\n# loading the schema.\n",
                encoding="utf-8",
            )
            (root / "serve").write_text(
                "#!/usr/bin/env -S node --no-warnings\n// Start the server on\n// the configured port.\n",
                encoding="utf-8",
            )
            (root / "data").write_text("plain data\nwithout a shebang\n", encoding="utf-8")

            files, errors = SOFT_WRAP.collect_files([str(root)], "auto", [])

            self.assertEqual([], errors)
            self.assertEqual(
                [(root / "serve", "comments"), (root / "setup", "comments")], files
            )
            self.assertEqual(
                frozenset({"//", "/*"}), SOFT_WRAP.comment_families_for(root / "serve")
            )
            self.assertEqual(
                frozenset({"#"}), SOFT_WRAP.comment_families_for(root / "setup")
            )

    def test_exclude_applies_to_explicit_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            changelog = root / "CHANGELOG.md"
            changelog.write_text("A wrapped\nsentence.\n", encoding="utf-8")
            schema = root / "db" / "schema.rb"
            schema.parent.mkdir()
            schema.write_text("# A wrapped\n# sentence.\n", encoding="utf-8")

            files, errors = SOFT_WRAP.collect_files(
                [str(changelog), str(schema)], "auto", ["CHANGELOG.md", "*db/*schema.rb"]
            )

            self.assertEqual([], errors)
            self.assertEqual([], files)

    def test_explicit_files_skip_vendored_and_license_texts_by_default(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / ".git").mkdir()
            vendored = root / "vendor" / "lib" / "notes.md"
            vendored.parent.mkdir(parents=True)
            license_text = root / "fonts" / "Inter-OFL.txt"
            license_text.parent.mkdir()
            names = [vendored, license_text, root / "LICENSE", root / "LICENSE.md"]
            for path in names:
                path.write_text("A wrapped\nsentence.\n", encoding="utf-8")

            files, errors = SOFT_WRAP.collect_files([str(path) for path in names], "auto", [])
            included, _errors = SOFT_WRAP.collect_files(
                [str(path) for path in names], "auto", [], default_excludes=False
            )

            self.assertEqual([], errors)
            self.assertEqual([], files)
            self.assertEqual(len(names), len(included))

    def test_ignored_directory_names_above_the_project_do_not_exclude_it(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory) / "tmp" / "build" / "project"
            project.mkdir(parents=True)
            (project / ".git").mkdir()
            readme = project / "README.md"
            readme.write_text("A wrapped\nsentence.\n", encoding="utf-8")

            explicit, explicit_errors = SOFT_WRAP.collect_files([str(readme)], "auto", [])
            scanned, scan_errors = SOFT_WRAP.collect_files([str(project)], "auto", [])

            self.assertEqual([], explicit_errors + scan_errors)
            self.assertEqual([(readme, "prose")], explicit)
            self.assertEqual([(readme, "prose")], scanned)

    def test_check_file_leaves_generated_files_alone(self):
        headers = [
            "# This file is auto-generated from the current state of the database. Instead\n"
            "# of editing this file, please use the migrations feature of Active Record to\n"
            "# incrementally modify your database.\n",
            "#!/usr/bin/env ruby\n# frozen_string_literal: true\n\n#\n"
            "# This file was generated by Bundler.\n#\n# The application 'rake' is installed as part of\n"
            "# a gem, and this file is here to facilitate running it.\n#\n",
            "# @Generated by the schema compiler from\n# the shared definitions.\n",
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            for number, header in enumerate(headers):
                path = Path(temporary_directory) / f"generated{number}.rb"
                path.write_text(header, encoding="utf-8")

                findings, fixed, error = SOFT_WRAP.check_file(path, "comments", True, False)

                self.assertEqual((0, 0, None), (findings, fixed, error))
                self.assertEqual(header, path.read_text(encoding="utf-8"))


    def test_check_file_still_checks_a_file_that_only_warns_against_editing(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "README.md"
            path.write_text(
                "Do not edit the examples below by hand.\n\nA sentence split across\ntwo lines.\n",
                encoding="utf-8",
            )

            findings, fixed, error = SOFT_WRAP.check_file(path, "prose", False, False)

            self.assertEqual((1, 0, None), (findings, fixed, error))

if __name__ == "__main__":
    unittest.main()
