# b0c9c907f875b918 / raw.png

事实卡：`demo-tumbler-aster-01` v2026-09-25.1 · 量测实现 cylinder-v1 · 来源 demo_fixture

综合判定：**hard_fail**（机器判据 7 条；纯人工事实 F8，机器不改写）

图片：E:\workbuddy_workspace\2026-09-20-16-38-19\amz-listing-kit\evals\product-demo\first-round\attempts\b0c9c907f875b918\raw.png

| 事实 | 机器判定 | 项 | 实测 | 声明/档位 |
|---|---|---|---|---|
| F1 | hard_fail | F1 高宽比（高/宽） | 1.4 | 3.1 |
| F2 | hard_fail | F2 上段占杯体 | 0.3235 | 0.72 |
| F3 | hard_fail | F3 下段占杯体 | 0.6765 | 0.28 |
|  |  | F3 防滑套筋条数 | 3 条 | 3 条 |
| F4 | pass | F4 杯盖占整器高 | 0.1281 | 0.2 |
| F4 | 人工 | 恰好两级同心台阶 | —— | 不由机器判定 |
| F4 | 人工 | 盖顶无开口 | —— | 不由机器判定 |
| F4 | 人工 | 无第二只盖子或翻盖 | —— | 不由机器判定 |
| F5 | pass | F5 独立装饰环段数 | 1 段 | 1 段 |
|  |  | F5 装饰环占整器高 | 0.0142 | 0.0 |
|  |  | F5 装饰环上沿位置（占整器高） | 0.1281 | 0.0 |
| F6 | manual | F6 底部轮廓离散（占主体宽） | 0.0672 | 0.0 |
|  |  | F6 检出底部防滑圈 | 1 | 1 |
| F7 | hard_fail | F7 杯身最大凸出（占主体宽） | 1.3899 | 0.0 |
|  |  | F7 主体外像素占比 | 0.1554 | 0.0 |
| F8 | 人工 |  | —— | 不由机器判定 |

## 未通过的项

- aspect_h_over_w = 1.4 → hard_fail（超出人工档：{"min": 2.3, "max": 3.9}）
- body_upper_share = 0.3235 → hard_fail（超出人工档：{"min": 0.5, "max": 0.88}）
- body_lower_share = 0.6765 → hard_fail（超出人工档：{"min": 0.12, "max": 0.5}）
- bottom_spread_share = 0.0672 → manual（落在人工档：{"max": 0.05}）
- body_protrusion = 1.3899 → hard_fail（超出人工档：{"max": 0.12}）
- extra_area_share = 0.1554 → hard_fail（超出人工档：{"max": 0.01}）


# 723ab2a69e19571d / raw.png

事实卡：`demo-tumbler-aster-01` v2026-09-25.1 · 量测实现 cylinder-v1 · 来源 demo_fixture

综合判定：**hard_fail**（机器判据 7 条；纯人工事实 F8，机器不改写）

图片：E:\workbuddy_workspace\2026-09-20-16-38-19\amz-listing-kit\evals\product-demo\first-round\attempts\723ab2a69e19571d\raw.png

| 事实 | 机器判定 | 项 | 实测 | 声明/档位 |
|---|---|---|---|---|
| F1 | manual | F1 高宽比（高/宽） | 2.459 | 3.1 |
| F2 | pass | F2 上段占杯体 | 0.6308 | 0.72 |
| F3 | pass | F3 下段占杯体 | 0.3692 | 0.28 |
|  |  | F3 防滑套筋条数 | 3 条 | 3 条 |
| F4 | pass | F4 杯盖占整器高 | 0.1313 | 0.2 |
| F4 | 人工 | 恰好两级同心台阶 | —— | 不由机器判定 |
| F4 | 人工 | 盖顶无开口 | —— | 不由机器判定 |
| F4 | 人工 | 无第二只盖子或翻盖 | —— | 不由机器判定 |
| F5 | pass | F5 独立装饰环段数 | 1 段 | 1 段 |
|  |  | F5 装饰环占整器高 | 0.0145 | 0.0 |
|  |  | F5 装饰环上沿位置（占整器高） | 0.1313 | 0.0 |
| F6 | pass | F6 底部轮廓离散（占主体宽） | 0.0178 | 0.0 |
|  |  | F6 检出底部防滑圈 | 1 | 1 |
| F7 | hard_fail | F7 杯身最大凸出（占主体宽） | 0.3731 | 0.0 |
|  |  | F7 主体外像素占比 | 0.3403 | 0.0 |
| F8 | 人工 |  | —— | 不由机器判定 |

## 未通过的项

- aspect_h_over_w = 2.459 → manual（落在人工档：{"min": 2.6, "max": 3.6}）
- body_protrusion = 0.3731 → hard_fail（超出人工档：{"max": 0.12}）
- extra_area_share = 0.3403 → hard_fail（超出人工档：{"max": 0.01}）


