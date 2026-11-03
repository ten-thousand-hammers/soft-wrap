# Soft Wrap

Soft Wrap is a Codex skill that keeps each prose sentence on one physical line and leaves visual wrapping to the editor.
It applies the rule to documentation, code comments, list items, review text, and user-facing responses in any project.

The repository uses the standard skill layout:

```text
skills/
└── soft-wrap/
    ├── SKILL.md
    ├── agents/openai.yaml
    └── scripts/soft_wrap.py
```

Install the skill by copying or symlinking `skills/soft-wrap` into your Codex skills directory, usually `~/.codex/skills/soft-wrap`.

Run the checker directly with Python 3 and no third-party dependencies:

```sh
python3 skills/soft-wrap/scripts/soft_wrap.py README.md src/
python3 skills/soft-wrap/scripts/soft_wrap.py --fix README.md src/
```

The checker scans prose files and full-line comments in common source formats, skips generated or structural layouts conservatively, and exits nonzero when a finding remains.
Use `--strict` to surface lower-confidence continuations for manual review, `--fix --strict` to join them once the false positives carry an ignore comment, and `--mode prose` or `--mode comments` for an uncommon file extension.
List files a tool writes without a generated header, such as a git-cliff `CHANGELOG.md`, in a `.soft-wrap-ignore` file at the project root.
Vendored directories, license texts and generated files are skipped by default; `--no-default-excludes` checks generated files, and vendored files or license texts you name on the command line, while directory scans still skip dependency and build directories. A `soft-wrap: ignore-next-line` comment keeps the line below it apart.
