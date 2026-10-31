# API 参考

stockchart 的公开 API 分五层（L0–L4），上层只通过下层的公开接口工作；坐标单位是
设计像素，随机性由 `seed` 控制，"裸腿"就是高度为 0 的丝袜。

## 目录

- [L0 — 腿部素材](leg-assets.md)：`Leg` / `LegLibrary` / `load_leg`
- [L1 — 渲染原语](rendering.md)：丝袜样式（`StockingStyle` / `STYLES`）、`render_stocking`、文字与手绘线
- [L2 — 自由柱状图](barplot.md)：`Scale` / `BarPlot`
- [L3 — 布局封装](layout.md)：`add_bars` / `add_grouped_bars` / `add_paired_bars`
- [L4 — 数据输入](data-input.md)：输入形式、`PlotData` / `normalize_data` / `register_data_type`
- [L4 — bar() 与 mirror_bar()](charts.md)：一行出图与 `ChartOptions` 透传选项

## 全局约定

- **坐标单位**一律是设计像素（腿高 720 的设计坐标系）；最终输出的放大倍数是独立的 `scale` 参数。
- **随机性**：选腿、丝袜纹理、手绘抖动全部由 `seed` 控制，同参数同 seed 渲染结果完全一致；不传 `seed` 则每次随机。
- **裸腿**即"丝袜高度为 0"，没有单独的开关。
- 上层只通过下层的公开接口工作：

| 层 | 职责 | 内容 |
| --- | --- | --- |
| L0 素材 | 腿素材的加载与选取 | `Leg` `LegLibrary` `load_leg` |
| L1 渲染原语 | 单个元素绘制 | `render_stocking` `StockingStyle` `STYLES` `draw_text` `sketch_line` `sketch_axis` |
| L2 自由柱状图 | 画布、基线、任意贴腿、配轴 | `Scale` `BarPlot` |
| L3 布局封装 | 统一间距、自动选腿 | `BarPlot.add_bars` 等便捷方法 |
| L4 一行出图 | 数据归一化 + 全自动布局 | `bar` `mirror_bar` |

`Canvas`、`Color` 为跨层基础对象，单列于下。

## 基础对象

```python
type Color = tuple[int, int, int] | tuple[int, int, int, int]
"""0–255，可带 alpha。"""


class Canvas:
    """最终渲染结果的载体：一块 RGBA 画布。

    通常由 `BarPlot.render()` 产生并绘制；自由绘制时也可直接构造，
    配合 L1 原语（`draw_text` / `sketch_*`）在上面作画。
    """

    def __init__(
        self,
        width_px: int,
        height_px: int,
        *,
        background: Color = DEFAULT_BACKGROUND,
    ) -> None:
        """构造空白画布并填充背景色。尺寸单位为设计像素。"""

    def save(self, path: str | Path) -> Path:
        """写出 PNG 文件。"""

    def to_pil(self) -> Image:
        """导出为 PIL Image（RGBA）。"""

    def to_numpy(self) -> np.ndarray:
        """导出为 (H, W, 4) uint8 RGBA 数组。"""
```

`BarPlot` 也提供 `save` / `to_pil` 直通方法（见 [L2 — 自由柱状图](barplot.md)），保证 L4 一行能出图。
