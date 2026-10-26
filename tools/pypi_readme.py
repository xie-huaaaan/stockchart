"""把 README 里的相对链接改写为 GitHub 绝对链接，供 PyPI 项目页渲染。

PyPI 页面只渲染打包进包元数据的 long_description，没有仓库路径上下文，
相对链接（图片、文档）在那里全部失效。发布工作流在 `uv build` 之前对
检出的 README 副本原地改写一次，不提交回仓库。

用法：`python tools/pypi_readme.py README.md`（输出到 stdout），
或 `python tools/pypi_readme.py README.md --in-place` 原地覆盖。
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

_OWNER_REPO = "xie-huaaaan/stockchart"
_BLOB = f"https://github.com/{_OWNER_REPO}/blob/main/"
_RAW = f"https://raw.githubusercontent.com/{_OWNER_REPO}/main/"

_MD_LINK = re.compile(r"(!?)\[([^\]]*)\]\(([^()\s]+)\)")
_IMG_SRC = re.compile(r'(<img\s[^>]*?src=")([^"]+)(")')


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("readme", type=Path, help="README 文件路径")
    parser.add_argument("--in-place", action="store_true", help="原地覆盖而不是输出到 stdout")
    args = parser.parse_args()
    text = rewrite(args.readme.read_text(encoding="utf-8"))
    if args.in_place:
        args.readme.write_text(text, encoding="utf-8", newline="\n")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
