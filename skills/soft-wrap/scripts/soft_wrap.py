#!/usr/bin/env python3
"""Find and fix physical newlines that split prose sentences."""

from __future__ import annotations

import argparse
import fnmatch
import functools
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence


MESSAGE = "Keep each prose sentence on one physical line; let the editor soft-wrap it."

PROSE_SUFFIXES = {
    ".adoc",
    ".asciidoc",
    ".markdown",
    ".md",
    ".mdx",
    ".rst",
    ".text",
    ".txt",
}

SOURCE_SUFFIXES = {
    ".bash",
    ".c",
    ".cc",
    ".cfg",
    ".cjs",
    ".clj",
    ".cljc",
    ".cljs",
    ".conf",
    ".cpp",
    ".cs",
    ".css",
    ".dart",
    ".edn",
    ".env",
    ".erl",
    ".ex",
    ".exs",
    ".fish",
    ".fs",
    ".fsx",
    ".go",
    ".h",
    ".hcl",
    ".hpp",
    ".hrl",
    ".hs",
    ".ini",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".kts",
    ".less",
    ".lhs",
    ".lua",
    ".m",
    ".mjs",
    ".mm",
    ".php",
    ".pl",
    ".pm",
    ".ps1",
    ".py",
    ".pyi",
    ".r",
    ".rake",
    ".rb",
    ".rs",
    ".sass",
    ".scala",
    ".scss",
    ".sh",
    ".sql",
    ".swift",
    ".tf",
    ".toml",
    ".ts",
    ".tsx",
    ".vb",
    ".yml",
    ".yaml",
    ".zsh",
}

HASH_COMMENT_SUFFIXES = {
    ".bash", ".cfg", ".conf", ".env", ".ex", ".exs", ".fish", ".hcl",
    ".ini", ".nim", ".php", ".pl", ".pm", ".ps1", ".py", ".pyi",
    ".r", ".rake", ".rb", ".sh", ".tf", ".toml", ".yaml", ".yml",
    ".zsh",
}
SLASH_LINE_COMMENT_SUFFIXES = {
    ".c", ".cc", ".cjs", ".cpp", ".cs", ".dart", ".fs", ".fsx", ".go",
    ".groovy", ".h", ".hpp", ".java", ".js", ".jsx", ".kt", ".kts",
    ".less", ".m", ".mjs", ".mm", ".php", ".rs", ".sass", ".scala",
    ".scss", ".sol", ".swift", ".ts", ".tsx", ".zig",
}
SLASH_BLOCK_COMMENT_SUFFIXES = SLASH_LINE_COMMENT_SUFFIXES | {".css"}
DASH_COMMENT_SUFFIXES = {".hs", ".lhs", ".lua", ".sql"}
SEMICOLON_COMMENT_SUFFIXES = {".cfg", ".clj", ".cljc", ".cljs", ".edn", ".el", ".ini", ".lisp", ".scm"}
PERCENT_COMMENT_SUFFIXES = {".erl", ".hrl", ".m"}
BANG_COMMENT_SUFFIXES = {".f", ".f03", ".f08", ".f90", ".f95"}
APOSTROPHE_COMMENT_SUFFIXES = {".vb"}
SOURCE_SUFFIXES |= (
    HASH_COMMENT_SUFFIXES
    | SLASH_BLOCK_COMMENT_SUFFIXES
    | DASH_COMMENT_SUFFIXES
    | SEMICOLON_COMMENT_SUFFIXES
    | PERCENT_COMMENT_SUFFIXES
    | BANG_COMMENT_SUFFIXES
    | APOSTROPHE_COMMENT_SUFFIXES
)

PROSE_NAMES = {
    "authors",
    "changelog",
    "changes",
    "contributors",
    "copying",
    "license",
    "news",
    "notice",
    "readme",
}

SOURCE_NAMES = {
    "dockerfile",
    "gemfile",
    "justfile",
    "makefile",
    "procfile",
    "rakefile",
    "vagrantfile",
}

YAML_SUFFIXES = {".yaml", ".yml"}

