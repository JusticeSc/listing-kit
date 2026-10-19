"""Temporary offline diagnostic: preserve navigation failure state without retries."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT))
import v2_stage_nav
import verify_v2_3_6_prompt_manual_edit as verifier

original_goto = v2_stage_nav.goto

def diagnose_goto(page, stage_id, timeout=20_000):
    try:
        return original_goto(page, stage_id, timeout)
    except Exception:
        snapshot = page.evaluate("""() => ({
          url: location.href,
          homeVisible: !!document.getElementById('home-view')?.getClientRects().length,
          projectVisible: !!document.getElementById('project-view')?.getClientRects().length,
          body: document.body.innerText.slice(0, 6000),
          session: window.__v2SessionProbe ? {
            generation: window.__v2SessionProbe.generation,
            projectId: window.__v2SessionProbe.projectId
          } : null,
          nav: [...document.querySelectorAll('[data-stage-nav]')].map(n => ({
            stage: n.dataset.stageNav, hidden: !n.getClientRects().length, disabled: n.disabled
          }))
        })""")
        print('RELOAD_DIAG ' + json.dumps(snapshot, ensure_ascii=False), flush=True)
        page.screenshot(path=str(Path(__file__).with_name('manual-reload-failure.png')), full_page=True)
        raise

v2_stage_nav.goto = diagnose_goto
sys.exit(verifier.main())
