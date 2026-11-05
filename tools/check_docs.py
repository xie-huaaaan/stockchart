"""文档自检：校验 Markdown 结构、相对链接与中英版本的章节对应。

不属于公开 API，只在开发时运行：

    uv run python tools/check_docs.py

检查项：
1. 围栏代码块闭合、标题前后空行、列表与表格前的空行、表格列数与分隔行；
2. 全部相对链接与 HTML 属性（img src / a href）指向存在的文件，锚点匹配目标标题；
3. 中英两版的标题层级与正文单元（列表项、表格、代码块）数量一一对应。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_ZH = ROOT / "docs" / "api.zh-CN"
API_EN = ROOT / "docs" / "api"

PAIRS = [(API_EN / name, API_ZH / name) for name in sorted(p.name for p in API_EN.glob("*.md"))] + [
    (ROOT / "docs" / "design.md", ROOT / "docs" / "design.zh-CN.md"),
    (ROOT / "README.md", ROOT / "README.zh-CN.md"),
]

DOCS = [
    ROOT / "README.md",
    ROOT / "README.zh-CN.md",
    ROOT / "AGENTS.md",
    ROOT / "CHANGELOG.md",
    ROOT / "TODO.md",
    ROOT / "docs" / "design.md",
    ROOT / "docs" / "design.zh-CN.md",
    *sorted(API_EN.glob("*.md")),
    *sorted(API_ZH.glob("*.md")),
]

FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
ITEM = re.compile(r"^\s*([-*+]|\d+[.)])\s")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
TABLE_SEP = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
# HTML 属性：src / href，值须用 ASCII 引号包裹
HTML_ATTR = re.compile(r"""(?:src|href)\s*=\s*(?P<q>["'])(?P<val>[^"']+)(?P=q)""")
# HTML 属性误用全角引号：解析器会把引号当属性值的一部分，链接必然失效
HTML_ATTR_FULLWIDTH = re.compile(r"""(?:src|href)\s*=\s*[“”]""")
ESCAPED_PIPE = re.compile(r"\\\|")


def rel(path: Path) -> str:
    """把路径转成相对仓库根的短表示。"""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def count_pipes(line: str) -> int:
    """数出未被转义的竖线数量（表格列数）。"""
    return len(ESCAPED_PIPE.sub("", line).split("|")) - 1


def strip_code(lines: list[str]) -> list[bool]:
    """标记每一行是否在围栏代码块内。"""
    flags: list[bool] = []
    inside = False
    fence = ""
    for line in lines:
        match = FENCE.match(line)
        if match:
            marker = match.group(1)
            if not inside:
                inside, fence = True, marker
            elif marker[0] == fence[0] and not line.strip()[len(fence) :].strip():
                inside, fence = False, ""
            flags.append(True)
            continue
        flags.append(inside)
    return flags


def check_structure(path: Path) -> list[str]:
    """检查单个文件的 Markdown 结构。"""
    problems: list[str] = []
    lines = path.read_text(encoding="utf-8").split("\n")
    in_code = strip_code(lines)
    in_list = False
    table_cols: int | None = None
    table_start = 0
    saw_separator = False

    for number, line in enumerate(lines, start=1):
        if in_code[number - 1]:
            continue

        text = line.strip()
        if not text:
            in_list = False
            if table_cols is not None:
                if not saw_separator:
                    problems.append(f"{rel(path)}:{table_start} 表格缺少 | --- | 分隔行")
                table_cols = None
            continue

        previous = lines[number - 2].strip() if number >= 2 else ""

        if text.startswith("|"):
            columns = count_pipes(text)
            if table_cols is None:
                table_cols = columns
                table_start = number
                saw_separator = False
            elif columns != table_cols:
                problems.append(
                    f"{rel(path)}:{number} 表格列数 {columns} 与表头 {table_cols} 不一致"
                )
            if number == table_start + 1:
                saw_separator = TABLE_SEP.match(text) is not None
            in_list = False
            continue

        if table_cols is not None and not saw_separator:
            problems.append(f"{rel(path)}:{table_start} 表格缺少 | --- | 分隔行")
        table_cols = None

        if ITEM.match(text):
            if (
                previous
                and not in_list
                and not previous.startswith("|")
                and not previous.startswith("#")
            ):
                problems.append(f"{rel(path)}:{number} 列表紧贴上文段落，应空一行")
            in_list = True
        elif line.startswith("  ") and in_list:
            pass
        else:
            in_list = False

        heading = HEADING.match(text)
        if heading:
            if previous and not previous.startswith("#"):
                problems.append(f"{rel(path)}:{number} 标题前缺空行")
            if number < len(lines) and lines[number].strip():
                problems.append(f"{rel(path)}:{number} 标题后缺空行")

    if table_cols is not None and not saw_separator:
        problems.append(f"{rel(path)}:{table_start} 表格缺少 | --- | 分隔行")
    if in_code[-1]:
        problems.append(f"{rel(path)} 围栏代码块未闭合")
    return problems


def slugify(title: str) -> str:
    """按 GitHub 的规则生成标题锚点。"""
    text = title.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors_of(path: Path) -> set[str]:
    """收集文件的标题锚点。"""
    lines = path.read_text(encoding="utf-8").split("\n")
    in_code = strip_code(lines)
    result: set[str] = set()
    for line, is_code in zip(lines, in_code, strict=True):
        if is_code:
            continue
        heading = HEADING.match(line.strip())
        if heading:
            result.add(slugify(heading.group(2)))
    return result


def check_links(path: Path) -> list[str]:
    """检查文件里的相对链接、HTML 属性与图片路径。"""
    problems: list[str] = []
    lines = path.read_text(encoding="utf-8").split("\n")
    in_code = strip_code(lines)

    for number, (line, is_code) in enumerate(zip(lines, in_code, strict=True), start=1):
        if is_code:
            continue
        if HTML_ATTR_FULLWIDTH.search(line):
            problems.append(
                f"{rel(path)}:{number} HTML 属性用了全角引号，链接会失效——须用 ASCII 引号"
            )
        targets = MD_LINK.findall(line)
        targets += [m.group("val") for m in HTML_ATTR.finditer(line)]

        for target in targets:
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            file_part, _, anchor = target.partition("#")
            if not file_part:
                continue
            resolved = (path.parent / file_part).resolve()
            if not resolved.exists():
                problems.append(f"{rel(path)}:{number} 链接失效 -> {target}")
                continue
            if anchor and resolved.suffix == ".md" and anchor.lower() not in anchors_of(resolved):
                problems.append(f"{rel(path)}:{number} 锚点失效 -> {target}")
    return problems


def count_code_blocks(lines: list[str]) -> int:
    """统计围栏代码块的块数（不是块内行数）。"""
    blocks = 0
    inside = False
    fence = ""
    for line in lines:
        match = FENCE.match(line)
        if not match:
            continue
        marker = match.group(1)
        if not inside:
            inside, fence = True, marker
            blocks += 1
        elif marker[0] == fence[0] and not line.strip()[len(fence) :].strip():
            inside, fence = False, ""
    return blocks


def units(path: Path) -> dict[str, int]:
    """统计一个文件的正文单元数量，用于中英对照。"""
    lines = path.read_text(encoding="utf-8").split("\n")
    in_code = strip_code(lines)
    counts = {"heading": 0, "bullet": 0, "numbered": 0, "table": 0, "code": 0}
    in_table = False
    for line, is_code in zip(lines, in_code, strict=True):
        if is_code:
            continue
        text = line.strip()
        if not text:
            in_table = False
            continue
        if HEADING.match(text):
            counts["heading"] += 1
        elif ITEM.match(text):
            if re.match(r"^\s*\d+[.)]\s", line):
                counts["numbered"] += 1
            else:
                counts["bullet"] += 1
        if text.startswith("|") and not in_table:
            counts["table"] += 1
            in_table = True
    counts["code"] = count_code_blocks(lines)
    return counts


def check_bilingual() -> list[str]:
    """检查中英两版的标题层级与正文单元数量是否一一对应。"""
    problems: list[str] = []
    for en_path, zh_path in PAIRS:
        if not zh_path.exists():
            problems.append(f"缺少中文对应文件 {rel(zh_path)}")
            continue

        def levels(path: Path) -> list[int]:
            out: list[int] = []
            lines = path.read_text(encoding="utf-8").split("\n")
            for line, is_code in zip(lines, strip_code(lines), strict=True):
                if is_code:
                    continue
                heading = HEADING.match(line.strip())
                if heading:
                    out.append(len(heading.group(1)))
            return out

        en_levels, zh_levels = levels(en_path), levels(zh_path)
        if en_levels != zh_levels:
            problems.append(f"{en_path.name} 中英标题层级不一致：EN {en_levels} / ZH {zh_levels}")

        en_units, zh_units = units(en_path), units(zh_path)
        for key in en_units:
            if en_units[key] != zh_units[key]:
                problems.append(
                    f"{en_path.name} 中英 {key} 数量不一致：EN {en_units[key]} / ZH {zh_units[key]}"
                )
    return problems


def main() -> int:
    problems: list[str] = []
    for path in DOCS:
        problems.extend(check_structure(path))
        problems.extend(check_links(path))
    problems.extend(check_bilingual())

    for problem in problems:
        print(f"✗ {problem}")
    if problems:
        print(f"\n共 {len(problems)} 处问题")
        return 1
    print(f"✓ {len(DOCS)} 个文档，结构、链接与中英对应关系均正常")
    return 0


if __name__ == "__main__":
    sys.exit(main())
