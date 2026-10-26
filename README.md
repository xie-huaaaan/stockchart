# stockchart

创意绘图库：用丝袜的高度表示数据大小。灵感来源见 `assets/sample.jpg`。

状态：L0–L4 全部实现（素材 / 渲染原语 / 自由柱状图 / 布局封装 / 一行出图），
渲染倍率原生，内置腿素材为透明 SVG（渲染时按目标倍率栅格化），213 个单测通过；
公开 API 已整理：支持 dict / numpy / pandas 风格表对象输入，标题默认居中，
x / y 轴名可直接指定。
详见 [docs/design.md](docs/design.md) 与 [docs/api.md](docs/api.md)，开发约定见 [AGENTS.md](AGENTS.md)。

```python
from stockchart import bar

bar(
    {"一月": 320, "二月": 480, "三月": 250, "四月": 560},
    title="月度统计",
    xlabel="月份",
    ylabel="人数",
    style="gray_sheer",
).save("chart.png")
```