HASH_INTERPRETERS = {
    "bash",
    "dash",
    "fish",
    "ksh",
    "perl",
    "python",
    "rake",
    "ruby",
    "sh",
    "zsh",
}
SLASH_INTERPRETERS = {"bun", "deno", "node", "tsx"}

DEFAULT_EXCLUDED_NAMES = (
    "copying",
    "copying.*",
    "licence",
    "licence.*",
    "license",
    "license.*",
    "ofl.txt",
    "*-ofl.txt",
)

IGNORE_FILE = ".soft-wrap-ignore"

IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tox",
    ".venv",
    "build",
    "coverage",
    "dist",
    "log",
    "node_modules",
    "pods",
    "target",
    "tmp",
    "vendor",
    "venv",
}

SENTENCE_END = re.compile(r"[.!?:](?:[)\]}'\"`*_~])*$")
CODE_SPAN = re.compile(r"`[^`\n]*`")
COLON_END = re.compile(r":(?:[)\]}'\"`*_~])*$")
FULL_STOP_END = re.compile(r"[.!?](?:[)\]}'\"`*_~])*$")
ABBREVIATION_END = re.compile(
    r"\b(?:approx|cf|Dr|e\.g|etc|i\.e|Mr|Mrs|Ms|No|resp|vs)\.$"
)
SAFE_CONTINUATION = re.compile(r"^[([{'\"`*_~]*[a-z]")
STRICT_CONTINUATION = re.compile(r"^[([{'\"`*_~]*[A-Za-z0-9]")
HYPHEN_SPLIT = re.compile(r"-$")
TABULAR = re.compile(r"\S[ \t]{2,}\S")
DEFINITION_ITEM = re.compile(r"^\S+\s+->\s")
GENERATED_BLOCK = re.compile(
    r"^(?:== Schema Information|Foreign Keys|Indexes|Table name:)"
)
SKIP_LINE = re.compile(
    r"^(?:#!|!/|-\*-|=begin|=end|encoding:|frozen_string_literal|HACK|NOTE|OPTIMIZE|REVIEW|rubocop:|standard:|TODO|FIXME)"
)
COMMENT_MARKUP = re.compile(r"^(?:[-*+]\s|\d+[.)]\s|[|>]|```|~~~)")
CODE_LIKE = re.compile(r"[{}]|=>")
TEMPLATE_TAG = re.compile(r"<%|\{\{")
COMMAND_START = r"(?:\$\s+|\.{1,2}/|~/|(?:bin|exe|sbin|script)/)"
COMMAND_LIKE = re.compile(
    rf"^(?:{COMMAND_START}|[\w.-]+(?:\s+[\w.:-]+)?\s+--?[A-Za-z])"
)
LITERAL_ARGUMENT = r"(?:\"[^\"]*\"|'[^']*'|:\w+|\w+:\s*\S+)"
CALL_WITH_LITERAL = re.compile(
    rf"^[a-z_]\w*[!?]?\s+{LITERAL_ARGUMENT}(?:\s*,\s*{LITERAL_ARGUMENT})*$"
)
CONFIG_KEY = re.compile(r"^[a-z_][\w.-]*:(?:\s|$)")
COMMENT_LIST_ITEM = re.compile(r"^(?:[-*+]|\d+[.)])[ \t]+")
LICENSE_BLOCK = re.compile(r"@(?:license|preserve)\b")
COMMAND_OR_URL_END = re.compile(rf"(?:\w+://\S*[\w/]|:\s+{COMMAND_START}.*)$")
IGNORE_NEXT_LINE = re.compile(r"\bsoft-wrap:\s*ignore-next-line\b")
# DO NOT EDIT is matched in capitals only, the way generators write it, so a hand-written "Do not edit the examples" stays checked.
GENERATED_HEADER = re.compile(
    r"(?i:@generated)\b|\bDO NOT EDIT\b|\b(?i:this file (?:is|was|has been) (?:auto-?)?generated)\b"
)
GENERATED_HEADER_LINES = 10
CODE_STATEMENT = re.compile(
    r"^(?:(?:begin|else|end|ensure|private|protected|public|rescue)\b|"
    r"(?:attr_accessor|attr_reader|attr_writer|class|def|extend|include|module|require|require_relative)\s|"
    r".*\bdo(?:\s*\|[^|]*\|)?$|"
    r"[@$]?[A-Za-z_]\w*(?:::[A-Z]\w*)*(?:\.[a-z_]\w*[!?]?)+[\s(]|"
    r"[@$]?[a-z_]\w*(?:\[[^]]*])?\s*(?:\|\||&&|[+*/-])?=[^=~>]|"
    r"%[wi](?:\(|\[))"
)
COMMENT_LINE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<marker>//+|/\*+|\*+|#+|--+|;+|%+|!+|')(?P<gap>[ \t]*)(?P<text>.*)$"
)
FENCE = re.compile(r"^[ \t]*(?:>[ \t]*)*(?:```|~~~)")
MARKDOWN_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}(?:[ \t]|$)")
MARKDOWN_LIST = re.compile(
    r"(?P<marker>(?:[-+*]|\d+[.)])[ \t]+(?:\[[ xX]\][ \t]+)?)(?P<text>.*)$"
)
MARKDOWN_RULE = re.compile(r"^[ \t]{0,3}(?:[-*_][ \t]*){3,}$")
RST_ADORNMENT = re.compile(r"^[=~^`:#*+_-]{3,}[ \t]*$")
LINK_DEFINITION = re.compile(r"^[ \t]*\[[^]]+]:")
HTML_LINE = re.compile(r"^[ \t]*</?[A-Za-z][^>]*>")
URL_LINE = re.compile(r"^(?:https?://|mailto:|www\.)\S+$")
QUOTE_PREFIX = re.compile(r"^(?P<indent>[ \t]*)(?P<quotes>(?:>[ \t]?)*)(?P<text>.*)$")