# c75a6d09d6ea00df / raw.png

事实卡：`demo-tumbler-aster-01` v2026-09-25.1 · 量测实现 cylinder-v1 · 来源 demo_fixture

综合判定：**hard_fail**（机器判据 7 条；纯人工事实 F8，机器不改写）

图片：E:\workbuddy_workspace\2026-09-20-16-38-19\amz-listing-kit\evals\product-demo\first-round\attempts\c75a6d09d6ea00df\raw.png

| 事实 | 机器判定 | 项 | 实测 | 声明/档位 |
|---|---|---|---|---|
| F1 | hard_fail | F1 高宽比（高/宽） | 1.327 | 3.1 |
| F2 | hard_fail | F2 上段占杯体 | 0.4733 | 0.72 |
| F3 | hard_fail | F3 下段占杯体 | 0.5267 | 0.28 |
|  |  | F3 防滑套筋条数 | 3 条 | 3 条 |
| F4 | pass | F4 杯盖占整器高 | 0.1264 | 0.2 |
| F4 | 人工 | 恰好两级同心台阶 | —— | 不由机器判定 |
| F4 | 人工 | 盖顶无开口 | —— | 不由机器判定 |
| F4 | 人工 | 无第二只盖子或翻盖 | —— | 不由机器判定 |
| F5 | pass | F5 独立装饰环段数 | 1 段 | 1 段 |
|  |  | F5 装饰环占整器高 | 0.0138 | 0.0 |
|  |  | F5 装饰环上沿位置（占整器高） | 0.1264 | 0.0 |
| F6 | hard_fail | F6 底部轮廓离散（占主体宽） | 0.1028 | 0.0 |
|  |  | F6 检出底部防滑圈 | 1 | 1 |
| F7 | hard_fail | F7 杯身最大凸出（占主体宽） | 1.4388 | 0.0 |
|  |  | F7 主体外像素占比 | 0.1329 | 0.0 |
| F8 | 人工 |  | —— | 不由机器判定 |

## 未通过的项

- aspect_h_over_w = 1.327 → hard_fail（超出人工档：{"min": 2.3, "max": 3.9}）
- body_upper_share = 0.4733 → hard_fail（超出人工档：{"min": 0.5, "max": 0.88}）
- body_lower_share = 0.5267 → hard_fail（超出人工档：{"min": 0.12, "max": 0.5}）
- bottom_spread_share = 0.1028 → hard_fail（超出人工档：{"max": 0.08}）
- body_protrusion = 1.4388 → hard_fail（超出人工档：{"max": 0.12}）
- extra_area_share = 0.1329 → hard_fail（超出人工档：{"max": 0.01}）


# 45ef384cb14bafbe / raw.png

事实卡：`demo-tumbler-aster-01` v2026-09-25.1 · 量测实现 cylinder-v1 · 来源 demo_fixture

综合判定：**hard_fail**（机器判据 7 条；纯人工事实 F8，机器不改写）

图片：E:\workbuddy_workspace\2026-09-20-16-38-19\amz-listing-kit\evals\product-demo\first-round\attempts\45ef384cb14bafbe\raw.png

| 事实 | 机器判定 | 项 | 实测 | 声明/档位 |
|---|---|---|---|---|
| F1 | pass | F1 高宽比（高/宽） | 3.099 | 3.1 |
| F2 | pass | F2 上段占杯体 | 0.6487 | 0.72 |
| F3 | pass | F3 下段占杯体 | 0.3513 | 0.28 |
|  |  | F3 防滑套筋条数 | 3 条 | 3 条 |
| F4 | pass | F4 杯盖占整器高 | 0.1227 | 0.2 |
| F4 | 人工 | 恰好两级同心台阶 | —— | 不由机器判定 |
| F4 | 人工 | 盖顶无开口 | —— | 不由机器判定 |
| F4 | 人工 | 无第二只盖子或翻盖 | —— | 不由机器判定 |
| F5 | pass | F5 独立装饰环段数 | 1 段 | 1 段 |
|  |  | F5 装饰环占整器高 | 0.0136 | 0.0 |
|  |  | F5 装饰环上沿位置（占整器高） | 0.1227 | 0.0 |
| F6 | pass | F6 底部轮廓离散（占主体宽） | 0.0282 | 0.0 |
|  |  | F6 检出底部防滑圈 | 1 | 1 |
| F7 | pass | F7 杯身最大凸出（占主体宽） | 0.0237 | 0.0 |
|  |  | F7 主体外像素占比 | 0.311 | 0.0 |
| F8 | 人工 |  | —— | 不由机器判定 |

## 未通过的项

- extra_area_share = 0.311 → hard_fail（超出人工档：{"max": 0.01}）
