# AGENTS.md

stockchart 是一个创意绘图库：用丝袜被拉起的高度表示数据大小。设计见
[docs/design.zh-CN.md](docs/design.zh-CN.md)，公开 API 以 `docs/api.zh-CN/`
（英文版 `docs/api/`）为准，中英文需同步修改。

## 现状

L0–L4 已全部可用：腿素材、丝袜渲染、自由柱状图、布局封装、一行出图；19 个样式，
输出 PNG。数据输入走 `normalize_data`（序列 / numpy / dict / pandas 风格表对象），
L4 的下层参数通过 `ChartOptions` 透传。新会话先看 `git log --oneline`，再读本文件与
`docs/`。

## 环境

- Python 3.12 + uv；依赖写进 `pyproject.toml`，不手改 `uv.lock`。
- `uv sync`
- `uv run python -m pytest`
- `uv run ruff check . && uv run ruff format .`
- `uv run python -m pyright`
- `uv run python tools/render_plot_review.py`：重出评审图到 `out/plots/`
- 素材管线：`uv run python tools/split_master.py dist/all_up_1.png`；改动素材后重出
  `out/preview_svg.png` 并核对配对与左右。

## 目录

- `src/stockchart/`：库源码；`assets/` 只放 `leg_XX.svg` 与 `legs.json`。
- `tests/`、`docs/`
- `tools/`：开发脚本，不属于公开 API，可依赖 scipy / vtracer。
- `dist/`、`out/`：开发素材与评审产物，不打包、运行时不引用。

## 必须遵守

- 运行时依赖只允许 `skia-python`、`numpy`、`pillow`；新增前先问。
- 坐标单位是设计像素（腿高 720）；输出只有 PNG，不做 SVG/PDF。
- 内置腿素材是透明 SVG，`render_stocking(scale=)` 按目标倍率栅格化；腿编号与配对
  一经发布不得变动。代码为 MPL-2.0，腿素材为 ARR，不得单独再分发或改作独立素材；
  改许可声明须同步 `LICENSE`、`ASSETS-LICENSE` 与两份 README。
- 默认值集中在 `defaults.py`；随机行为由 `seed` 控制，保证可复现。
- pandas 只按 `index` / `columns` / `to_numpy()` 结构识别，不 import、不进依赖。
- 公开 API 的 docstring 与 `docs/api.zh-CN/`（及英文版 `docs/api/`）同步；改签名先改文档。
- 新增 L4 透传参数时同步 `ChartOptions`、`_OPTION_KEYS` 与 `docs/api.zh-CN/charts.md`
  的选项表。

## 风格与提交

- 现代 Python：`type` 别名、`X | None`、`dataclass(slots=True, frozen=True)`。
- 全部代码带类型标注；公开 API 不用 `Any`。
- 中文文档/注释，英文标识符；内部函数一两句 docstring 即可。
- 每完成一个可运行的功能点提交一次，中文一句话概述；提交前跑测试 / ruff / pyright。
- 需求不明确先问用户；用中文交流；外网站点打不开时提醒开 VPN。
