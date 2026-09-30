#!/usr/bin/env python
"""远程持久化验证：关页重开 / 服务器重启后项目与候选字节不变；双浏览器配置隔离。

用法：
    uv run --locked python tools/verify_remote_persistence.py \
        --profile <浏览器配置目录> --label restart-b [--compare-with <a.json>]

证明：项目来自 IndexedDB（关页重开、服务器重启后仍可恢复）；候选图片字节哈希稳定；
另一个全新浏览器配置看不到该项目（天然隔离）。不证明：模型调用质量、交付 ZIP。
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402

enable_utf8()

EVIDENCE_DIR = ROOT / "evals" / "product-v2"

CANDIDATE_HASHES = """
async () => {
  const cards = [...document.querySelectorAll('#review-list .review-card')];
  const rows = [];
  for (const card of cards) {
    const shotId = card.getAttribute('data-shot-id');
    const img = card.querySelector('.review-preview img');
    if (!img || !img.src) { rows.push({ shot_id: shotId, sha256: null, note: 'no-preview' }); continue; }
    try {
      const response = await fetch(img.src);
      const buffer = await response.arrayBuffer();
      const digest = await crypto.subtle.digest('SHA-256', buffer);
      const hex = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
      rows.push({ shot_id: shotId, sha256: hex, bytes: buffer.byteLength });
    } catch (error) {
      rows.push({ shot_id: shotId, sha256: null, note: String(error).slice(0, 120) });
    }
  }
  return rows;
}
"""


def read_home(page) -> dict:
    return page.evaluate(
        """() => ({
             projects: [...document.querySelectorAll('#project-list .project-row')]
               .map((row) => (row.querySelector('.name') || row).textContent.trim()),
             empty_visible: !((document.getElementById('empty-state') || {}).hidden !== false),
             in_project: Boolean(document.getElementById('project-view')
               && !document.getElementById('project-view').hidden),
           })""")


def main() -> int:
    parser = argparse.ArgumentParser(description="远程持久化验证")
    parser.add_argument("--base", default="https://47.115.172.233:8080")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--label", default="")
    parser.add_argument("--compare-with", default="")
    parser.add_argument("--expect-projects", type=int, default=1)
    args = parser.parse_args()

    from playwright.sync_api import expect, sync_playwright  # noqa: PLC0415

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    label = f"-{args.label}" if args.label else ""
    json_path = EVIDENCE_DIR / f"remote-persistence-{stamp}{label}.json"
    txt_path = EVIDENCE_DIR / f"remote-persistence-{stamp}{label}.txt"

    console_errors: list[str] = []
    http_errors: list[str] = []
    snapshot: dict = {}

    print("=" * 72)
    print(f"远程持久化验证：{args.base} · profile={args.profile}")
    print("=" * 72)

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            args.profile, headless=True, viewport={"width": 1440, "height": 900},
            ignore_https_errors=True)
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(60_000)
        page.on("console", lambda message: console_errors.append(message.text)
                if message.type == "error" else None)
        page.on("response", lambda response: http_errors.append(
            f"{response.status} {response.url}") if response.status >= 400 else None)
        page.goto(args.base + "/", wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        home = read_home(page)
        opened_directly = home["in_project"]
        if not opened_directly and home["projects"]:
            page.click('#project-list .project-row button[data-action="open"]')
            expect(page.locator("#project-view")).to_be_visible()
            page.wait_for_timeout(600)

        page.click('#stage-nav [data-stage-nav="review"]')
        expect(page.locator('[data-stage-panel="review"]')).to_be_visible()
        page.wait_for_function(
            """() => {
                 const images = [...document.querySelectorAll(
                   '#review-list .review-card .review-preview img')];
                 return images.length > 0 && images.every((img) => img.complete && img.naturalWidth > 0);
               }""", timeout=60_000)
        cards = page.locator("#review-list .review-card").count()
        candidates = page.evaluate(CANDIDATE_HASHES)

        page.click('#stage-nav [data-stage-nav="deliver"]')
        expect(page.locator('[data-stage-panel="deliver"]')).to_be_visible()
        page.wait_for_timeout(600)
        deliver = page.evaluate(
            """() => ({ gates: [...document.querySelectorAll('#delivery-gate .gate-row')].map((row) => ({
                 shot_id: row.getAttribute('data-shot-id'),
                 state: row.getAttribute('data-selection-state') })),
                 status: (document.getElementById('deliver-status') || {}).textContent || '',
                 export_disabled: (document.getElementById('deliver-export') || {}).disabled })""")
        context.close()

        isolated_dir = tempfile.mkdtemp(prefix="amz-isolation-")
        isolated = pw.chromium.launch_persistent_context(
            isolated_dir, headless=True, viewport={"width": 1440, "height": 900},
            ignore_https_errors=True)
        try:
            fresh = isolated.pages[0] if isolated.pages else isolated.new_page()
            fresh.goto(args.base + "/", wait_until="domcontentloaded")
            fresh.wait_for_timeout(1200)
            isolated_home = read_home(fresh)
        finally:
            isolated.close()

    snapshot = {
        "finished_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z"),
        "base": args.base,
        "profile": args.profile,
        "opened_directly": opened_directly,
        "projects": home["projects"],
        "review_cards": cards,
        "candidates": candidates,
        "deliver": deliver,
        "isolated_profile_projects": isolated_home["projects"],
        "console_errors": console_errors[:20],
        "http_errors": sorted(set(http_errors))[:20],
    }
    comparison: dict = {}
    if args.compare_with:
        with Path(args.compare_with).open(encoding="utf-8") as handle:
            before = json.load(handle)
        hash_equal = ([(row["shot_id"], row["sha256"]) for row in before["candidates"]]
                      == [(row["shot_id"], row["sha256"]) for row in candidates])
        comparison = {
            "before": args.compare_with,
            "projects_equal": before["projects"] == home["projects"],
            "candidate_hashes_equal": hash_equal,
            "deliver_equal": before["deliver"]["gates"] == deliver["gates"],
        }
    snapshot["comparison"] = comparison
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    checks = [
        ("RP-01", f"该项目配置里有 {args.expect_projects} 个项目且可打开",
         len(home["projects"]) == args.expect_projects),
        ("RP-02", "关页重开后逐图候选从 IndexedDB 取回且哈希可计算",
         cards > 0 and all(row["sha256"] for row in candidates)),
        ("RP-03", "交付阶段逐图采用状态保持 current",
         len(deliver["gates"]) == cards
         and all(row["state"] == "current" for row in deliver["gates"])),
        ("RP-04", "另一个全新浏览器配置看不到该项目（天然隔离）",
         isolated_home["projects"] == []),
    ]
    if comparison:
        checks.append(("RP-05", "与上一次快照相比：项目名、候选哈希、采用状态完全一致",
                       all(comparison.values())))

    lines = [
        "amz-listing-kit Product V2 远程持久化验证（关页重开 / 服务器重启后）",
        "NOT-AUTHORITY: point-in-time verification evidence only",
        f"finished_at: {snapshot['finished_at']}",
        f"base: {args.base}",
        f"profile: {args.profile}",
        f"json: {json_path.relative_to(ROOT).as_posix()}",
        "",
        "CHECKS",
    ]
    ok = True
    for check_id, title, passed in checks:
        lines.append(f"- [{'PASS' if passed else 'FAIL'}] {check_id} {title}")
        print(f"  [{'PASS' if passed else 'FAIL'}] {check_id} {title}")
        ok = ok and passed
    lines += ["", "PROJECTS", *[f"- {name}" for name in home["projects"]]]
    lines += ["", "CANDIDATES"]
    for row in candidates:
        lines.append(f"- {row['shot_id']}: {row.get('sha256')} bytes={row.get('bytes')}")
    lines += ["", "DELIVER"]
    lines += [f"- {row['shot_id']}: {row['state']}" for row in deliver["gates"]]
    lines.append(f"- status: {deliver['status']}")
    lines.append(f"- export_disabled: {deliver['export_disabled']}")
    lines += ["", "ISOLATION",
              f"- fresh profile projects: {isolated_home['projects']}"]
    if comparison:
        lines += ["", "COMPARISON", json.dumps(comparison, ensure_ascii=False)]
    lines += ["", "ERRORS",
              f"- console_errors: {len(console_errors)}",
              f"- http_errors: {sorted(set(http_errors))[:8]}",
              "", "BOUNDARY",
              "浏览器侧持久化证据；服务器重启事实由同一时段的 CI 部署记录佐证，不由本脚本单独证明。"]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print()
    print(f"证据：{txt_path.relative_to(ROOT).as_posix()}")
    print(f"结果：{'全过' if ok else '有失败'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