@dataclass(frozen=True)
class PhysicalLine:
    body: str
    ending: str


@dataclass(frozen=True)
class Violation:
    previous_index: int
    line_index: int
    content_start: int
    certain: bool


@dataclass(frozen=True)
class CommentLine:
    index: int
    indent: str
    marker: str
    gap: str
    text: str
    content_start: int


@dataclass(frozen=True)
class ProseLine:
    index: int
    indent_width: int
    quote_depth: int
    kind: str
    marker_width: int
    text: str
    content_start: int
    skip: bool
    explicit_break: bool


def split_physical_lines(text: str) -> list[PhysicalLine]:
    lines: list[PhysicalLine] = []
    for raw in text.splitlines(keepends=True):
        if raw.endswith("\r\n"):
            lines.append(PhysicalLine(raw[:-2], "\r\n"))
        elif raw.endswith(("\n", "\r")):
            lines.append(PhysicalLine(raw[:-1], raw[-1]))
        else:
            lines.append(PhysicalLine(raw, ""))
    if not lines and text == "":
        return []
    return lines


def marker_family(marker: str) -> str:
    if marker.startswith("//"):
        return "//"
    if marker.startswith("/*") or marker.startswith("*"):
        return "/*"
    return marker[0]


def parse_comment(
    index: int, body: str, families: frozenset[str] | None = None
) -> CommentLine | None:
    match = COMMENT_LINE.match(body)
    if not match:
        return None
    if families is not None and marker_family(match.group("marker")) not in families:
        return None
    return CommentLine(
        index=index,
        indent=match.group("indent"),
        marker=match.group("marker"),
        gap=match.group("gap"),
        text=match.group("text").rstrip(),
        content_start=match.start("text"),
    )


def adjacent_comments(previous: CommentLine, current: CommentLine) -> bool:
    if current.index != previous.index + 1:
        return False
    if marker_family(previous.marker) != marker_family(current.marker):
        return False
    if marker_family(previous.marker) == "/*":
        return abs(len(previous.indent) - len(current.indent)) <= 1
    return previous.indent == current.indent


