#!/usr/bin/env python
"""V2.UI.2 六阶段工作台的验证导航助手。

为什么需要单独一处：V2.UI.2 起工作台按「资料—理解—方案—生成—审核返工—交付」分阶段切换，
同一时刻只有一个阶段面板可见（`ui/stage-shell.js`）。任何验证器在操作某个阶段的控件前，
都必须先切到那个阶段；否则 `page.click` 会一直等一个被隐藏的元素。

纪律：
  - 阶段未解锁时**直接报错**，不回退成「点别的」「跳过」或降低断言——那会把真实缺陷洗成通过。
  - 只点阶段条，不直接改 DOM（隐藏/显示面板），保证验证走的是用户真实路径。
"""
from __future__ import annotations

STAGE_IDS = ("intake", "understand", "plan", "generate", "review", "deliver")
STAGE_LABELS = {"intake": "资料", "understand": "理解", "plan": "方案",
                "generate": "生成", "review": "审核返工", "deliver": "交付"}


def current_stage(page) -> str:
    """当前可见阶段 id（没有可见阶段时返回空串）。"""

    panels = page.evaluate(
        """() => [...document.querySelectorAll("#stage-panels [data-stage-panel]")]
          .filter((node) => !node.hidden).map((node) => node.dataset.stagePanel)""")
    return panels[0] if panels else ""


def goto(page, stage_id: str, timeout: int = 20_000) -> None:
    """切到目标阶段；已是目标阶段时什么也不做。"""

    if stage_id not in STAGE_IDS:
        raise AssertionError(f"未知阶段 id：{stage_id}")
    if current_stage(page) == stage_id:
        return
    button = page.locator(f'#stage-nav [data-stage-nav="{stage_id}"]')
    button.wait_for(state="visible", timeout=timeout)
    if button.is_disabled():
        raise AssertionError(
            f"阶段「{STAGE_LABELS[stage_id]}」当前不可达（阶段条仍锁定）；"
            f"当前阶段是「{STAGE_LABELS.get(current_stage(page), current_stage(page))}」")
    button.click()
    page.wait_for_selector(
        f'#stage-panels [data-stage-panel="{stage_id}"]:not([hidden])', timeout=timeout)


def probe(page) -> dict:
    """阶段条快照：每个阶段的禁用/当前/完成/锁定与摘要文案。"""

    return page.evaluate(
        """() => {
          const nav = document.getElementById("stage-nav");
          const buttons = [...nav.querySelectorAll("[data-stage-nav]")].map((node) => ({
            id: node.dataset.stageNav, disabled: node.disabled,
            current: node.classList.contains("is-current"),
            complete: node.classList.contains("is-complete"),
            locked: node.classList.contains("is-locked"),
          }));
          const summary = document.getElementById("stage-summary");
          return { buttons: buttons, summary: summary ? summary.textContent.trim() : "" };
        }""")


def reveal(page, selector: str, timeout: int = 20_000) -> None:
    """展开包住 selector 的 <details>（已展开时不动它）。

    渐进披露是产品合同的一部分（工程信息默认收进「详情」）；验证器要读里面的内容时，
    必须先像用户一样点开它，而不是直接读隐藏文本。
    """

    node = page.locator(selector).first
    if node.count() == 0:
        raise AssertionError(f"找不到元素：{selector}")
    if node.is_visible():
        return
    summary = page.locator(f"details:has({selector}) > summary").first
    if summary.count() == 0:
        raise AssertionError(f"{selector} 当前不可见，且找不到包住它的 <details> 折叠区")
    summary.click()
    node.wait_for(state="visible", timeout=timeout)
