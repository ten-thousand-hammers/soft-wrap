#!/usr/bin/env python3
"""Find and fix physical newlines that split prose sentences."""

from __future__ import annotations

import argparse
import fnmatch
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
    r"^(?:#!|-\*-|=begin|=end|encoding:|frozen_string_literal|HACK|NOTE|OPTIMIZE|REVIEW|rubocop:|standard:|TODO|FIXME)"
)
COMMENT_MARKUP = re.compile(r"^(?:[-*+]\s|\d+[.)]\s|[|>]|```|~~~)")
CODE_LIKE = re.compile(r"[{}]|=>")
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


def continuation_certainty(text: str, strict: bool) -> bool | None:
    if SAFE_CONTINUATION.search(text):
        return True
    if strict and STRICT_CONTINUATION.search(text):
        return False
    return None


def skip_comment_text(text: str) -> bool:
    return bool(
        SKIP_LINE.search(text)
        or COMMENT_MARKUP.search(text)
        or TABULAR.search(text)
        or CODE_LIKE.search(text)
    )


def find_comment_violations(
    lines: Sequence[PhysicalLine],
    strict: bool = False,
    families: frozenset[str] | None = None,
) -> list[Violation]:
    violations: list[Violation] = []
    for block in comment_blocks(lines, families):
        texts = [line.text for line in block]
        if any(GENERATED_BLOCK.search(text) for text in texts):
            continue
        if any(CODE_STATEMENT.search(text) for text in texts):
            continue
        if any(TABULAR.search(text) or DEFINITION_ITEM.search(text) for text in texts):
            continue
        for previous, current in zip(block, block[1:]):
            if not previous.text or not current.text:
                continue
            if skip_comment_text(previous.text) or skip_comment_text(current.text):
                continue
            if previous.gap != current.gap:
                continue
            if HYPHEN_SPLIT.search(previous.text) or ends_sentence(previous.text):
                continue
            certainty = continuation_certainty(current.text, strict)
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
        if HYPHEN_SPLIT.search(previous.text) or ends_sentence(previous.text):
            continue
        certainty = continuation_certainty(current.text, strict)
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


def analyze_text(
    text: str,
    mode: str,
    strict: bool = False,
    comment_families: frozenset[str] | None = None,
) -> list[Violation]:
    lines = split_physical_lines(text)
    if mode == "prose":
        return find_prose_violations(lines, strict)
    if mode == "comments":
        return find_comment_violations(lines, strict, comment_families)
    raise ValueError(f"unknown mode: {mode}")


def apply_safe_fixes(
    text: str,
    mode: str,
    comment_families: frozenset[str] | None = None,
) -> tuple[str, int]:
    fixed = 0
    while True:
        lines = split_physical_lines(text)
        violations = (
            find_prose_violations(lines)
            if mode == "prose"
            else find_comment_violations(lines, families=comment_families)
        )
        safe = [violation for violation in violations if violation.certain]
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


def comment_families_for(path: Path) -> frozenset[str] | None:
    suffix = path.suffix.lower()
    families: set[str] = set()
    if suffix in HASH_COMMENT_SUFFIXES or path.name.lower() in SOURCE_NAMES:
        families.add("#")
    if suffix in SLASH_LINE_COMMENT_SUFFIXES:
        families.add("//")
    if suffix in SLASH_BLOCK_COMMENT_SUFFIXES:
        families.add("/*")
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
    return None


def excluded(path: Path, patterns: Sequence[str]) -> bool:
    candidate = path.as_posix()
    return any(
        fnmatch.fnmatch(candidate, pattern) or fnmatch.fnmatch(path.name, pattern)
        for pattern in patterns
    )


def walk_directory(directory: Path, patterns: Sequence[str]) -> Iterator[Path]:
    for root, directories, filenames in os.walk(directory, followlinks=False):
        directories[:] = sorted(
            name
            for name in directories
            if name.lower() not in IGNORED_DIRECTORIES
            and not excluded(Path(root) / name, patterns)
        )
        for filename in sorted(filenames):
            path = Path(root) / filename
            if not excluded(path, patterns) and infer_mode(path) is not None:
                yield path


def collect_files(
    paths: Sequence[str], forced_mode: str, patterns: Sequence[str]
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
            candidates = walk_directory(path, patterns)
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
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


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


def check_file(path: Path, mode: str, fix: bool, strict: bool) -> tuple[int, int, str | None]:
    text, error = read_utf8(path)
    if error or text is None:
        return 0, 0, error
    families = comment_families_for(path) if mode == "comments" else None
    fixed = 0
    if fix:
        updated, fixed = apply_safe_fixes(text, mode, families)
        if updated != text:
            try:
                path.write_bytes(updated.encode("utf-8"))
            except OSError as write_error:
                return 0, 0, str(write_error)
            text = updated
    violations = analyze_text(text, mode, strict, families)
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
        help="join high-confidence continuations in place",
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
        help="exclude a path or basename glob; repeat as needed",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    files, collection_errors = collect_files(args.paths, args.mode, args.exclude)
    for error in collection_errors:
        print(error, file=sys.stderr)
    findings = 0
    fixed = 0
    file_errors = 0
    for path, mode in files:
        path_findings, path_fixed, error = check_file(
            path, mode, args.fix, args.strict
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
