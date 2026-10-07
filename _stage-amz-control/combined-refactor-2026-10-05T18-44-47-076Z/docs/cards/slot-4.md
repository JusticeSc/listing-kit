<!-- ⚠️ 由 tools/gen_slot_cards.py 从 config/slots.yaml 生成，不要直接改这里。 -->
<!-- 改这一格 → 改 config/slots.yaml → 跑 `python tools/gen_slot_cards.py`；一致性由 `python tools/check_docs.py` 守卫。 -->

# 坑位 4 · 场景使用

**一句话**：模型只画空背景 → 主体确定性贴入（★唯一调模型）

| 属性 | 值 |
|---|---|
| 渲染器 | `gen_bg_paste`（生成背景 + 贴主体） |
| 调生成模型 | **是**（全表 1/7 格调模型） |
| 背景 | `generated` —— **模型生成的空背景**（全表唯一一处；主体事后确定性贴入） |
| 文字 | `none` |
| 平台强制项 | 否 |
| 校验强度 | `loose`（实际跑 2 项） |
| 主体占比 | 46%（出图参数与校验判据是**同一个数**） |

## 要什么 —— 缺任何一项就**跳过这一格**（不报错、不凑图）

| 素材 | 是什么 | 缺了会怎样 |
|---|---|---|
| `front` | 正面原片 | 跳过这一格 |

## 不做的事

- **不叠字**：本格的平台档位要求画面里没有任何文字。

## 出错走哪一级（从便宜往贵试，**不许跳级**）

| 校验项 | 走 | 为什么 |
|---|---|---|
| `aspect_ratio` | **L0** | 非 1:1 → 居中补白到正方形（补白，不裁切：绝不切掉主体） |
| `long_side_px` | **L0** | 分辨率不足 → LANCZOS 放大到目标边长 |

## 照抄

```bash
python run.py --product examples/product_fullset.json --only 4 --dry-run
python run.py --product examples/product_fullset.json --only 4
```

```text
# 只挪主体位置（免费：生成底被复用，不会重新调模型）：
python run.py --product examples/product_fullset.json --redo 4 --layer placement
```

> 七格**共有**的规矩（齐套怎么算 / 主体为什么只有一份 / 抠图为什么提前 / 导出阈值 / 要签什么字）在 [索引](README.md) 里 —— 那些话每张卡都一样，所以只写一遍。
