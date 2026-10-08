from pathlib import Path
import json
from playwright.sync_api import sync_playwright

result = {'evidence_kind':'NOT-AUTHORITY','hypotheses':[
    'Native Tab may visit browser chrome at the last control: BODY active and document.hasFocus false, dialog stays modal.',
    'The app may close/rebuild its dialog: open/modal flag would disappear; a minimal native dialog would not reproduce.',
    'The page may be backgrounded: document.hasFocus would be false throughout, not just at the boundary.'
]}
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
    page = browser.new_page()
    page.set_content('<button id="background">Background business action</button><dialog id="modal"><textarea id="direction"></textarea><button id="preview">Preview</button><button disabled>Submit</button></dialog>')
    page.bring_to_front()
    page.evaluate("modal.showModal();direction.focus()")
    rows=[]
    for step in range(8):
        rows.append(page.evaluate("step=>({step,id:document.activeElement.id,tag:document.activeElement.tagName,document_has_focus:document.hasFocus(),dialog_open:modal.open,dialog_modal:modal.matches(':modal')})",step))
        page.keyboard.press('Tab')
    before=page.evaluate('document.activeElement.id')
    page.evaluate('background.focus()')
    result.update({'native_tab':rows,'background_focus_blocked':page.evaluate('document.activeElement.id')==before,'browser':browser.version})
    browser.close()
path=Path(__file__).with_name('prototype-native-focus-diagnosis-20261002.json')
path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
