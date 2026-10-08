<!-- ⚠️ 由 tools/gen_slot_cards.py 从 config/slots.yaml 生成，不要直接改这里。 -->
<!-- 改这一格 → 改 config/slots.yaml → 跑 `python tools/gen_slot_cards.py`；一致性由 `python tools/check_docs.py` 守卫。 -->

# 坑位卡索引

一份对应一个动作的交付单元。由 `config/slots.yaml` 生成，**读它就不用读代码**。

| 坑 | 用途 | 渲染器 | 调模型 | 要的素材 | 卡 |
|---|---|---|---|---|---|
| 1 | 主图 / 纯白底展示 | `compose_white` | 否 | `front` | [slot-1.md](slot-1.md) |
| 2 | 卖点图解 / 信息图 | `flat_overlay` | 否 | `front`、`bullets` | [slot-2.md](slot-2.md) |
| 3 | 尺寸规格 | `flat_overlay` | 否 | `front`、`specs` | [slot-3.md](slot-3.md) |
| 4 | 场景使用 | `gen_bg_paste` | **是** | `front` | [slot-4.md](slot-4.md) |
| 5 | 细节材质 | `closeup_crop` | 否 | `closeup` | [slot-5.md](slot-5.md) |
| 6 | 包装内容物 | `contents_compose` | 否 | `contents` | [slot-6.md](slot-6.md) |
| 7 | 对比 / 信任背书 | `compare_side` | 否 | `front`、`competitor` | [slot-7.md](slot-7.md) |

全表 7 格，其中 **1 格**调用生成模型。

---

## 七格共有的规矩（卡里不重复写 —— 每张都一样的话只该有一份）

- **缺料不凑图。** 缺任何一项素材就跳过那一格，不拿别的图顶上 —— 凑出来的图花掉的是信任。"没拍特写"与"拍糊了"是两件不同的事：前者跳过，后者整批拒收。
- **张数是算出来的，不是配置项。** 实际出几张 = 本表 ∩ 素材齐套，消费方是 `src/assets.py`。没有"输出几张"这种设置。
- **主体只有一份（不变量 A）。** 凡需要 `front` 的格子读的是同一份 `subject.png`、同一个 sha256。所以「几张图里的杯子不是同一个杯子」在结构上不可能发生 —— 这是数据约束，不是提示词里的期望。
- **抠图提前、集中做。** 渲染器声明要求先抠好的素材（见 `src/registry.py` 的 `cuts` 声明），抠图一律排在任何模型调用**之前**：抠图失败就不该再烧调用费，而且一轮只抠一次 —— 于是"只改了位置"的重做不必重抠，产出的像素与上一版逐字节一致。
- **出错走哪一级的判据一处定义**，在 `src/fixers.py` 的 `CHECK_RUNG`。加一条校验规则时必须同时给它归类，否则「它落到哪一级」就变成没人说得清的问题。
- **阈值（出图与校验共用，不许两处各写一份）**：画布 1600×1600，平台下限长边 1000px，体积上限 10MB，JPEG 质量 92；文件名 `{upc}_{slot}_{seq}` 必须含 UPC —— 文件名不含产品标识会阻碍过审。

## 要签的字（工具判不了，须有人负责，不签不出图）

| 签字项 | 什么时候要求 |
|---|---|
| `no_watermark` / `no_props` / `single_subject` / `angle_ok` | 本次提供了任何图片素材（这四条都判不了：没有规则可写，硬写一个启发式检测器产出的是**不可靠的告警** —— 那比不检更坏）|
| `font_license` | 本次会出文字（`text != none` 的格子存在）|
| `competitor_clean` | 位置 7 在本次的计划里（它会把竞品原片并排放进成品图）|

## 两条约定

- **卡是生成的，不要直接改。** 改 `config/slots.yaml` 那一行，再跑 `python tools/gen_slot_cards.py`。不一致会被 `python tools/check_docs.py` 报成 `stale`。
- **围栏有语义**：```bash 里的命令守卫**会真跑**（缺 `--dry-run` 就自动补上，守卫不替人花钱调模型）；```text 里的是给人看的示例，不执行。所以往卡里写命令时，能跑的放 bash，需要前置状态的放 text。