def comment_blocks(
    lines: Sequence[PhysicalLine], families: frozenset[str] | None = None
) -> list[list[CommentLine]]:
    blocks: list[list[CommentLine]] = []
    current: list[CommentLine] = []
    in_slash_block = False
    for index, line in enumerate(lines):
        parsed = parse_comment(index, line.body, families)
        if parsed and parsed.marker.startswith("*") and not in_slash_block:
            parsed = None
        if parsed and parsed.marker.startswith("/*"):
            in_slash_block = True
        if parsed and (not current or adjacent_comments(current[-1], parsed)):
            current.append(parsed)
        else:
            if len(current) > 1:
                blocks.append(current)
            current = [parsed] if parsed else []
        if in_slash_block and "*/" in line.body:
            in_slash_block = False
    if len(current) > 1:
        blocks.append(current)
    return blocks


def ends_sentence(text: str) -> bool:
    return bool(SENTENCE_END.search(text)) and not bool(ABBREVIATION_END.search(text))


def without_code_spans(text: str) -> str:
    """Replace each code span with a placeholder, so `over?` doesn't end a sentence but `reset!`. still does."""
    return CODE_SPAN.sub("`code`", text)


def continuation_certainty(text: str, strict: bool) -> bool | None:
    if SAFE_CONTINUATION.search(text):
        return True
    if strict and STRICT_CONTINUATION.search(text):
        return False
    return None


def break_certainty(previous: str, current: str, strict: bool) -> bool | None:
    """Return whether the break between two lines splits a sentence, or None if it does not."""
    if HYPHEN_SPLIT.search(previous):
        return None
    certainty = continuation_certainty(current, strict)
    ending = without_code_spans(previous)
    if COLON_END.search(ending):
        # After a colon, join only a line that finishes the sentence, so an example such as "echo hello" stays on its own line; --fix repeats, so a longer continuation joins up from its last line.
        if not (certainty and FULL_STOP_END.search(without_code_spans(current))):
            return None
    elif ends_sentence(ending):
        return None
    if certainty is False and COMMAND_OR_URL_END.search(previous):
        return None
    return certainty


def skip_comment_text(text: str, config_keys: bool = False) -> bool:
    return bool(
        SKIP_LINE.search(text)
        or COMMENT_MARKUP.search(text)
        or TABULAR.search(text)
        or CODE_LIKE.search(text)
        or TEMPLATE_TAG.search(text)
        or COMMAND_LIKE.search(text)
        or CALL_WITH_LITERAL.search(text)
        or (config_keys and CONFIG_KEY.search(text))
    )


def list_item_continues(previous: CommentLine, current: CommentLine) -> bool:
    """Whether current is indented to the text of the list item on the previous line."""
    item = COMMENT_LIST_ITEM.match(previous.text)
    if not item:
        return False
    item_text = previous.text[item.end() :]
    if skip_comment_text(item_text):
        return False
    text_column = len(previous.gap.expandtabs(4)) + len(item.group().expandtabs(4))
    return len(current.gap.expandtabs(4)) == text_column


def license_block(block: Sequence[CommentLine]) -> bool:
    if marker_family(block[0].marker) == "/*" and block[0].text.startswith("!"):
        return True
    return any(LICENSE_BLOCK.search(line.text) for line in block)


def find_comment_violations(
    lines: Sequence[PhysicalLine],
    strict: bool = False,
    families: frozenset[str] | None = None,
    config_keys: bool = False,
) -> list[Violation]:
    violations: list[Violation] = []
    for block in comment_blocks(lines, families):
        texts = [line.text for line in block]
        if license_block(block):
            continue
        if any(GENERATED_BLOCK.search(text) for text in texts):
            continue
        if any(CODE_STATEMENT.search(text) for text in texts):
            continue
        if any(TABULAR.search(text) or DEFINITION_ITEM.search(text) for text in texts):
            continue
        for previous, current in zip(block, block[1:]):
            if not previous.text or not current.text:
                continue
            if skip_comment_text(current.text, config_keys):
                continue
            if not list_item_continues(previous, current):
                if skip_comment_text(previous.text, config_keys) or previous.gap != current.gap:
                    continue
            certainty = break_certainty(previous.text, current.text, strict)
            if certainty is None:
                continue
            violations.append(
                Violation(
                    previous_index=previous.index,
                    line_index=current.index,
                    content_start=current.content_start,
                    certain=certainty,
                )
            )
    return violations


