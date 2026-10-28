#!/usr/bin/env python3
"""Check a spec-lite doc tree: unique ids, resolvable links, no cycles, sane ADRs.

Usage: python3 check_specs.py [docs-root]    (default: docs)
Layout: <root>/spec/**.md  and  <root>/decisions/NNNN-*.md
Exit 0 when clean, 1 on any error.
No third-party imports: frontmatter is parsed by hand (PyYAML is not assumed).
"""

import re
import sys
from pathlib import Path

REQUIRED = ("id", "type", "title")
SINGLE_LINKS = ("parent",)
LIST_LINKS = ("depends-on", "depends_on")
STATUSES = {"draft", "active", "stale", "done", "deprecated"}
KEY_RE = re.compile(r"^([A-Za-z0-9_-]+):\s*(.*)$")
ADR_NAME_RE = re.compile(r"^(\d{4})-[a-z0-9-]+\.md$")
SUPERSEDE_RE = re.compile(r"superseded by ADR-(\d{4})", re.IGNORECASE)


def parse_value(raw: str):
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        return [v.strip().strip("\"'") for v in raw[1:-1].split(",") if v.strip()]
    return raw.strip("\"'")


def read_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    out, key = {}, None
    for line in text[3:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = KEY_RE.match(line)
        if match:
            key, raw = match.group(1), match.group(2)
            if raw:
                value = parse_value(raw)
                if key in LIST_LINKS:
                    out[key] = value if isinstance(value, list) else [value]
                else:
                    out[key] = value
            else:
                out[key] = [] if key in LIST_LINKS else ""
            continue
        if key and line.strip().startswith("-") and isinstance(out.get(key), list):
            out[key].append(line.strip()[1:].strip().strip("\"'"))
    return out


def as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def collect_specs(spec_root: Path):
    specs, extras, errors = {}, [], []
    for path in sorted(spec_root.rglob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        meta = read_frontmatter(path.read_text(encoding="utf-8"))
        if not meta.get("id"):
            errors.append(f"{path}: 缺 frontmatter id")
            continue
        for field in REQUIRED:
            if not meta.get(field):
                errors.append(f"{path}: 缺必填字段 {field}")
        status = meta.get("status")
        if status and status not in STATUSES:
            errors.append(f"{path}: status={status!r} 不在 {sorted(STATUSES)}")
        sid = str(meta["id"])
        if sid in specs:
            errors.append(f"{path}: id 重复 {sid!r}，已被 {specs[sid][0]} 使用")
            extras.append((path, meta))
            continue
        specs[sid] = (path, meta)
    return specs, extras, errors


def check_links(specs, extras=()) -> list:
    errors = []
    for path, meta in list(specs.values()) + list(extras):
        for field in SINGLE_LINKS + LIST_LINKS:
            for target in as_list(meta.get(field)):
                if target not in specs:
                    errors.append(f"{path}: {field} -> {target!r} 不存在")
    return errors


def find_cycle(specs) -> list:
    state, stack = {}, []

    def visit(sid):
        state[sid] = 1
        stack.append(sid)
        for field in SINGLE_LINKS + LIST_LINKS:
            for target in as_list(specs[sid][1].get(field)):
                if target not in specs:
                    continue
                if state.get(target) == 1:
                    return " -> ".join(stack[stack.index(target):] + [target])
                if state.get(target) is None:
                    found = visit(target)
                    if found:
                        return found
        stack.pop()
        state[sid] = 2
        return None

    for sid in specs:
        if state.get(sid) is None:
            found = visit(sid)
            if found:
                return [f"循环引用: {found}"]
    return []


def check_adrs(decision_root: Path) -> list:
    errors, numbers = [], {}
    for path in sorted(decision_root.glob("*.md")):
        match = ADR_NAME_RE.match(path.name)
        if not match:
            errors.append(f"{path}: ADR 文件名须为 NNNN-kebab-title.md")
            continue
        number = match.group(1)
        if number in numbers:
            errors.append(f"{path}: ADR 编号重复 {number}，已被 {numbers[number]} 使用")
        numbers[number] = path.name
    for path in sorted(decision_root.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if not re.search(r"^Status:", text, re.MULTILINE):
            errors.append(f"{path}: 缺 Status: 行")
        for target in SUPERSEDE_RE.findall(text):
            if target not in numbers:
                errors.append(f"{path}: 指向不存在的 ADR-{target}")
    return errors


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "docs")
    if not root.is_dir():
        print(f"ERR 目录不存在: {root}")
        return 1
    spec_root = root / "spec" if (root / "spec").is_dir() else root
    specs, extras, errors = collect_specs(spec_root)
    errors += check_links(specs, extras)
    errors += find_cycle(specs)
    if (root / "decisions").is_dir():
        errors += check_adrs(root / "decisions")
    for line in errors:
        print(f"ERR {line}")
    if errors:
        print(f"{len(errors)} 处错误，未通过")
        return 1
    print(f"OK {len(specs)} specs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
