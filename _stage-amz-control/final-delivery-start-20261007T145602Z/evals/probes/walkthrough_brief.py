# -*- coding: utf-8 -*-
"""走查说明的落点判据（单页版）：说明里让陌生人看的每一句，页面上真的有落点吗。

用法
----
    python evals/probes/walkthrough_brief.py              # 起真进程、真 HTTP，检查说明
    python evals/probes/walkthrough_brief.py --self-test  # 五处改坏都必须被抓到

它起一个真进程，用真 HTTP 取回**单页与它的渲染代码**（/、/static/workbench.js、
/static/mock-service.js），然后验四件事：

1. 落点：说明里每一对「」里的句子，都能在真实服务返回的单页或渲染代码里逐字找到；
2. 方向：标注「做过之后才出现」的句子，不许出现在初始 HTML 里 —— 否则它只是页面上本来就
   有的一句话，分不清「做过一遍」和「什么都没做」；
3. 术语：说明里不许出现命令行 / JSON / 字段名 / 对象名这类开发者词汇（「」里引用的页面
   原文不受此限，因为那是被测者会真的看到的字）；
4. 标记完整性：八个步骤里，每一步至少有一条「你应该看到」；「点一下」的按钮名必须在渲染
   代码里找得到。

**边界（必须如实登记）**：单页的状态是浏览器里跑出来的，本判据**不能**证明「点完之后真的
渲染出这句话」，它只证明「这句话不在初始页面上、并且确实来自这份页面的渲染代码」。逐步骤
的渲染证据来自一次真人或代理按说明走的预演记录（见 D2.R2a 证据文件），不能由本判据替代。

判据红了先怀疑说明写错，不要先改页面：这份说明是给陌生人的合同。
"""

from __future__ import annotations

import argparse
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:  # Windows 控制台默认是 GBK，中文与符号会打不出来
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[2]
BRIEF = ROOT / 'evals/product-demo/d2-r2/walkthrough-brief.md'
FIXTURE = 'demo/fixture/aster-01'

STEP_RE = re.compile(r'^###\s*第\s*([0-9]+)\s*步\s*·\s*(.+?)\s*$', re.M)
QUOTED_RE = re.compile(r'「([^」]+)」')
PLACEHOLDER_RE = re.compile(r'\{[^}]*\}')
MARK_NOW = '（现在就有）'
MARK_AFTER = '（做过之后才出现）'
BANNED = ('命令行', '终端', 'JSON', 'API', '字段', '数据库', 'SQLite', '端口', '进程',
          '接口', '端点', '状态机', 'provider', 'Attempt', 'Candidate', 'Prompt', 'Shot',
          'Task', 'PlanVersion', '对象名', 'npm', 'Python', '脚本', '哈希', '跑一次命令')


def norm(value: str) -> str:
    """去空白后比较：中文句子里的换行只是排版，不是内容差异。"""
    return ''.join(str(value or '').split())


def landing(phrase: str) -> str:
    return norm(PLACEHOLDER_RE.sub('', phrase))


def parse_brief(text: str) -> dict:
    steps = []
    marks = [(m.start(), m.group(1), m.group(2)) for m in STEP_RE.finditer(text)]
    for index, (start, number, title) in enumerate(marks):
        end = marks[index + 1][0] if index + 1 < len(marks) else len(text)
        block = text[start:end]
        tail = re.search(r'^## ', block[len('### '):], re.M)
        if tail:
            block = block[:len('### ') + tail.start()]
        initial, result, actions, quoted = [], [], [], []
        for line in block.splitlines():
            found = QUOTED_RE.findall(line)
            if not found:
                continue
            quoted += found
            if line.strip().startswith('- 点一下'):
                actions.append(found[0])
            if MARK_NOW in line:
                initial += found
            if MARK_AFTER in line:
                result += found
        steps.append({'n': int(number), 'title': title.strip(), 'initial': initial,
                      'result': result, 'actions': actions, 'quoted': quoted})
    outside = QUOTED_RE.sub(' ', text)
    return {'steps': steps, 'outside': outside}


def check(brief_text: str, bundle: dict) -> list:
    parsed = parse_brief(brief_text)
    problems = []
    served = norm(bundle['html'] + bundle['js'] + bundle['mock'])
    html_only = norm(bundle['html'])
    js_only = norm(bundle['js'])

    for term in BANNED:
        if term in parsed['outside']:
            problems.append('说明正文里出现开发者词汇「%s」—— 说明是给陌生人的，不是给开发的' % term)

    if not parsed['steps']:
        problems.append('说明里一个编号步骤都没有')
    for step in parsed['steps']:
        if not step['quoted']:
            problems.append('第 %d 步一句要看的都不写 —— 空标记会静默通过' % step['n'])
        if not (step['initial'] or step['result']):
            problems.append('第 %d 步没有「你应该看到」的标记 —— 无法判断这一步有没有落点' % step['n'])
        for phrase in step['quoted']:
            if landing(phrase) not in served:
                problems.append('第 %d 步：「%s」在服务返回的单页与渲染代码里都找不到' % (step['n'], phrase))
        for phrase in step['result']:
            if landing(phrase) in html_only:
                problems.append('第 %d 步：「%s」写成「做过之后才出现」，但初始 HTML 里就有' % (step['n'], phrase))
        for button in step['actions']:
            if landing(button) not in js_only and landing(button) not in html_only:
                problems.append('第 %d 步：按钮「%s」在渲染代码里找不到' % (step['n'], button))
    return problems


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def http_get(url: str, timeout: float = 5.0) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read().decode('utf-8', 'replace')