def prose_skip_mask(lines: Sequence[PhysicalLine]) -> list[bool]:
    skipped = [False] * len(lines)
    in_frontmatter = bool(lines and lines[0].body.strip() == "---")
    in_fence = False
    for index, line in enumerate(lines):
        stripped = line.body.strip()
        if in_frontmatter:
            skipped[index] = True
            if index > 0 and stripped in {"---", "..."}:
                in_frontmatter = False
            continue
        if FENCE.search(line.body):
            skipped[index] = True
            in_fence = not in_fence
            continue
        if in_fence:
            skipped[index] = True
    return skipped


def parse_prose_line(
    index: int, line: PhysicalLine, masked: bool
) -> ProseLine:
    quote_match = QUOTE_PREFIX.match(line.body)
    assert quote_match is not None
    indent = quote_match.group("indent")
    quotes = quote_match.group("quotes")
    remainder = quote_match.group("text")
    base_start = quote_match.start("text")
    leading = remainder[: len(remainder) - len(remainder.lstrip())]
    logical = remainder[len(leading) :]
    list_match = MARKDOWN_LIST.match(logical)
    kind = "plain"
    marker_width = 0
    text = logical.strip()
    content_start = base_start + len(leading)
    if list_match:
        kind = "list"
        marker_width = len(list_match.group("marker"))
        text = list_match.group("text").strip()
        content_start = base_start + len(leading) + list_match.start("text")
    stripped = line.body.strip()
    structural = bool(
        masked
        or not stripped
        or MARKDOWN_HEADING.search(logical)
        or MARKDOWN_RULE.search(logical)
        or RST_ADORNMENT.search(stripped)
        or LINK_DEFINITION.search(logical)
        or HTML_LINE.search(logical)
        or stripped.startswith((".. ", "::", "|"))
        or URL_LINE.search(text)
        or TABULAR.search(text)
        or DEFINITION_ITEM.search(text)
        or SKIP_LINE.search(text)
    )
    return ProseLine(
        index=index,
        indent_width=len((indent + leading).expandtabs(4)),
        quote_depth=quotes.count(">"),
        kind=kind,
        marker_width=marker_width,
        text=text.rstrip(),
        content_start=content_start,
        skip=structural,
        explicit_break=line.body.endswith(("  ", "\\")),
    )


def prose_lines_compatible(previous: ProseLine, current: ProseLine) -> bool:
    if previous.quote_depth != current.quote_depth:
        return False
    if previous.kind == "plain" and current.kind == "plain":
        return previous.indent_width == current.indent_width
    if previous.kind == "list" and current.kind == "plain":
        minimum = previous.indent_width + 2
        maximum = previous.indent_width + max(previous.marker_width, 2)
        return minimum <= current.indent_width <= maximum
    return False


def find_prose_violations(
    lines: Sequence[PhysicalLine], strict: bool = False
) -> list[Violation]:
    masked = prose_skip_mask(lines)
    parsed = [
        parse_prose_line(index, line, masked[index])
        for index, line in enumerate(lines)
    ]
    violations: list[Violation] = []
    for previous, current in zip(parsed, parsed[1:]):
        if previous.skip or current.skip or previous.explicit_break:
            continue
        if not previous.text or not current.text:
            continue
        if not prose_lines_compatible(previous, current):
            continue
        if (
            previous.kind == "plain"
            and current.kind == "plain"
            and previous.indent_width >= 4
        ):
            continue
        if CODE_LIKE.search(previous.text) or CODE_LIKE.search(current.text):
            continue
        certainty = break_certainty(previous.text, current.text, strict)
        if certainty is None:
            continue
        violations.append(
            Violation(
                previous_index=previous.index,
                line_index=current.index,
                content_start=current.content_start,
                certain=certainty,
            )
        )
    return violations


