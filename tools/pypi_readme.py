"""把双语 README 合成 PyPI 项目页用的单文件。

PyPI 页面只渲染打包进包元数据的 long_description：没有仓库路径上下文，
相对链接全部失效；`open` 等属性会被渲染器剥掉；仓库 README 开头的标题、
语言切换行与徽章在页面里既重复又多余。因此合成规则：

- 用 “Stock Chart (丝袜统计图)” 作一级标题，开头放 GitHub 仓库链接；
- 只保留许可相关徽章置顶（代码 MPL / 素材 ARR）；版本与 Python 徽章在 PyPI 页面冗余；
  剔除两份 README 各自的标题与语言切换行，只留正文；
- 英文正文直接铺开，中文正文收进可折叠的 `<details>`（PyPI 渲染器
  不保留 `open` 属性，无法默认展开）；
- 所有相对链接改写为 GitHub 绝对链接（正文链接 → blob 页，图片 → raw，徽章外链同理）。

发布工作流在 `uv build` 之前对检出的 README 副本生成合成版，不提交回仓库。

用法：`python tools/pypi_readme.py README.md README.zh-CN.md`（输出到 stdout），
或 `python tools/pypi_readme.py README.md README.zh-CN.md --in-place`
把结果写回第一个文件。
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

_BLOB = "https://github.com/xie-huaaaan/stockchart/blob/main/"
_RAW = "https://raw.githubusercontent.com/xie-huaaaan/stockchart/main/"

# 正文两侧不允许嵌套方括号，避免吃进徽章那种 [![img](url)](url) 嵌套结构
_MD_LINK = re.compile(r"(!?)\[([^\[\]]*)\]\(([^()\s]+)\)")
_IMG_SRC = re.compile(r'(<img\s[^>]*?src=")([^"]+)(")')
# 徽章外链目标（图片地址已是绝对地址，不受影响）
_BADGE_LINK = re.compile(r"\]\((?!https?://|//|#|mailto:)([^()\s]+)\)")
_BADGE_PREFIXES = ("[![License", "[![Assets")


def _is_relative(url: str) -> bool:
    return not url.startswith(("http://", "https://", "//", "#", "mailto:"))


def rewrite(text: str) -> str:
    """相对链接 → GitHub blob 页；相对图片（含 <img src>）→ raw 地址。"""

    def _md(m: re.Match[str]) -> str:
        if not _is_relative(m[3]):
            return m[0]
        base = _RAW if m[1] else _BLOB
        return f"{m[1]}[{m[2]}]({base}{m[3]})"

    def _img(m: re.Match[str]) -> str:
        if not _is_relative(m[2]):
            return m[0]
        return f"{m[1]}{_RAW}{m[2]}{m[3]}"

    return _IMG_SRC.sub(_img, _MD_LINK.sub(_md, text))


def _strip_header(text: str) -> tuple[str, list[str]]:
    """去掉文件开头的一级标题与语言切换行，返回正文和收集到的徽章行。"""
    lines = text.split("\n")
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and lines[i].startswith("# "):
        i += 1
    badges: list[str] = []
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped:
            i += 1
            continue
        if "](README" in stripped:  # 语言切换行
            i += 1
            continue
        if stripped.startswith("[!["):  # 徽章行：提到合成页顶部，只放一次
            badges.append(stripped)
            i += 1
            continue
        break
    return "\n".join(lines[i:]).strip("\n"), badges


def _absolute_badge_links(badge: str) -> str:
    """把徽章外链的相对目标改成 GitHub blob 地址。"""
    return _BADGE_LINK.sub(lambda m: f"]({_BLOB}{m[1]})", badge)


def compose(en: str, zh: str) -> str:
    """合成双语页面：许可徽章置顶、英文铺开、中文折叠。"""
    en_body, badges = _strip_header(en)
    zh_body, _ = _strip_header(zh)
    # PyPI 页面侧栏自带版本号与 Python 版本要求，置顶只保留许可相关徽章
    kept_badges = " ".join(
        _absolute_badge_links(b) for b in badges if b.startswith(_BADGE_PREFIXES)
    )
    return (
        "# Stock Chart (丝袜统计图)\n"
        "\n"
        "[GitHub: xie-huaaaan/stockchart](https://github.com/xie-huaaaan/stockchart)\n"
        "\n"
        f"{kept_badges}\n"
        "\n"
        f"{rewrite(en_body)}\n"
        "\n"
        "---\n"
        "\n"
        "<details>\n"
        "<summary>简体中文</summary>\n"
        "\n"
        f"{rewrite(zh_body)}\n"
        "\n"
        "</details>\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("readme_en", type=Path, help="英文 README 路径")
    parser.add_argument("readme_zh", type=Path, help="中文 README 路径")
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="把合成结果写回英文 README，而不是输出到 stdout",
    )
    args = parser.parse_args()
    combined = compose(
        args.readme_en.read_text(encoding="utf-8"),
        args.readme_zh.read_text(encoding="utf-8"),
    )
    if args.in_place:
        args.readme_en.write_text(combined, encoding="utf-8", newline="\n")
    else:
        print(combined, end="")


if __name__ == "__main__":
    main()
