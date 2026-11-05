"""文档自检：校验 Markdown 结构、相对链接与中英分册的章节对应。

不属于公开 API，只在开发时运行：

    uv run python tools/check_docs.py

检查项：
1. 围栏代码块闭合、标题前后空行、列表与表格前的空行、表格列数一致；
2. 全部相对链接（含 <img src>）指向存在的文件，锚点链接匹配目标标题；
3. 中英分册（docs/api 与 docs/api.zh-CN）的标题层级一一对应。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = [
    ROOT / "README.md",
    ROOT / "README.zh-CN.md",
    ROOT / "AGENTS.md",
    ROOT / "CHANGELOG.md",
    ROOT / "TODO.md",
    ROOT / "docs" / "design.md",
    ROOT / "docs" / "design.zh-CN.md",
    *sorted((ROOT / "docs" / "api").glob("*.md")),
    *sorted((ROOT / "docs" / "api.zh-CN").glob("*.md")),
]

FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
ITEM = re.compile(r"^\s*([-*+]|\d+[.)])\s")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)")
IMG = re.compile(r"<img[^>]*\ssrc=\"([^\"]+)\"")
ESCAPED_PIPE = re.compile(r"\\\|")


def count_pipes(line: str) -> int:
    """数出未被转义的竖线数量（表格列数）。"""
    return len(ESCAPED_PIPE.sub("", line).split("|")) - 1


def check_structure(path: Path) -> list[str]:
    """检查单个文件的 Markdown 结构。"""
    problems: list[str] = []
    lines = path.read_text(encoding="utf-8").split("\n")
    in_code = False
    fence_open = ""
    in_list = False
    table_cols: int | None = None

    for number, line in enumerate(lines, start=1):
        match = FENCE.match(line)
        if match:
            marker = match.group(1)
            if not in_code:
                in_code, fence_open = True, marker
            elif marker[0] == fence_open[0] and not line.strip()[len(fence_open) :].strip():
                in_code, fence_open = False, ""
            continue
        if in_code:
            continue

        text = line.strip()
        if not text:
            in_list = False
            table_cols = None
            continue

        previous = lines[number - 2].strip() if number >= 2 else ""

        if text.startswith("|"):
            columns = count_pipes(text)
            if table_cols is None:
                table_cols = columns
            elif columns != table_cols:
                problems.append(
                    f"{path.relative_to(ROOT)}:{number} "
                    f"表格列数 {columns} 与表头 {table_cols} 不一致"
                )
            in_list = False
            continue
        table_cols = None

        if ITEM.match(text):
            if (
                previous
                and not in_list
                and not previous.startswith("|")
                and not previous.startswith("#")
            ):
                problems.append(f"{path.relative_to(ROOT)}:{number} 列表紧贴上文段落，应空一行")
            in_list = True
        elif line.startswith("  ") and in_list:
            pass
        else:
            in_list = False

        heading = HEADING.match(text)
        if heading:
            if previous and not previous.startswith("#"):
                problems.append(f"{path.relative_to(ROOT)}:{number} 标题前缺空行")
            if number < len(lines) and lines[number].strip():
                problems.append(f"{path.relative_to(ROOT)}:{number} 标题后缺空行")

    if in_code:
        problems.append(f"{path.relative_to(ROOT)} 围栏代码块未闭合")
    return problems


def anchors_of(path: Path) -> set[str]:
    """收集文件的标题锚点（GitHub 风格）。"""
    result: set[str] = set()
    for line in path.read_text(encoding="utf-8").split("\n"):
        heading = HEADING.match(line.strip())
        if heading:
            slug = re.sub(r"[^\w一-鿿\- ]", "", heading.group(2)).strip().lower()
            result.add(re.sub(r"\s+", "-", slug))
    return result


def check_links(path: Path) -> list[str]:
    """检查文件里的相对链接与图片路径。"""
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")
    targets = re.findall(r"\[[^\]]*\]\(([^)\s]+)\)", text)
    targets += re.findall(r"<img[^>]*\ssrc=\"([^\"]+)\"", text)

    for target in targets:
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        file_part, _, anchor = target.partition("#")
        if not file_part:
            continue
        resolved = (path.parent / file_part).resolve()
        if not resolved.exists():
            problems.append(f"{path.relative_to(ROOT)} 链接失效 -> {target}")
            continue
        if anchor and resolved.suffix == ".md" and anchor.lower() not in anchors_of(resolved):
            problems.append(f"{path.relative_to(ROOT)} 锚点失效 -> {target}")
    return problems


def check_bilingual() -> list[str]:
    """检查中英分册的标题层级是否一一对应。"""
    problems: list[str] = []
    english = sorted((ROOT / "docs" / "api").glob("*.md"))
    chinese = sorted((ROOT / "docs" / "api.zh-CN").glob("*.md"))
    if [p.name for p in english] != [p.name for p in chinese]:
        problems.append("docs/api 与 docs/api.zh-CN 的分册文件不一致")
        return problems

    for en_path, zh_path in zip(english, chinese, strict=True):

        def levels(path: Path) -> list[int]:
            out: list[int] = []
            in_code = False
            for line in path.read_text(encoding="utf-8").split("\n"):
                if FENCE.match(line):
                    in_code = not in_code
                    continue
                if in_code:
                    continue
                heading = HEADING.match(line.strip())
                if heading:
                    out.append(len(heading.group(1)))
            return out

        if levels(en_path) != levels(zh_path):
            problems.append(
                f"{en_path.name} 中英标题层级不一致：EN {levels(en_path)} / ZH {levels(zh_path)}"
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