def find_violations(
    lines: Sequence[PhysicalLine],
    mode: str,
    strict: bool = False,
    comment_families: frozenset[str] | None = None,
    config_keys: bool = False,
) -> list[Violation]:
    if mode == "prose":
        violations = find_prose_violations(lines, strict)
    elif mode == "comments":
        violations = find_comment_violations(lines, strict, comment_families, config_keys)
    else:
        raise ValueError(f"unknown mode: {mode}")
    protected: set[int] = set()
    for index, line in enumerate(lines):
        if IGNORE_NEXT_LINE.search(line.body):
            protected.update((index, index + 1))
    return [
        violation
        for violation in violations
        if violation.previous_index not in protected and violation.line_index not in protected
    ]


def analyze_text(
    text: str,
    mode: str,
    strict: bool = False,
    comment_families: frozenset[str] | None = None,
    config_keys: bool = False,
) -> list[Violation]:
    lines = split_physical_lines(text)
    return find_violations(lines, mode, strict, comment_families, config_keys)


def apply_safe_fixes(
    text: str,
    mode: str,
    comment_families: frozenset[str] | None = None,
    config_keys: bool = False,
    strict: bool = False,
) -> tuple[str, int]:
    """Join SW001 breaks, and SW002 breaks too when strict; a soft-wrap: ignore-next-line comment protects a false positive."""
    fixed = 0
    while True:
        lines = split_physical_lines(text)
        violations = find_violations(lines, mode, strict, comment_families, config_keys)
        safe = [violation for violation in violations if strict or violation.certain]
        if not safe:
            return text, fixed
        for violation in reversed(safe):
            previous = lines[violation.previous_index]
            current = lines[violation.line_index]
            continuation = current.body[violation.content_start :].strip()
            joined = f"{previous.body.rstrip()} {continuation}"
            lines[violation.previous_index] = PhysicalLine(joined, current.ending)
            del lines[violation.line_index]
        text = "".join(line.body + line.ending for line in lines)
        fixed += len(safe)


def shebang_interpreter(path: Path) -> str | None:
    try:
        with path.open("rb") as handle:
            first_line = handle.readline(256)
    except OSError:
        return None
    if not first_line.startswith(b"#!"):
        return None
    words = first_line[2:].decode("utf-8", "replace").split()
    if words and Path(words[0]).name == "env":
        words = [word for word in words[1:] if not word.startswith("-")]
    if not words:
        return None
    return re.sub(r"[\d.]+$", "", Path(words[0]).name)


def script_families(path: Path) -> set[str]:
    if path.suffix:
        return set()
    interpreter = shebang_interpreter(path)
    if interpreter in HASH_INTERPRETERS:
        return {"#"}
    if interpreter in SLASH_INTERPRETERS:
        return {"//", "/*"}
    return set()


def comment_families_for(path: Path) -> frozenset[str] | None:
    suffix = path.suffix.lower()
    families: set[str] = set()
    if suffix in HASH_COMMENT_SUFFIXES or path.name.lower() in SOURCE_NAMES:
        families.add("#")
    if suffix in SLASH_LINE_COMMENT_SUFFIXES:
        families.add("//")
    if suffix in SLASH_BLOCK_COMMENT_SUFFIXES:
        families.add("/*")
    if path.name.lower() not in SOURCE_NAMES:
        families |= script_families(path)
    if suffix in DASH_COMMENT_SUFFIXES:
        families.add("-")
    if suffix in SEMICOLON_COMMENT_SUFFIXES:
        families.add(";")
    if suffix in PERCENT_COMMENT_SUFFIXES:
        families.add("%")
    if suffix in BANG_COMMENT_SUFFIXES:
        families.add("!")
    if suffix in APOSTROPHE_COMMENT_SUFFIXES:
        families.add("'")
    return frozenset(families) if families else None


