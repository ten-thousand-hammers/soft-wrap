---
name: soft-wrap
description: Prevent hard line breaks inside prose sentences and keep each sentence on one physical line so editors can soft-wrap it. Use whenever Codex writes, rewrites, formats, reviews, or fixes prose in any project, including Markdown, plain text, documentation, code comments, changelogs, commit or pull-request text, and user-facing responses, or when the user requests soft wrapping, one sentence per line, or removal of mid-sentence newlines.
---

# Soft Wrap

Keep every prose sentence on one physical line, regardless of its length, and let the editor or renderer wrap it visually.

## Apply the rule

1. Inspect applicable project instructions before editing.
2. Write each complete prose sentence on one physical line.
3. Use a newline only after terminal punctuation, between paragraphs, or where the file format gives the newline structural meaning.
4. Apply the rule inside headings, list items, blockquotes, documentation, and full-line code comments as well as ordinary paragraphs.
5. Preserve line breaks in code, tables, diagrams, generated content, literal blocks, and other structures where a newline changes meaning.
6. Do not wrap prose to a target column width.

For user-facing responses, inspect every newline before sending the response and join any sentence that crosses it.

## Check edited files

Run the bundled dependency-free checker on every prose or source file that was created or edited:

```sh
python3 <skill-dir>/scripts/soft_wrap.py path/to/file another/path
```

Use `--fix` to join high-confidence continuations, then inspect the diff and run the checker again:

```sh
python3 <skill-dir>/scripts/soft_wrap.py --fix path/to/file another/path
python3 <skill-dir>/scripts/soft_wrap.py path/to/file another/path
```

Use `--strict` for a final review when a continuation can begin with a proper noun, number, acronym, or inline code; resolve true positives manually because strict findings are intentionally not auto-fixed.

```sh
python3 <skill-dir>/scripts/soft_wrap.py --strict path/to/file another/path
```

Pass a directory to scan supported documentation and source files recursively; extensionless scripts are checked when their shebang names a known interpreter.
Use `--mode prose` or `--mode comments` for an unsupported extension.
`--exclude GLOB` skips matching files, including files named on the command line.
Vendored directories, license texts and files whose header says they are generated are skipped by default; pass `--no-default-excludes` to check them anyway.
For a rare line that must stay on its own, put a `soft-wrap: ignore-next-line` comment on the line above it.
Exit status `1` means findings remain, and exit status `2` means a file could not be checked.

The checker is a conservative backstop, not permission to skip the visual review.
