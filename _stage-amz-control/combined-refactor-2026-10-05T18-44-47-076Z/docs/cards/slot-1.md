<!-- ⚠️ 由 tools/gen_slot_cards.py 从 config/slots.yaml 生成，不要直接改这里。 -->
<!-- 改这一格 → 改 config/slots.yaml → 跑 `python tools/gen_slot_cards.py`；一致性由 `python tools/check_docs.py` 守卫。 -->

# 坑位 1 · 主图 / 纯白底展示

**一句话**：subject.png → 纯白画布居中

| 属性 | 值 |
|---|---|
| 渲染器 | `compose_white`（纯白底合成） |
| 调生成模型 | **否**（全表 1/7 格调模型） |
| 背景 | `pure_white` —— 纯白画布（常量，不是生成） |
| 文字 | `none` |
| 平台强制项 | 是（不可关闭） |
| 校验强度 | `strict`（实际跑 8 项） |
| 主体占比 | 85%（出图参数与校验判据是**同一个数**） |

## 要什么 —— 缺任何一项就**跳过这一格**（不报错、不凑图）

| 素材 | 是什么 | 缺了会怎样 |
|---|---|---|
| `front` | 正面原片 | 跳过这一格 |

## 不做的事

- **不调生成模型**：本格像素全部来自事实（原片 / 文字 / 常量）。全表 7 格里只有 1 格能调模型 —— 判据是「这块像素有没有事实持有者」，不是「这张图重不重要」。
- **不叠字**：本格的平台档位要求画面里没有任何文字。

## 出错走哪一级（从便宜往贵试，**不许跳级**）

| 校验项 | 走 | 为什么 |
|---|---|---|
| `white_bg_purity` | **L0** | 背景近白但不纯 → 只刷与边缘连通的背景区（不碰主体） |
| `product_fill` | **L0** | 占比不足 → 裁掉多余留白并重排画布（放大倍数过大则退回 L1） |
| `has_text_block` | **L3** | 位置 1 出现文字：擦掉是掩盖违规内容，必须查明来源 |
| `aspect_ratio` | **L0** | 非 1:1 → 居中补白到正方形（补白，不裁切：绝不切掉主体） |
| `long_side_px` | **L0** | 分辨率不足 → LANCZOS 放大到目标边长 |
| `filename_has_upc` | **L3** | 改名属交付层，不动像素 |
| `file_size` | **L0** | 体积超限 → 逐级降 JPEG 质量，降到下限仍超则如实报修不了 |
| `edge_clean` | **L3** | 边缘脏的原因不明（水印？主体被裁切？）→ 交人 |

## 照抄

```bash
python run.py --product examples/product_fullset.json --only 1 --dry-run
python run.py --product examples/product_fullset.json --only 1
```

```text
# 只挪主体位置（免费：生成底被复用，不会重新调模型）：
python run.py --product examples/product_fullset.json --redo 1 --layer placement
```

> 七格**共有**的规矩（齐套怎么算 / 主体为什么只有一份 / 抠图为什么提前 / 导出阈值 / 要签什么字）在 [索引](README.md) 里 —— 那些话每张卡都一样，所以只写一遍。