def infer_mode(path: Path) -> str | None:
    suffix = path.suffix.lower()
    name = path.name.lower()
    if suffix in PROSE_SUFFIXES or name in PROSE_NAMES:
        return "prose"
    if suffix in SOURCE_SUFFIXES or name in SOURCE_NAMES:
        return "comments"
    if script_families(path):
        return "comments"
    return None


def relative_path(path: Path) -> Path:
    try:
        return path.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        return path


def excluded(path: Path, patterns: Sequence[str]) -> bool:
    candidates = {path.as_posix(), relative_path(path).as_posix()}
    return any(
        fnmatch.fnmatch(path.name, pattern)
        or any(fnmatch.fnmatch(candidate, pattern) for candidate in candidates)
        for pattern in patterns
    )


def license_name(path: Path) -> bool:
    name = path.name.lower()
    return any(fnmatch.fnmatch(name, pattern) for pattern in DEFAULT_EXCLUDED_NAMES)


def project_root(path: Path) -> Path | None:
    absolute = path.resolve()
    for directory in (absolute, *absolute.parents):
        if (directory / ".git").exists():
            return directory
    return None


def project_directories(path: Path) -> tuple[str, ...]:
    """The directories between the project root and path, so a checkout under /tmp or build/ isn't mistaken for one."""
    relative = relative_path(path)
    if not relative.is_absolute():
        return relative.parts[:-1]
    root = project_root(path)
    if root is None:
        return ()
    return path.resolve().relative_to(root).parts[:-1]


def ignore_file_patterns(root: Path) -> tuple[str, ...]:
    """Globs from the project's .soft-wrap-ignore, one per line; # starts a comment and a trailing / names a directory."""
    ignore_file = root / IGNORE_FILE
    try:
        modified = ignore_file.stat().st_mtime_ns
    except OSError:
        return ()
    return read_ignore_file(ignore_file, modified)


@functools.lru_cache(maxsize=None)
def read_ignore_file(ignore_file: Path, modified: int) -> tuple[str, ...]:
    """Keyed on the modification time too, so an edited ignore file applies to the next scan in the same process."""
    try:
        lines = ignore_file.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return ()
    patterns = (line.strip() for line in lines)
    return tuple(pattern for pattern in patterns if pattern and not pattern.startswith("#"))


def ignored_by_project(path: Path) -> bool:
    """Whether the .soft-wrap-ignore at the project root (the nearest .git, else the working directory) lists path or a directory it is in."""
    root = project_root(path)
    if root is None:
        root = Path.cwd().resolve()
    try:
        parts = path.resolve().relative_to(root).parts
    except ValueError:
        return False
    patterns = ignore_file_patterns(root)
    for depth in range(1, len(parts) + 1):
        relative = "/".join(parts[:depth])
        name = parts[depth - 1]
        directory = depth < len(parts) or path.is_dir()
        for pattern in patterns:
            if pattern.endswith("/"):
                if not directory:
                    continue
                pattern = pattern.rstrip("/")
            if fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(name, pattern):
                return True
    return False


def excluded_by_default(path: Path) -> bool:
    """Vendored code and license texts belong to someone else; their line breaks stay."""
    if license_name(path):
        return True
    return any(part.lower() in IGNORED_DIRECTORIES for part in project_directories(path))


def generated(text: str) -> bool:
    header = text.splitlines()[:GENERATED_HEADER_LINES]
    return any(GENERATED_HEADER.search(line) for line in header)


def walk_directory(
    directory: Path, patterns: Sequence[str], default_excludes: bool = True
) -> Iterator[Path]:
    for root, directories, filenames in os.walk(directory, followlinks=False):
        directories[:] = sorted(
            name
            for name in directories
            if name.lower() not in IGNORED_DIRECTORIES
            and not excluded(Path(root) / name, patterns)
            and not ignored_by_project(Path(root) / name)
        )
        for filename in sorted(filenames):
            path = Path(root) / filename
            if excluded(path, patterns) or (default_excludes and license_name(path)):
                continue
            if ignored_by_project(path):
                continue
            if infer_mode(path) is not None:
                yield path