def start_server():
    port = free_port()
    proc = subprocess.Popen(
        [sys.executable, 'app/server.py', '--offline-fixture', FIXTURE, '--port', str(port)],
        cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = 'http://127.0.0.1:%d' % port
    for _ in range(80):
        try:
            if '阶段：待确认资料' in http_get(base + '/', timeout=1.0):
                return proc, base
        except Exception:
            pass
        if proc.poll() is not None:
            raise SystemExit(2)
        time.sleep(0.25)
    proc.kill()
    raise SystemExit(2)


def fetch_bundle(base: str) -> dict:
    return {
        'html': http_get(base + '/'),
        'js': http_get(base + '/static/workbench.js'),
        'mock': http_get(base + '/static/mock-service.js'),
    }


def report(problems: list, parsed: dict) -> int:
    steps = parsed['steps']
    phrases = sum(len(s['quoted']) for s in steps)
    results = sum(len(s['result']) for s in steps)
    actions = sum(len(s['actions']) for s in steps)
    print('走查说明的落点判据（单页版 · 真进程 · 真 HTTP · 零付费）')
    print('=' * 72)
    print('  说明：%s' % BRIEF.relative_to(ROOT).as_posix())
    print('  步骤：%d 步 · 要看的句子 %d 条（其中「做过之后才出现」%d 条）· 要点的按钮 %d 处'
          % (len(steps), phrases, results, actions))
    for step in steps:
        print('  第 %d 步 %s：看 %d 条，按钮 %d 处'
              % (step['n'], step['title'], len(step['quoted']), len(step['actions'])))
    if problems:
        print()
        for item in problems:
            print('  [x] ' + item)
        print()
        print('结果：没通过（%d 条）—— 说明里写了页面上没有的东西，或动作结果本来就存在' % len(problems))
        return 1
    print()
    print('结果：全过（退出码 0）—— 每一句都有落点，「做过之后才出现」的话初始页面上都没有')
    print('边界：本判据不证明「点完之后真的渲染出这句话」；那一条由按说明走的预演记录承担。')
    return 0


def self_test() -> int:
    proc, base = start_server()
    try:
        bundle = fetch_bundle(base)
        brief = BRIEF.read_text(encoding='utf-8')
        cases = [
            ('说明原样', brief, None),
            ('「现在就有」改成页面上没有的话',
             brief.replace('「离线 Mock · 不调用模型」', '「这个字符串绝不存在」'), '找不到'),
            ('把初始页面上就有的字写成「做过之后才出现」',
             brief.replace('（做过之后才出现）「阶段：方案可调整」', '（做过之后才出现）「重置演示」'), '初始 HTML 里就有'),
            ('说明正文里混进开发者词汇',
             brief.replace('## 一步步走', '## 一步步走（先用命令行确认）'), '开发者词汇'),
            ('某一步把「你应该看到」删掉',
             brief.replace('- 你应该看到：（做过之后才出现）「阶段：逐图审核」「待检查」', '- 这一步不用看什么'),
             '没有「你应该看到」的标记'),
        ]
        bad = 0
        print('走查说明落点判据的反向对照（%d 向）' % len(cases))
        for label, text, expect in cases:
            problems = check(text, bundle)
            if expect is None:
                ok = not problems
                detail = '全过' if ok else ('%d 条问题：%s' % (len(problems), problems[0]))
            else:
                hit = [p for p in problems if expect in p]
                ok = bool(hit)
                detail = hit[0] if hit else ('没抓到（得到 %s）' % (problems or '零条问题'))
            print('  [%s] %s：%s' % ('OK  ' if ok else '未过', label, detail))
            bad += 0 if ok else 1
        print()
        print('反向对照：%d/%d 与预期一致。' % (len(cases) - bad, len(cases)))
        return 1 if bad else 0
    finally:
        proc.kill()
        proc.wait(timeout=10)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='走查说明的落点判据（单页版）')
    parser.add_argument('--brief', default=str(BRIEF))
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    text = Path(args.brief).read_text(encoding='utf-8')
    proc, base = start_server()
    try:
        bundle = fetch_bundle(base)
    finally:
        proc.kill()
        proc.wait(timeout=10)
    return report(check(text, bundle), parse_brief(text))


if __name__ == '__main__':
    raise SystemExit(main())
