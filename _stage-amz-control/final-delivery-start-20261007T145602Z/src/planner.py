"""事实抽取：商品输入 → 事实（唯一合法的"事实进入系统"的入口）。

三条边界
--------
  · 这里只**搬运**事实，不**生成**事实 —— 规格数字、卖点文案都出自卖家。
    工具替卖家编一句话，就是替他做了一次虚假宣传承诺。
  · 卖点要过两份禁用词；被拦下的条目要**记进 facts 并打到日志**，
    不能静默丢弃 —— 运营必须知道哪一条没进图，以及为什么。
  · subject 只取标题前 24 字：整句标题进提示词会引入歧义。

两份禁用词，缺一不可
------------------
    forbidden_words     文案违规（"最好""绝对""全网最低"）—— 广告法 + 平台文案规则
    forbidden_on_image  图上不允许出现的东西（价格 / 二维码 / amazon / 好评…）
    叠在图上的一切文字**同时**受这两条约束，所以取并集。

    ★ forbidden_on_image 原先只在 brand.json 里躺着、没有任何代码读它 ——
      和 v1 那个"写着 no_watermark 却从未实现"的例子同型：**看起来有保护，
      实际是空的**。这里给它接上第一个消费方；M4 落地后它会再被
      gen_bg_paste 用作生成负向词（第二处消费同一份清单，不另存一份）。

不在本模块的东西
----------------
提示词素材（禁字条款、负向词表、产品排除词）**不在这里**。
它们是 `renderers/gen_bg_paste.py` 的私有资产 —— 放在唯一消费它的那个文件里，
换掉生成方式时不需要翻第二个地方。（这条是从"死字段"教训来的：
一个声明只能有一个解释者。）
"""
from __future__ import annotations

from typing import Any

# subject 截断长度：足够指代商品主体，又不至于把整句标题塞进提示词
SUBJECT_MAX_CHARS = 24


def extract_facts(product: dict[str, Any], brand: dict) -> dict[str, Any]:
    """从商品输入中抽取事实。

    输入 product 期望字段：
      upc      产品标识（过审硬要求，同时用于文件命名）
      title    商品标题
      bullets  卖点列表（原始顺序，未必是最优讲述顺序）
      specs    规格字典，如 {"容量": "500ml", "材质": "316不锈钢"}
      assets   素材路径字典，如 {"front": "input/cup_front.jpg"}
               （由 src/assets.py 消费，本模块不碰）
    """
    title = (product.get("title") or "").strip()
    bullets = [b.strip() for b in (product.get("bullets") or []) if b and b.strip()]

    # 两份清单取并集，并**分别记下命中的是哪一份规则** ——
    # 因为"为什么这条被删"在下架申诉时是要给出依据的。
    rules = ([(w, "forbidden_words") for w in (brand.get("forbidden_words") or [])]
             + [(w, "forbidden_on_image") for w in (brand.get("forbidden_on_image") or [])])
    kept, dropped = [], []
    for b in bullets:
        hit = [{"word": w, "rule": r} for w, r in rules if w and w.lower() in b.lower()]
        if hit:
            dropped.append({"text": b, "hit": hit})
        else:
            kept.append(b)

    return {
        "upc": product.get("upc") or "NOUPC",
        "title": title,
        # 主体描述：标题前段足以指代商品主体，避免整句进入提示词造成歧义
        "subject": title[:SUBJECT_MAX_CHARS] if title else "商品",
        "bullets": kept,
        "dropped_bullets": dropped,
        "specs": product.get("specs") or {},
    }
