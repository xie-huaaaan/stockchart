# AGENTS.md

stockchart：创意绘图库，用丝袜（stocking）的高度表示数据大小。效果参考 `assets/sample.jpg`。
设计细节见 [docs/design.md](docs/design.md)，本文件只写约定。

## 当前进度

- ✅ L0 素材层（`legs.py`/`library.py`/`src/stockchart/assets/`）与 L1 丝袜渲染原语
  （`stocking/`：`render_stocking`、`StockingStyle` 及 19 个 `STYLES` 预设）完成并经用户评审；
- ✅ L1 文字与线条（`canvas.py`/`text.py`/`sketch.py`）、L2 `Scale`/`BarPlot`（`plot.py`）、
  L3 `add_bars` 系列与 L4 `bar`/`mirror_bar`（`topline.py`）完成；单测 213 项；
  视觉观感（间距、刻度、标签、图例、光影、标题、轴名）已评审通过；
- ✅ 绘制细节补齐：坐标轴默认直线（`axis_style="clean"`，手绘抖动可选）、
  x 标签过长自动倾斜避让、图例长标签自动折行/省略、默认组间距 120；
- ✅ 渲染倍率原生：`render_stocking(scale=)` 在目标像素空间生成袜身纹理与光影，
  `BarPlot.render(scale=)` 位图按 1:1 贴图；内置素材只存**透明 SVG**
  （`src/stockchart/assets/leg_XX.svg`），渲染时按目标倍率栅格化，不再存位图；
- ✅ 公开 API 整理：`normalize_data`（`functools.singledispatch`）支持序列 / numpy /
  dict / pandas 风格表对象与自定义注册（不 import pandas）；L4 透传参数收进
  `ChartOptions`（`**options: Unpack[ChartOptions]`）；标题默认居中，新增
  `title` / `xlabel` / `ylabel` 与 L2 的 `add_x_axis_name` / `add_y_axis_name`；
- 评审产物在 `out/`（gitignore），`tools/render_styles_review.py`、
  `tools/render_matrix_review.py`、`tools/render_plot_review.py` 可随时重出全部对比图。

## 已定决策（评审得出，改动前先确认）

- **光影作用于整条腿**：`Shading.skin=0.5`（皮肤用暖色 `skin_shadow_color`）；
  `0` 为"只作用于袜子"的旧观感；裸腿同样参与，保证同图各腿受光一致。
- **内置素材只存透明 SVG**：`tools/split_master.py` 把 13 对超分母图切分、拉伸到
  设计尺寸 × 4 后追踪成彩色 SVG，再用腿身可见轮廓生成 `<clipPath>` 恢复透明背景；
  `src/stockchart/assets/` 只有 `leg_XX.svg` 与 `legs.json`，没有位图。
  `render_stocking(scale=k)` 按目标倍率栅格化 SVG；`Leg.image` 只是设计尺寸的
  布局预览（`pixels_per_unit=1`），渲染时不使用它。
- **不做图表 SVG 输出**：袜身是逐像素算法，输出只有 PNG；SVG 仅作为腿素材的
  内部格式，不对外导出。
- **不做“高密度位图 + 降采样”**：矢量素材一份源覆盖 1×/2×/4×，按目标高度
  栅格化，避免位图的二次采样。
- **skia 的 SVG clipPath 只在固有尺寸下正确**：`vector.rasterize_svg` 先按
  SVG 固有尺寸（设计 × 4）渲染，再 Lanczos 缩放到目标；不要在别处直接把
  SVG 容器缩放到目标尺寸。
- **坐标轴默认不成手绘风**：`axis_style="clean"` 为默认（直线轴线/箭头/刻度/网格），
  `"handdrawn"` 才启用 seed 控制的抖动。评审认为默认手绘观感不佳。
- **长标签用主流库的避让方式**：x 标签默认 `rotation="auto"`，相邻标签相压时
  逐级尝试 45°/60°/75°/90° 并补足画布边距；图例标签超过行宽自动折行（最多 3 行，
  仍放不下末行省略），不靠无限加宽画布。`rotation=0` 可关闭倾斜。
- **L4 数据输入走 `normalize_data`**：`functools.singledispatch` 处理序列 / numpy /
  `Mapping`，pandas 表对象按 `index` / `columns` / `to_numpy()` 结构识别，
  **运行时不 import pandas**。`dict` 标量值→键作 x 标签，等长序列值→键作系列名；
  显式 `labels` / `series_labels` 覆盖推断值；自定义类型用 `register_data_type`。
- **L4 透传参数用 `ChartOptions` 打包**：只把图表语义参数留在签名；
  `axis_style` / `background` / `grid` / `ticks` / `x_label_pos` / `x_label_rotation` /
  `title_align` / 字号 / `legend_*` / `bar_gap` / `group_gap` 走 `**options`，
  内部路由到 `BarPlot` / `add_*`，未知键报 `TypeError`。旧关键字写法仍可用。
- **标题默认居中**：`add_title` 在绘图区上方居中（52px），`align="left"` 可左对齐；
  比画布宽时对称扩宽，不折行不裁字。轴名 30px：x 轴名横排居中在标签之下，
  y 轴名逐字竖排在刻度数字左侧。`add_y_axis` 不再接收 `label`，名称统一用
  `add_y_axis_name`。

## 环境与命令

