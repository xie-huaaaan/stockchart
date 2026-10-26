# AGENTS.md

stockchart：创意绘图库，用丝袜（stocking）的高度表示数据大小。效果参考 `assets/sample.jpg`。
设计细节见 [docs/design.md](docs/design.md)，本文件只写约定。

## 当前进度

- ✅ L0 素材层（`legs.py`/`library.py`/`src/stockchart/assets/`）与 L1 丝袜渲染原语
  （`stocking/`：`render_stocking`、`StockingStyle` 及 19 个 `STYLES` 预设）完成并经用户评审；
- ✅ L1 文字与线条（`canvas.py`/`text.py`/`sketch.py`）、L2 `Scale`/`BarPlot`（`plot.py`）、
  L3 `add_bars` 系列与 L4 `bar`/`mirror_bar`（`topline.py`）完成；单测 141 项；
  视觉观感（间距、刻度、标签、图例、光影）已评审通过；
- ✅ 渲染倍率原生：`render_stocking(scale=)` 在目标像素空间生成袜身纹理与光影，
  `BarPlot.render(scale=)` 位图按 1:1 贴图；素材用 `Leg.pixels_per_unit` 表达密度，
  内置 2 倍密素材由 `tools/trace_legs.py` 生成；
- ⬜ 待做：公开 API 整理——`functools.singledispatch` 支持 pandas 等常用数据结构
  （不硬依赖这些库）、参数收敛（下层透传参数改用 `**kwargs` 打包）、文档同步。
  用户明确表示：现阶段以渲染效果为先，API 允许较大调整；
- 评审产物在 `out/`（gitignore），`tools/render_styles_review.py`、
  `tools/render_matrix_review.py`、`tools/render_plot_review.py` 可随时重出全部对比图。

## 已定决策（评审得出，改动前先确认）

- **光影作用于整条腿**：`Shading.skin=0.5`（皮肤用暖色 `skin_shadow_color`）；
  `0` 为"只作用于袜子"的旧观感；裸腿同样参与，保证同图各腿受光一致。
- **不做 SVG 输出**：袜身是逐像素算法（条纹相位、网眼、蕾丝孔点、光影、墨线检测），
  转矢量要么重写渲染器、要么追踪成品（会改变线宽）。输出只有 PNG。
- **矢量化只用于素材**：`tools/trace_legs.py` 先放大 4 倍再追踪（1–2px 细线与
  灰阶在原分辨率下会被追踪器混匀/变淡，墨量偏大 20%–55%；预放大后误差 <5%）；
  用户已用 Upscayl 备好 4× 超分母图（`dist/`，gitignore），不再做手工矢量母版。
- **一套高密度素材 + 按需降采样**，不做多分辨率阶梯：素材比目标密则降采样。

## 环境与命令

- Python 3.12，`uv` 管理依赖。依赖写进 `pyproject.toml`，不手改 `uv.lock`。
- `uv sync`：安装依赖
- `uv run python -m pytest`：测试（本机裸 `uv run pytest` 有脚本路径问题）
- `uv run ruff check . && uv run ruff format .`：lint 与格式化
- `uv run python -m pyright`：类型检查（strict）
- `uv run python tools/trace_legs.py [--density 2] [--pre-scale 4] [--only leg_01]`：
  由 720p 素材生成 `leg_XX@Nx.png` 与 `legs_hires.json`
- `uv run python tools/render_plot_review.py` 等：重出评审图到 `out/`

## 目录

- `src/stockchart/`：库源码。`src/stockchart/assets/` 只放打包进库的资源
  （`leg_XX.png` 设计尺寸素材、`leg_XX@2x.png` 高密度素材、`legs.json` 与 `legs_hires.json`）。
- `assets/`：开发期原始素材与参考图（`row1–3.png`、`sample.jpg`），不打包、运行时不引用。
- `dist/`：用户用 Upscayl 做的 4×/5× 超分母图（gitignore，不入库），供素材管线使用。
- `tools/`：开发脚本（`split_legs.py` 切分、`trace_legs.py` 矢量化、`render_*_review.py` 评审图），
  不属于库的公开 API，可依赖 scipy / vtracer / cairosvg 等 dev 依赖。
- `tests/`、`docs/`

## 依赖

- 运行时只允许：`skia-python`（渲染、文字）、`numpy`、`pillow`。新增运行时依赖前先和用户确认。
- 不使用 matplotlib。不依赖系统是否装有某个具体字体。
- 开发依赖（pytest、ruff、pyright、scipy、vtracer、cairosvg）放在 `[dependency-groups].dev`；
  后两者只给 `tools/trace_legs.py` 用，不进运行时。

