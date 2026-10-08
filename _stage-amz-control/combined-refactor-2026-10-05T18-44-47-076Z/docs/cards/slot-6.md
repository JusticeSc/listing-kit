<!-- ⚠️ 由 tools/gen_slot_cards.py 从 config/slots.yaml 生成，不要直接改这里。 -->
<!-- 改这一格 → 改 config/slots.yaml → 跑 `python tools/gen_slot_cards.py`；一致性由 `python tools/check_docs.py` 守卫。 -->

# 坑位 6 · 包装内容物

**一句话**：内容物原片（已抠）→ 铺白底 → 叠字

| 属性 | 值 |
|---|---|
| 渲染器 | `contents_compose`（内容物合成 + 叠字） |
| 调生成模型 | **否**（全表 1/7 格调模型） |
| 背景 | `pure_white` —— 纯白画布（常量，不是生成） |
| 文字 | `overlay` |
| 平台强制项 | 否 |
| 校验强度 | `loose`（实际跑 3 项） |
| 文案条数上限 | 3 |

## 要什么 —— 缺任何一项就**跳过这一格**（不报错、不凑图）

| 素材 | 是什么 | 缺了会怎样 |
|---|---|---|
| `contents` | 内容物原片 | 跳过这一格 |

## 不做的事

- **不调生成模型**：本格像素全部来自事实（原片 / 文字 / 常量）。全表 7 格里只有 1 格能调模型 —— 判据是「这块像素有没有事实持有者」，不是「这张图重不重要」。
- **不让模型画字**：文字用字体文件绘制，所以**不可能出现错别字**（代价是排版朴素 —— 错字是事故，难看不是）。

## 出错走哪一级（从便宜往贵试，**不许跳级**）

| 校验项 | 走 | 为什么 |
|---|---|---|
| `aspect_ratio` | **L0** | 非 1:1 → 居中补白到正方形（补白，不裁切：绝不切掉主体） |
| `long_side_px` | **L0** | 分辨率不足 → LANCZOS 放大到目标边长 |
| `text_present` | **L1** | 文字没画上 → 重放文字层（不是修像素） |

## 照抄

```bash
python run.py --product examples/product_fullset.json --only 6 --dry-run
python run.py --product examples/product_fullset.json --only 6
```

```text
# 改了一句卖点之后，只重排文字层（秒级、零模型调用）：
python run.py --product examples/product_fullset.json --redo 6 --layer text
```

> 七格**共有**的规矩（齐套怎么算 / 主体为什么只有一份 / 抠图为什么提前 / 导出阈值 / 要签什么字）在 [索引](README.md) 里 —— 那些话每张卡都一样，所以只写一遍。