- Python 3.12，`uv` 管理依赖。依赖写进 `pyproject.toml`，不手改 `uv.lock`。
- `uv sync`：安装依赖
- `uv run python -m pytest`：测试（本机裸 `uv run pytest` 有脚本路径问题）
- `uv run ruff check . && uv run ruff format .`：lint 与格式化
- `uv run python -m pyright`：类型检查（strict）
- `uv run python tools/split_master.py dist/all_up_1.png`：
  切分 13 对超分母图、生成透明 SVG 素材（`src/stockchart/assets/leg_XX.svg`）
  与 `out/preview_svg.png`；`--only leg_01` 可只处理一条
- `uv run python tools/split_legs.py`：从 720p 行图生成设计尺寸位图参考
  （`assets/legs_720/`，仅供核对/兜底，不进库）
- `uv run python tools/render_plot_review.py` 等：重出评审图到 `out/`

## 目录

- `src/stockchart/`：库源码。`src/stockchart/assets/` 只放打包进库的资源：
  `leg_XX.svg`（透明矢量素材）与 `legs.json`。
- `assets/`：开发期原始素材与参考图（`row1–3.png`、`sample.jpg`、
  `legs_720/` 位图参考），不打包、运行时不引用。
- `dist/`：用户用 Upscayl 做的 4×/5× 超分母图（gitignore，不入库），
  供 `split_master.py` 使用。
- `tools/`：开发脚本（`split_legs.py` 720p 参考、`split_master.py` SVG 素材、
  `render_*_review.py` 评审图），不属于库的公开 API，
  可依赖 scipy / vtracer 等 dev 依赖。
- `tests/`、`docs/`

## 依赖

- 运行时只允许：`skia-python`（渲染、文字）、`numpy`、`pillow`。新增运行时依赖前先和用户确认。
- 不使用 matplotlib。不依赖系统是否装有某个具体字体。
- 开发依赖（pytest、ruff、pyright、scipy、vtracer）放在 `[dependency-groups].dev`；
  后两者只给 `tools/split_master.py` 的素材管线用，不进运行时。

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
  设计像素（腿高 720），是布局坐标系；`pixels_per_unit` 表示"`image` 像素 / 设计像素"。
  内置素材的 `image` 是设计尺寸预览（1），渲染时按目标倍率栅格化 SVG；外部位图
  素材才可能 >1。调用方从不传设计尺寸，上层代码也不该改它。
- 腿编号全局唯一、一经发布不得变动：`leg_01`…`leg_26`，按 row1→row3、从左到右；
  配对编号 `pair_01`…`pair_13`。
- 元数据至少含：腿编号、所属配对编号、左/右、来源行与序号、像素尺寸、足底中心 x、足底宽度。
- 切分时丢弃像素面积过小的杂点（用户手工制作时的瑕疵），阈值写在脚本常量里。
- **内置素材是透明 SVG**：`tools/split_master.py` 从 `dist/all_up_1.png`（13 对 /
  26 条腿）切分，按形状匹配（alpha 掩膜 IoU）认领 `leg_XX`；每条腿拉伸到设计
  尺寸 × 4，用 vtracer 追踪成彩色 SVG，再用腿身可见轮廓（蓝色通道低于纸底）生成
  `<clipPath>`，得到透明背景。母图左右贴边的腿会被截断（当前 pair_04/08），同一对
  一起回退到 720p 行图，其余来自 AI 母图。`Leg.image` 只是设计尺寸的布局预览，
  渲染由 `render_stocking` 按 `scale` 重新栅格化；没有位图素材、没有多分辨率阶梯。
- `tools/split_legs.py` 从 720p 行图生成 `assets/legs_720/` 位图参考，仅供核对与
  母图贴边兜底，不进库；库内编号/配对以 `legs.json` 为准。
- 修改素材后必须重新生成 `out/preview_svg.png` 并让用户核对配对与左右。

## 渲染约定

- 坐标单位是"设计像素"（腿高 720）；输出分辨率用 `scale` 参数（像素/设计单位）。
- 袜身在 `scale` 倍像素空间里**重新生成**（样式里的像素长度随之放大），不是放大成品图；
  内置 SVG 素材按目标倍率栅格化（skia 固有尺寸渲染后缩放），外部位图按比例重采样，
  图层按设备像素 1:1 贴图。
- 文字走 skia，字体选择见 docs/design.md"字体"一节：逐字符回退，保证中文可显示；
  找不到字形时用"豆腐块"而不是抛异常。单行绘制原语 `draw_text(rotation=)` 绕
  锚点旋转；多行由 `wrap_text` 与调用方排版（图例）。
- 坐标轴样式由 `BarPlot(axis_style=)` 决定，L4 经 `ChartOptions` 传入；默认 `"clean"`。
- x 标签在相邻位置放不下时自动倾斜（角度随位置在基线上/下取正负），用旋转后的
  包围盒计算上下/左右边距；图例长标签在可用宽度内折行。
- 标题默认在绘图区上方居中（`DEFAULT_TITLE_SIZE=52`），轴名 `DEFAULT_AXIS_NAME_SIZE=30`；
  标题 / 轴名比画布宽时对称扩宽并保留左右边距，不折行、不裁字。y 轴名逐字竖排。
- L4 的数据归一与选项透传：`normalize_data`（`singledispatch`）负责所有输入格式，
  `ChartOptions`（`TypedDict` + `Unpack`）负责下层参数；新增透传参数时同步三处：
  `ChartOptions`、`_OPTION_KEYS`、docs/api.md 的选项表。
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
