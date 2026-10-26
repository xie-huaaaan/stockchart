# stockchart

创意绘图库：用丝袜的高度表示数据大小。灵感来源见 `assets/sample.jpg`。

状态：L0–L4 全部实现（素材 / 渲染原语 / 自由柱状图 / 布局封装 / 一行出图），
渲染倍率原生，内置腿素材为透明 SVG（渲染时按目标倍率栅格化），145 个单测通过；
视觉观感已评审通过，下一步是公开 API 整理。
详见 [docs/design.md](docs/design.md) 与 [docs/api.md](docs/api.md)，开发约定见 [AGENTS.md](AGENTS.md)。

```python
from stockchart import bar

bar([320, 480, 250, 560], labels=["一月", "二月", "三月", "四月"], style="gray_sheer").save(
    "chart.png"
)
```
