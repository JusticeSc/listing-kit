"""Throwaway R2.2 actual-UI smoke, isolated headless Chrome and fake upstreams."""
from __future__ import annotations
import hashlib
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from tools.v2_test_server import start
from src.providers.v2_fake_image import FakeImageProvider

OUT = ROOT / 'evals/product-v2/refactor'
FIXTURE = OUT / 'r21-assets-20261001-1445/headless-downloads/project.zip'
INIT = """window.__prototypeTrail=[];
document.addEventListener('click',e=>{const n=e.target.closest('button,[role=tab],summary');if(n)window.__prototypeTrail.push({kind:'click',id:n.id,text:n.innerText.slice(0,160),t:performance.now()});},true);
window.addEventListener('DOMContentLoaded',()=>import('/harness/workbench-prototype.js').catch(e=>{window.__prototypeLoadError=e.message;}));"""
DB = """async()=>{const result={};for(const info of await indexedDB.databases()){const db=await new Promise((ok,no)=>{const r=indexedDB.open(info.name);r.onsuccess=()=>ok(r.result);r.onerror=()=>no(r.error);});const stores={};for(const name of db.objectStoreNames)stores[name]=await new Promise((ok,no)=>{const r=db.transaction(name,'readonly').objectStore(name).getAll();r.onsuccess=()=>ok(r.result.map(v=>JSON.parse(JSON.stringify(v,(k,x)=>x instanceof Blob?{blob_size:x.size,blob_type:x.type}:x))));r.onerror=()=>no(r.error);});result[info.name]=stores;db.close();}return result;}"""

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def run():
    mode = 'ok'
    server, base = start()
    server.image_provider_factory = lambda: FakeImageProvider(scenario=mode, size=1200)
    evidence = {'evidence_kind':'NOT-AUTHORITY','schema':'amz-prototype-smoke/v1',
                'started_at':datetime.now(timezone.utc).isoformat(),
                'upstreams':'all four explicitly fake; genuine product handler and IndexedDB',
                'observations':[], 'responsive':[], 'native_zoom':[], 'keyboard':[]}
    requests, errors, blocked = [], [], []
    try:
        with tempfile.TemporaryDirectory(prefix='r22-prototype-owned-chrome-') as profile, sync_playwright() as p:
            context = p.chromium.launch_persistent_context(profile, executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe', headless=True, viewport={'width':1440,'height':900}, device_scale_factor=1)
            context.add_init_script(INIT)
            def route(r):
                url = r.request.url
                if url.startswith(base+'/') or url.startswith(('data:','blob:','chrome:')):
                    r.continue_()
                else:
                    blocked.append(url)
                    r.abort()
            context.route('**/*', route)
            context.on('request', lambda r: requests.append({'url':r.url,'method':r.method}))
            page = context.new_page()
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(base+'/?prototype=workbench')
            page.locator('#create-project:not([disabled])').wait_for()
            page.locator('body[data-prototype-ready="true"]').wait_for()
            blank = page.evaluate(DB)
            assert all(not rows for stores in blank.values() for rows in stores.values())
            evidence['browser'] = {'version':context.new_cdp_session(page).send('Browser.getVersion')['product'],'user_agent':page.evaluate('navigator.userAgent'),'headless':True,'fresh_profile':True,'profile_kind':'independent temporary persistent context, not incognito'}
            page.locator('#import-file').set_input_files(str(FIXTURE))
            page.locator('#project-list button[data-action="open"]').click()
            page.locator('#project-view:not([hidden])').wait_for()

            def store(): return page.evaluate(DB)['amz-listing-kit-v2']
            def submits(): return sum(r['method']=='POST' and r['url'].endswith('/api/v2/images/submit') for r in requests)
            def dismiss():
                if page.locator('dialog[open]').count():
                    page.keyboard.press('Escape')
                    page.locator('dialog[open]').wait_for(state='hidden')
            def compare(shot):
                dismiss()
                page.locator('[data-stage-nav="review"]').click()
                page.locator(f'.review-card[data-shot-id="{shot}"] button').first.click()
                page.locator('#compare-panel:not([hidden])').wait_for()
            def rework(shot):
                compare(shot)
                page.locator('#rework-open').click()
                page.locator('dialog[open] #rework-direction').wait_for()
                page.locator('#rework-direction').fill('只调整背景留白，商品外观与已确认文案保持不变。')
                page.locator('#rework-preview').click()
                page.locator('#rework-submit:not([disabled])').wait_for()
                page.locator('#rework-submit').click()

            before = store()
            rework('shot_infographic_benefits')
            page.wait_for_function("document.querySelector('.review-card[data-shot-id=shot_infographic_benefits]').innerText.includes('候选 2 个')")
            after = store()
            unchanged = lambda rows: [d for d in rows['documents'] if d['payload'].get('shot_id') and d['payload']['shot_id']!='shot_infographic_benefits']
            selections = lambda rows: [d for d in rows['documents'] if d['kind']=='selection']
            assert unchanged(before)==unchanged(after) and selections(before)==selections(after)
            evidence['observations'].append({'scenario':'single-shot rework','unrelated_records_equal':True,'selection_records_equal':True,'two_shots_each_two_candidates':True})

            mode = 'status_unknown'
            rework('shot_scene_lifestyle')
            page.locator('#attempt-list [data-shot-id="shot_scene_lifestyle"][data-attempt-state="unknown"]').wait_for(state='attached')
            mode = 'submit_unknown'
            rework('shot_detail_material')
            page.locator('#attempt-list [data-shot-id="shot_detail_material"][data-attempt-state="unknown"]').wait_for(state='attached')
            dismiss()
            page.locator('[data-stage-nav="generate"]').click()
            no_task = page.locator('#attempt-list [data-shot-id="shot_detail_material"]')
            assert no_task.get_by_role('button',name='核对任务',exact=True).count()==0
            assert '不能直接查询' in no_task.locator('.prototype-recovery').inner_text()
            evidence['observations'].append({'scenario':'no-task Unknown','query_absent':True,'old_candidate_retained':len([d for d in store()['documents'] if d['kind']=='candidate' and d['payload']['shot_id']=='shot_detail_material'])==1})
            count_before = submits()
            mode = 'status_unknown'
            known = page.locator('#attempt-list [data-shot-id="shot_scene_lifestyle"]')
            known.get_by_role('button',name='核对任务',exact=True).click()
            known.locator('.attempt-actions button').first.wait_for()
            page.wait_for_function("!document.querySelector('#attempt-list [data-shot-id=shot_scene_lifestyle] .attempt-actions button').disabled")
            assert known.get_attribute('data-attempt-state')=='unknown' and submits()==count_before
            evidence['observations'].append({'scenario':'still-Unknown reconciliation','state':'unknown','submits_before':count_before,'submits_after':submits()})

            compare('shot_main_clean')
            page.locator('#rework-open').click()
            page.locator('dialog[open]').wait_for()
            for _ in range(16):
                page.keyboard.press('Tab')
                focus = page.evaluate("()=>({id:document.activeElement.id,tag:document.activeElement.tagName,document_has_focus:document.hasFocus(),dialog_modal:Boolean(document.querySelector('dialog:modal')),in_modal:Boolean(document.activeElement.closest('dialog[open]')),box:document.activeElement.getBoundingClientRect().toJSON(),outline:getComputedStyle(document.activeElement).outlineStyle})")
                evidence['keyboard'].append(focus)
                assert (focus['in_modal'] and focus['outline']!='none') or (focus['tag']=='BODY' and not focus['document_has_focus'] and focus['dialog_modal'])
            if not page.evaluate('document.hasFocus()'):
                page.keyboard.press('Shift+Tab')
            assert page.evaluate("Boolean(document.activeElement.closest('dialog[open]'))")
            dismiss()
            assert page.evaluate('document.activeElement.id')=='rework-open'
            assert page.locator('#compare-panel').is_visible()
            evidence['observations'].append({'scenario':'native modal Tab enclosure and Escape return','steps':16,'focus':'rework-open','comparison_retained':True})

            page.locator('[data-stage-nav="understand"]').click()
            page.locator('#slots-toggle').click()
            row = page.locator('#slot-list [data-slot-id="signature_features"]')
            row.get_by_role('button',name='修改',exact=True).click()
            old_value = row.locator('#slot-editor-value').input_value()
            before_fact = store()
            row.locator('#slot-editor-value').fill(old_value+'\n保持参考图中的杯盖结构。')
            row.get_by_role('button',name='保存',exact=True).click()
            page.wait_for_function("document.querySelectorAll('#prompt-list [data-prompt-state=stale]').length===4")
            impact = page.locator('#prototype-fact-impact').inner_text()
            after_fact = store()
            assert selections(before_fact)==selections(after_fact)
            assert [d for d in before_fact['documents'] if d['kind']=='candidate']==[d for d in after_fact['documents'] if d['kind']=='candidate']
            assert submits()==count_before
            page.get_by_role('button',name='检查受影响图片与发送摘要',exact=True).click()
            assert page.locator('[data-stage-panel="generate"]').is_visible()
            evidence['observations'].append({'scenario':'fact edit impact and continued workflow','affected_prompts':4,'impact':impact,'candidates_and_selections_preserved':True,'no_automatic_submit':True})

            def set_zoom(factor):
                settings = context.new_page()
                try:
                    settings.goto('chrome://settings/appearance')
                    settings.locator('settings-ui').wait_for()
                    selector = None
                    for candidate in settings.locator('select').all():
                        option = candidate.locator('option[value="2"]')
                        if option.count() and option.inner_text().strip()=='200%':
                            selector = candidate
                            break
                    assert selector is not None, 'Actual Chrome zoom select missing'
                    selector.select_option(str(factor))
                    return {'value':selector.input_value(),'label':selector.locator('option:checked').inner_text().strip()}
                finally:
                    settings.close()
                    page.bring_to_front()
            def measure(stage):
                if stage=='review': compare('shot_main_clean')
                else: page.locator(f'[data-stage-nav="{stage}"]').click()
                return page.evaluate("""stage=>({stage,width:innerWidth,height:innerHeight,dpr:devicePixelRatio,visual_scale:visualViewport.scale,scroll_width:document.documentElement.scrollWidth,css_zoom:getComputedStyle(document.body).zoom,css_transform:getComputedStyle(document.body).transform,images:[...document.querySelectorAll(stage==='review'?'#prototype-image-plane img':stage==='understand'?'#prototype-source-images img':'.prototype-recovery')].filter(e=>e.getClientRects().length).map(e=>({alt:e.alt||null,box:e.getBoundingClientRect().toJSON()}))})""",stage)
            for width,height in [(1440,900),(1366,768)]:
                set_zoom(1)
                page.set_viewport_size({'width':width,'height':height})
                page.wait_for_function('w=>Math.abs(innerWidth-w)<=2',arg=width)
                for factor in [1.25,2]:
                    settings = set_zoom(factor)
                    page.wait_for_function('(arg)=>Math.abs(innerWidth-arg.w/arg.z)<=2',arg={'w':width,'z':factor})
                    for stage in ['understand','review','generate']:
                        metric = {'base_width':width,'native_zoom':factor,'settings':settings,**measure(stage)}
                        assert metric['scroll_width']<=metric['width']+1 and metric['css_zoom']=='1' and metric['css_transform']=='none'
                        evidence['native_zoom'].append(metric)
                        if width==1366 and factor==2 and stage=='review': page.screenshot(path=str(OUT/'prototype-compare-native200-20261002.png'))
            set_zoom(1)
            for width,height in [(1440,900),(1366,768),(390,844)]:
                page.set_viewport_size({'width':width,'height':height})
                page.wait_for_function('w=>Math.abs(innerWidth-w)<=2',arg=width)
                for stage in ['understand','review','generate']:
                    metric = {'requested_width':width,**measure(stage)}
                    assert metric['scroll_width']<=metric['width']+1
                    evidence['responsive'].append(metric)
                    if stage=='review' and width in (1440,390): page.screenshot(path=str(OUT/f'prototype-compare-{width}-20261002.png'))
                    if stage=='understand' and width==1440: page.screenshot(path=str(OUT/'prototype-facts-1440-20261002.png'))
            before_refresh = store()
            count_before_refresh = submits()
            page.reload()
            page.locator('body[data-prototype-ready="true"]').wait_for()
            page.locator('#project-view:not([hidden])').wait_for()
            assert store()==before_refresh and submits()==count_before_refresh
            evidence['observations'].append({'scenario':'refresh','records_unchanged':True,'submits_before':count_before_refresh,'submits_after':submits(),'snapshot_sha256':digest(before_refresh)})
            evidence['console_page_errors']=errors
            evidence['blocked_requests']=blocked
            evidence['requests']=requests
            evidence['trail']=page.evaluate('window.__prototypeTrail')
            assert not errors and not blocked
            evidence['result']='PASS'
            context.close()
    except Exception as error:
        evidence['result']='FAIL'
        evidence['failure']={'type':type(error).__name__,'message':str(error)}
        raise
    finally:
        evidence['finished_at']=datetime.now(timezone.utc).isoformat()
        (OUT/'prototype-smoke-20261002.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        server.shutdown()
        server.server_close()
        print(json.dumps({'result':evidence.get('result'),'native_zoom_surfaces':len(evidence['native_zoom']),'responsive_surfaces':len(evidence['responsive']),'keyboard_steps':len(evidence['keyboard']),'evidence':'evals/product-v2/refactor/prototype-smoke-20261002.json'},ensure_ascii=False))

if __name__=='__main__':
    run()