## 代码约定

- 使用现代语法：`def f[T](x: list[T]) -> T`、`type Alias = ...`、`X | None`、`match`、`dataclass(slots=True, frozen=True)`。
- 全部代码带类型标注，公开 API 不用 `Any`。
- 内部实现代码：模块、类、函数写简短文档注释（一两句话说明功能，不复述参数名）。
- 公开 API（[docs/api.md](docs/api.md) 收录的接口）：docstring 完整——功能、参数、返回值、语义与默认行为（边界值、0 值处理等），与 api.md 保持一致。
- 行内注释主要写“为什么”（取舍、约束、坑）；只有作用无法一眼看出时才写“做了什么”。不写来历、不写“修复了 xxx”。
- 公共 API 分五层：L0 素材（`Leg`/`LegLibrary`/`load_leg`）→ L1 渲染原语（`render_stocking`、文字与手绘线）→ L2 自由柱状图（`BarPlot`/`Scale`/`Canvas`）→ L3 布局封装（`add_bars` 等便捷方法）→ L4 一行出图（`bar`/`mirror_bar`）。上层只通过下层的公开接口工作；签名以 docs/api.md 为准，改动先改文档再改代码。
- 默认行为要合理，所有魔法数字（80%、y 轴极大值、颜色、间距等）都暴露为可调参数，并有集中的默认值定义，不散落在绘制代码里。
- 渲染结果应可复现：任何随机行为都由 `seed` 控制。
- 性能热点优先用 numpy 向量化；只有 profile 证明不够再考虑 C/C++ 扩展，且需先与用户确认。

## 素材约定

- **设计像素 vs 图像密度**：`Leg` 的 `width/height/foot_center_x/foot_width` 一律是
  设计像素（腿高 720），是布局坐标系；`pixels_per_unit` 表示"图像像素 / 设计像素"。
  调用方从不传设计尺寸，上层代码也不该改它。
- 切分脚本为 `tools/split_legs.py`，输出到 `src/stockchart/assets/`：每条腿一个带 alpha
  的 PNG（720 高），外加元数据 `legs.json`。
- 腿编号全局唯一、一经发布不得变动：`leg_01`…`leg_26`，按 row1→row3、从左到右；
  配对编号 `pair_01`…`pair_13`。
- 元数据至少含：腿编号、所属配对编号、左/右、来源行与序号、像素尺寸、足底中心 x、足底宽度。
- 切分时丢弃像素面积过小的杂点（用户手工制作时的瑕疵），阈值写在脚本常量里。
- **高密度素材**：`tools/trace_legs.py` 先放大 4× 再矢量化（vtracer stacked）再栅格化，
  产出 `leg_XX@2x.png`（alpha 取原图升采样，保证轮廓不变）与 `legs_hires.json`；
  `LegLibrary` 按该 json 自动选最密的一套并写 `pixels_per_unit`。
  用户已用 Upscayl 备好 4× 超分母图（`dist/`），后续升级素材走同一条管线。
- 修改素材后必须重新生成预览图（带编号）并让用户核对配对与左右。

## 渲染约定

- 坐标单位是"设计像素"（腿高 720）；输出分辨率用 `scale` 参数（像素/设计单位）。
- 袜身在 `scale` 倍像素空间里**重新生成**（样式里的像素长度随之放大），不是放大成品图；
  位图按设备像素 1:1 贴图，素材比目标密时降采样。
- 文字走 skia，字体选择见 docs/design.md"字体"一节：逐字符回退，保证中文可显示；
  找不到字形时用"豆腐块"而不是抛异常。
- 输出格式：PNG 文件，以及内存中的 numpy 数组 / PIL Image。不做 SVG/PDF（理由见"已定决策"）。

## 版本管理（Git）

- 仓库根目录即项目根目录，`main` 为开发主线。
- 每完成一个可运行的功能点或修复就 commit，消息用中文一句话概述改动要点；
  不确定是否保留的实验性改动先开 `experiment/*` 分支，常规迭代直接提交 `main`。
- 提交前跑 `uv run python -m pytest`（本机 `uv run pytest` 有脚本路径问题）。
- `out/` 为评审产物目录，不入库（已 gitignore），评审前用 `tools/render_*_review.py` 重新生成。
- 新会话接手时先 `git log --oneline` 了解进度，再读本文件与 docs/。

## 协作

- 需求不明确时先问用户，不要硬猜；无法访问外网站点时提醒用户开启 VPN。
- 用中文与用户交流、写文档；代码标识符用英文，注释与文档字符串用中文。
