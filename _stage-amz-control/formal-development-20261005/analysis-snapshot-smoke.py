from pathlib import Path
import json
import sys
import tempfile
from playwright.sync_api import sync_playwright, expect

ARTIFACTS = Path(__file__).parent
REF = ARTIFACTS.parents[1] / '_working/amz-listing-kit-product-v2/walkthrough-assets/food/honey-jar-antique.jpg'
label = sys.argv[1] if len(sys.argv) > 1 else 'before'
with tempfile.TemporaryDirectory(prefix='amz-analysis-snapshot-') as profile:
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(profile, channel='chrome', headless=True,
            viewport={'width':1440,'height':900})
        try:
            page = context.pages[0]
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto('http://127.0.0.1:53436/', wait_until='domcontentloaded')
            expect(page.locator('#create-project')).to_be_enabled()
            page.fill('#new-project-name', '分析原快照隔离-'+label)
            page.click('#create-project')
            expect(page.locator('#project-view')).to_be_visible()
            page.set_input_files('#ref-file', str(REF))
            expect(page.locator('#ref-list .ref-row')).to_have_count(1)
            page.fill('#intake-name', '旧资料蜂蜜罐')
            page.fill('#intake-description', '旧资料：透明玻璃罐，金属盖。')
            page.click('#intake-save')
            expect(page.locator('#analyze-run')).to_be_enabled()
            held = []
            def hold(route):
                held.append(route)
                page.evaluate('globalThis.__analysisRequestHeld=true')
            page.route('**/api/v2/semantic/analyze', hold)
            page.click('#analyze-run')
            expect(page.locator('#analyze-run')).to_be_disabled()
            page.wait_for_function('()=>globalThis.__analysisRequestHeld===true')
            assert len(held) == 1
            request = held[0].request.post_data_json
            page.fill('#intake-name', '新资料陶瓷杯')
            page.fill('#intake-description', '新资料：陶瓷杯，不是玻璃罐。')
            page.click('#intake-save')
            response = held[0].fetch()
            held[0].fulfill(response=response)
            expect(page.locator('#analyze-run')).to_be_enabled()
            records = page.evaluate('''async () => {
                const {openStorage}=await import('/storage/index.js');
                const opened=await openStorage();
                try { const p=await opened.repository.pointer.get();
                    return {project:p, documents:await opened.repository.documents.listAll(p.project_id)};
                } finally {opened.db.close();}
            }''')
            result = {'label':label, 'request_product_name':request['product_name'],
                'current_name':page.locator('#intake-name').input_value(),
                'result':page.locator('#analyze-result').inner_text(),
                'error':page.locator('#analyze-error').inner_text(),
                'records':records, 'page_errors':errors,
                'boundary':'Isolated headless Chrome; real local gateway fake semantic only; no paid calls'}
            (ARTIFACTS / ('analysis-snapshot-'+label+'.json')).write_text(
                json.dumps(result,ensure_ascii=False,indent=2), encoding='utf-8')
            page.screenshot(path=str(ARTIFACTS/('analysis-snapshot-'+label+'.png')),full_page=True)
            print(json.dumps({'request_name':result['request_product_name'], 'current_name':result['current_name'],
                'slots':[{ 'id':d['document_id'],'status':d['payload'].get('status'),'value':d['payload'].get('value') }
                    for d in records['documents'] if d['kind']=='fact_slot'],
                'error':result['error'],'page_errors':errors},ensure_ascii=False))
        finally:
            context.close()
