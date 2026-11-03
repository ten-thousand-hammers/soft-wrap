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
Use `--strict` to surface lower-confidence continuations for manual review and `--mode prose` or `--mode comments` for an uncommon file extension.
Vendored directories, license texts and generated files are skipped unless you pass `--no-default-excludes`, and a `soft-wrap: ignore-next-line` comment keeps the line below it apart.
