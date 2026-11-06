# AGENTS.md

stockchart 用丝袜被拉起的高度表示数据大小。设计见 [docs/design.zh-CN.md](docs/design.zh-CN.md)，公开 API 见 `docs/api.zh-CN/` 与 `docs/api/`。开发早期允许破坏性变更，无需兼容旧接口或保持像素一致。

## 开发与验证

- 中文交流。开始前看 `git log --oneline`、工作区状态和相关文档，保留用户已有修改。
- Python 3.12 + uv，`uv sync` 安装依赖；修改 `pyproject.toml` 后由 uv 更新锁文件，不手改 `uv.lock`。
- 提交前运行 `uv run python -m pytest`、`uv run ruff check .`、`uv run ruff format .`、`uv run python -m pyright`；开发中不必反复全量测试。
- 文档改动运行 `uv run python tools/check_docs.py` 和 `uv run python tools/check_docstrings.py`。
- 渲染或布局改动运行 `tools/render_plot_review.py` 与 `tools/render_golden.py`（均用 `uv run python`）；黄金图重生成后用 `--check` 核对，不入库。
- 每个可运行功能点提交一次，提交说明用中文。可自行提交到开发分支，提交到 `main` 须用户同意；发布、推送按用户指令执行。

## 代码与文档

- 代码在 `src/stockchart/`，按职责拆分模块；`tools/` 为开发脚本，`dist/`、`out/` 不供运行时引用或打包。
- 运行时依赖仅限 `skia-python`、`numpy`、`pillow`，新增须先问；开发脚本可用额外依赖。pandas 仅按结构识别，不导入、不加入运行时依赖。
- 全部代码带类型标注，公开 API 不用 `Any`；使用现代 Python 类型语法和 dataclass。中文注释、英文标识符，注释说明原因与隐含约束。
- Docstring 遵循 PEP 257 + Google 风格；公开接口完整说明，私有接口至少说明用途。构造参数、约束、字段集中在类说明中。
- 公开 API 的源码 docstring 是事实来源，改动时同步中英文 API 文档；中文代码块中的 docstring 须与源码逐字一致，英文为翻译。
- L4 透传选项同步 `ChartOptions`、`_OPTION_KEYS` 及中英文 `charts.md` 选项表。
- Markdown 段落和列表项各占一行，不硬折行；中文正文用全角引号，代码与 HTML 属性用 ASCII 引号。

## 绘图约定

- 图表、丝袜和素材元数据使用设计像素（内置腿高 720）；Canvas 与低层原语使用输出像素。输出格式仅 PNG。
- `extent_up` / `extent_down`、L4 `height_px` / `width_px` 仅描述柱区，标题、标签、图例等空间另算；`max_fill` / `max_abs_fill` 相对素材设计高度。
- 默认值集中在 `defaults.py`（样式字段默认值在其 dataclass）；随机行为由 `seed` 控制，相同 seed 可复现，不传则每次随机。

## 素材与许可

- 内置素材在 `assets/`，发布后的腿编号与配对不变；代码为 MPL-2.0，素材及派生数据为 ARR。许可改动同步 `LICENSE`、`ASSETS-LICENSE` 与两份 README。
- SVG、墨线算法或 Skia 版本变化后，运行 `uv run python tools/prepare_asset_data.py` 重生成 `_precomputed/` 的 NPZ/SKP；缺失或失配时运行时会重建。
- 修改素材后用 `tools/render_leg_catalog.py` 重出目录图，并核对左右与配对；素材生成和简化工具见 `tools/`，禁止对同一批素材反复有损简化。