def collect_files(
    paths: Sequence[str],
    forced_mode: str,
    patterns: Sequence[str],
    default_excludes: bool = True,
) -> tuple[list[tuple[Path, str]], list[str]]:
    files: list[tuple[Path, str]] = []
    errors: list[str] = []
    seen: set[Path] = set()
    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            errors.append(f"{path}: path does not exist")
            continue
        candidates: Iterable[Path]
        if path.is_dir():
            candidates = walk_directory(path, patterns, default_excludes)
        elif excluded(path, patterns) or ignored_by_project(path):
            continue
        elif default_excludes and excluded_by_default(path):
            continue
        else:
            candidates = [path]
        for candidate in candidates:
            key = candidate.resolve()
            if key in seen:
                continue
            mode = forced_mode if forced_mode != "auto" else infer_mode(candidate)
            if mode is None:
                errors.append(
                    f"{candidate}: unsupported file type; pass --mode prose or --mode comments"
                )
                continue
            seen.add(key)
            files.append((candidate, mode))
    return files, errors


def display_path(path: Path) -> str:
    return str(relative_path(path))


def read_utf8(path: Path) -> tuple[str | None, str | None]:
    try:
        data = path.read_bytes()
    except OSError as error:
        return None, str(error)
    if b"\0" in data:
        return None, "binary file"
    try:
        return data.decode("utf-8"), None
    except UnicodeDecodeError:
        return None, "not UTF-8"


def check_file(
    path: Path,
    mode: str,
    fix: bool,
    strict: bool,
    default_excludes: bool = True,
) -> tuple[int, int, str | None]:
    text, error = read_utf8(path)
    if error or text is None:
        return 0, 0, error
    if default_excludes and generated(text):
        return 0, 0, None
    families = comment_families_for(path) if mode == "comments" else None
    config_keys = path.suffix.lower() in YAML_SUFFIXES
    fixed = 0
    if fix:
        updated, fixed = apply_safe_fixes(text, mode, families, config_keys, strict)
        if updated != text:
            try:
                path.write_bytes(updated.encode("utf-8"))
            except OSError as write_error:
                return 0, 0, str(write_error)
            text = updated
    violations = analyze_text(text, mode, strict, families, config_keys)
    shown_path = display_path(path)
    for violation in violations:
        code = "SW001" if violation.certain else "SW002"
        qualifier = MESSAGE if violation.certain else f"Possible hard wrap: {MESSAGE}"
        print(
            f"{shown_path}:{violation.line_index + 1}:{violation.content_start + 1}: {code} {qualifier}"
        )
    return len(violations), fixed, None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Find hard line breaks inside prose sentences."
    )
    parser.add_argument("paths", nargs="*", default=["."], help="files or directories")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="join high-confidence continuations in place; with --strict, join lower-confidence ones too",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="also report lower-confidence capitalized or numeric continuations",
    )
    parser.add_argument(
        "--mode",
        choices=("auto", "prose", "comments"),
        default="auto",
        help="override file-type detection",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="exclude a path or basename glob; repeat as needed (a project can also list globs in .soft-wrap-ignore)",
    )
    parser.add_argument(
        "--no-default-excludes",
        dest="default_excludes",
        action="store_false",
        help=(
            "also check files marked as generated, and vendored files and license texts "
            "named on the command line; directory scans still skip dependency and build directories"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    files, collection_errors = collect_files(
        args.paths, args.mode, args.exclude, args.default_excludes
    )
    for error in collection_errors:
        print(error, file=sys.stderr)
    findings = 0
    fixed = 0
    file_errors = 0
    for path, mode in files:
        path_findings, path_fixed, error = check_file(
            path, mode, args.fix, args.strict, args.default_excludes
        )
        if error:
            print(f"{display_path(path)}: {error}", file=sys.stderr)
            file_errors += 1
            continue
        findings += path_findings
        fixed += path_fixed
    if fixed:
        noun = "break" if fixed == 1 else "breaks"
        print(f"Fixed {fixed} hard line {noun}.")
    if collection_errors or file_errors:
        return 2
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
