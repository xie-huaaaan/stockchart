"""校验 API 文档代码块里的 docstring 与源码一致。

不属于公开 API，只在开发时运行：

    uv run python tools/check_docstrings.py

规则：
- 中文版（docs/api.zh-CN）里每个公开 API 的 docstring 必须与源码逐字一致；
- 英文版（docs/api）里每个公开 API 的 docstring 必须是源码的翻译，因此要求
  小节、参数名与顺序、要点条目数与源码完全对应（措辞由人负责）。

改源码的 docstring 后，先同步中文版，再同步英文版。
"""

from __future__ import annotations

import ast
import inspect
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "stockchart"
API_ZH = ROOT / "docs" / "api.zh-CN"
API_EN = ROOT / "docs" / "api"

MODULES = [
    "canvas.py",
    "color.py",
    "data.py",
    "legs.py",
    "library.py",
    "plot/api.py",
    "plot/scale.py",
    "plot/styles.py",
    "plot/types.py",
    "sketch.py",
    "stocking/render.py",
    "stocking/styles.py",
    "text/render.py",
    "topline.py",
]

# 拆分后的子包：这些模块目前只含私有实现，列入清单是为了将来有公开 API 时能被覆盖
SUBPACKAGE_MODULES = [
    "plot/draw.py",
    "plot/layout.py",
    "stocking/edge.py",
    "stocking/fabric.py",
    "stocking/geometry.py",
    "stocking/ink.py",
    "stocking/shading.py",
]

FENCE = re.compile(r"^```python\s*$")
SECTIONS = ("Args:", "Returns:", "Raises:", "Attributes:")
ENTRY = re.compile(r"^\s{4}(\w+):")


def source_docstrings() -> dict[str, str]:
    """抽取源码里所有公开 API 的 docstring。"""
    found: dict[str, str] = {}
    for rel in MODULES + SUBPACKAGE_MODULES:
        path = SRC / rel
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                found[node.name] = ast.get_docstring(node) or ""
                for sub in node.body:
                    if isinstance(sub, ast.FunctionDef):
                        found[f"{node.name}.{sub.name}"] = ast.get_docstring(sub) or ""
            elif isinstance(node, ast.FunctionDef):
                found[node.name] = ast.get_docstring(node) or ""
    return found


def block_nodes(tree: ast.Module) -> list[tuple[str, ast.AST]]:
    """列出代码块里的 (限定名, 节点)。"""
    out: list[tuple[str, ast.AST]] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            out.append((node.name, node))
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef):
                    out.append((f"{node.name}.{sub.name}", sub))
        elif isinstance(node, ast.FunctionDef):
            out.append((node.name, node))
    return out


def doc_node(node: ast.AST) -> ast.Expr | None:
    """取节点体里的 docstring 语句。"""
    body = getattr(node, "body", None)
    if not body or not isinstance(body[0], ast.Expr):
        return None
    expr = body[0]
    if isinstance(expr.value, ast.Constant) and isinstance(expr.value.value, str):
        return expr
    return None


def structure(text: str) -> dict[str, list[str]]:
    """把 docstring 拆成小节 → 条目名列表。"""
    out: dict[str, list[str]] = {}
    current = ""
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped in SECTIONS:
            current = stripped
            out[current] = []
            continue
        if current:
            match = ENTRY.match(line)
            if match:
                out[current].append(match.group(1))
            elif stripped.startswith("- "):
                out[current].append("-")
    return out


def lookup(src: dict[str, str], name: str) -> str | None:
    """按限定名找源码 docstring，兼容文档里写成顶层函数的 BarPlot 方法。"""
    for key in (name, f"BarPlot.{name}"):
        if src.get(key):
            return src[key]
    return None


def iter_docs(folder: Path):
    """遍历一个目录下的所有 ```python 代码块。"""
    for path in sorted(folder.glob("*.md")):
        lines = path.read_text(encoding="utf-8").split("\n")
        i = 0
        while i < len(lines):
            if FENCE.match(lines[i]):
                start = i + 1
                i += 1
                body: list[str] = []
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    body.append(lines[i])
                    i += 1
                try:
                    tree = ast.parse("\n".join(body))
                except SyntaxError:
                    continue
                for name, node in block_nodes(tree):
                    expr = doc_node(node)
                    if expr is None:
                        continue
                    yield path, start, name, inspect.cleandoc(ast.get_docstring(node) or "")
            i += 1


def main() -> int:
    src = source_docstrings()
    problems: list[str] = []

    zh_checked = 0
    for path, line, name, doc in iter_docs(API_ZH):
        want = lookup(src, name)
        if want is None:
            continue
        zh_checked += 1
        if inspect.cleandoc(want) != doc:
            problems.append(f"{path.relative_to(ROOT)}:{line} {name} 的 docstring 与源码不一致")

    en_checked = 0
    for path, line, name, doc in iter_docs(API_EN):
        want = lookup(src, name)
        if want is None:
            continue
        en_checked += 1
        a, b = structure(want), structure(doc)
        if set(a) != set(b):
            problems.append(
                f"{path.relative_to(ROOT)}:{line} {name} 的小节与源码不符："
                f"源码 {sorted(a)} / 文档 {sorted(b)}"
            )
            continue
        for section in a:
            if a[section] != b[section]:
                problems.append(
                    f"{path.relative_to(ROOT)}:{line} {name}.{section} 的条目与源码不符："
                    f"源码 {a[section]} / 文档 {b[section]}"
                )

    print(f"中文版逐字核对 {zh_checked} 条，英文版结构核对 {en_checked} 条")
    for problem in problems:
        print(f"✗ {problem}")
    if problems:
        print(f"\n共 {len(problems)} 处问题")
        return 1
    print("✓ 文档 docstring 与源码一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
