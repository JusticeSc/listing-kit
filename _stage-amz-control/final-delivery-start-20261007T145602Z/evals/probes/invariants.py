r"""四条不变量 · 契约探针 —— 每条不变量都要有一个**能红的**判据。

为什么必须有它（这一层此前整个缺失）
----------------------------------
四条不变量写在 README 里、写在注释里，但**没有任何一条有可执行的判据**。
「改动不得破坏四条不变量」这句话在工程上等于没有约束 —— 因为"破坏"没有定义，
也就没有东西会在破坏发生时响。

更细一层的问题：**一个不会失败的断言等于装饰。** 所以本文件的每一条判据都配一个
**反向对照**（planted sample）：拿一份**故意植入违规**的样本再打一次，必须红。
只有正向（真实文件干净）不算证明 —— 万一判据本身是瞎的呢？

    A 主体只有一份         → 渲染器层零抠图调用 + 抠图只有一个生产口 + 主图不自己抠
    B 生成层看不见主体     → 由**真实请求体**推导；植入一个含图像的请求体必须被认出
    C 文字层不参与画面生成 → 背景提示词里不含任何卖点字面 / 规格数值
    D 位置 1 零模型调用     → 不是声明为 false，而是那个文件里根本没有入口

代价：全部是**静态或纯函数**判据，毫秒级、不联网、不产图、不花钱。
跑一次就知道四条不变量还在不在，而不是等出图之后用眼睛看。

为什么不做成"跑一遍管线再验"：那种探针没人愿意跑，于是它实际上没被跑。
真正需要跑管线的那部分在 `tools/verify_m3..m7.py`，以及位置 4 的冻结快照
`evals/run_golden.py`。

用法：
    python evals/probes/invariants.py        # 退出码 0 全过 / 1 有探针红
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402  （控制台编码归一：见 src/console.py）
enable_utf8()

import imagegen      # noqa: E402
import registry      # noqa: E402
import schema        # noqa: E402
from kit_config import load_brand  # noqa: E402
from renderers import gen_bg_paste as gbp  # noqa: E402

OK, BAD = "\u2713", "\u2717"
SLOT_ID = 4
PRODUCT = ROOT / "examples" / "product_fullset.json"
RENDERER_DIR = ROOT / "src" / "renderers"


class Probes:
    """收集判据结果。每条判据都要能失败 —— 失败的证明方式是**植入样本**。"""

    def __init__(self) -> None:
        self.fails: list[str] = []
        self.checks = 0
        self.paired = 0

    def one(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks += 1
        print(f"   {OK if ok else BAD} {name}")
        if detail:
            print(f"       {detail}")
        if not ok:
            self.fails.append(name)

    def both_ways(self, name: str, pred, clean_sample, planted_sample,
                  clean_desc: str = "", planted_desc: str = "") -> None:
        """一条判据 + 它的**反向对照**。

        只验"真实样本是干净的"没有意义 —— 判据自己坏了也照样是绿的。
        所以必须再做一次：把违规**植入**进去，判据要变红。
        """
        self.checks += 1
        self.paired += 1
        clean, planted = pred(clean_sample), pred(planted_sample)
        ok = (not clean) and bool(planted)
        print(f"   {OK if ok else BAD} {name}")
        print(f"       真实样本：{'干净' if not clean else f'报出 {clean}'}"
              + (f"（{clean_desc}）" if clean_desc else ""))
        print(f"       植入违规：{'已认出 ' + str(planted) if planted else '**没认出**'}"
              + (f"（{planted_desc}）" if planted_desc else ""))
        if not ok:
            self.fails.append(f"{name}（真实样本 {clean} / 植入样本 {planted}）")


# ================================================================ A

# 只匹配**调用形态**，不匹配裸词 —— gen_bg_paste 的注释里就写着"rembg 偶发
# bad allocation"，按裸词匹配会把一句注释报成违规。判据必须窄到只认动作。
#
# ★ 这里必须把两件**看起来一样、其实不同**的事分开。第一版没分，于是
#   `fixers.fix_background` 里的 `synth.background_mask(img)` 被报成了违规 —— 假报警。
#
#   CUTOUT_CALL  产出**前景 / 主体 alpha** 的调用：它一出现，就说明这一处
#                在**决定主体长什么样**。多一处 = 多一个主体生产口（A 的反面）。
#   BG_SEG       背景分割**原语**（洪填找背景）。它本身不产出主体 ——
#                两个地方在用它：抠图（取反成前景）与 L0 刷白背景（只刷背景、不碰主体）。
#                把它算成抠图，等于"因为同一把尺子被两个人用过，就说他们干的是同一件事"。
CUTOUT_CALL = re.compile(
    r"\bremove_background\s*\(|\b_cutout_by_floodfill\s*\(|"
    r"\brembg\s*\.\s*(?:new_session|remove)\b")
BG_SEG = re.compile(r"\bfloodfill\s*\(|\bbackground_mask\s*\(")
ANY_PIXEL_JOB = re.compile(CUTOUT_CALL.pattern + "|" + BG_SEG.pattern)

# 抠图：定义处（synth.py）与两个允许的生产口。除此之外任何地方调它 = 多出一个主体生产口。
CUTOUT_ALLOWED = {"subject.py", "cutouts.py", "synth.py"}

# make_main_image 的调用块（到配对的右括号为止；够长以覆盖多行调用）
MAIN_CALL_BLOCK = re.compile(r"make_main_image\s*\(([\s\S]{0,900}?)\)\s*\n")


def _cutout_calls_in(text: str) -> list[str]:
    """渲染器层有没有碰"决定主体长什么样"或"分割背景"这两件事？

    渲染器层用的是**已经抠好的**主体（ctx['subject']），所以两者都该是零。
    """
    return sorted({m.group(0) for m in ANY_PIXEL_JOB.finditer(text)})


def _subject_producer_calls(text: str) -> list[str]:
    """这份源码里**产出前景 alpha** 的调用（`def remove_background(` 是定义，不算）。"""
    hits = []
    for i, ln in enumerate(text.splitlines(), 1):
        if re.match(r"\s*def\s+remove_background\s*\(", ln):
            continue
        if CUTOUT_CALL.search(ln):
            hits.append(f"{i}: {ln.strip()[:60]}")
    return hits


def _main_calls_without_passthrough(texts: dict) -> list[str]:
    """哪些 make_main_image 调用**没有**显式传 force_passthrough=True？

    少传这一个参数 = 那个渲染器自己又抠了一遍（make_main_image 默认会抠），
    于是位置 1 与位置 2 各有一个主体 —— 而这件事没有任何日志会记。
    """
    out = []
    for name, t in texts.items():
        for m in MAIN_CALL_BLOCK.finditer(t):
            if "force_passthrough=True" not in m.group(1):
                out.append(name)
    return out


def _producer_outside_allowlist(tree: dict) -> dict:
    """一份源码树里，哪些文件在**允许名单之外**产出主体 alpha。"""
    sites = {n: _subject_producer_calls(t) for n, t in tree.items()}
    return {k: v for k, v in sites.items() if v and k not in CUTOUT_ALLOWED}


def probe_a(p: Probes, cfg: dict) -> None:
    print("\nA. 主体只有一份（不变量 A）")

    # A1 —— 渲染器层零抠图。这是 A 的**代码级证据**：一旦某个渲染器自己抠图，
    #       系统里就有七个主体，七张图的轮廓由七次独立推断决定。
    p.both_ways(
        "A1 渲染器不许自己抠图（src/renderers/*.py 零抠图调用）",
        _cutout_calls_in,
        "\n".join(f.read_text(encoding="utf-8")
                  for f in sorted(RENDERER_DIR.glob("*.py"))),
        "@register('x')\ndef render(slot, ctx):\n    rgba, _ = synth.remove_background(img)\n",
        clean_desc="所有渲染器都从 ctx 取主体",
        planted_desc="植入的渲染器自己调了 remove_background")

    # A2 —— 抠图的生产口只有两处：主体一处、外来素材一处。
    #       判据只认**产出前景 alpha** 的调用（见 CUTOUT_CALL 的说明）：
    #       `background_mask` 是原语，L0 刷白背景也在用它，不算多一个主体生产口。
    src_tree = {f.name: f.read_text(encoding="utf-8")
                for f in sorted((ROOT / "src").rglob("*.py"))}
    extra = _producer_outside_allowlist(src_tree)
    p.one("A2 产出主体 alpha 的调用口只有 subject.py / cutouts.py"
          "（synth.py 是定义处）", not extra,
          f"扫了 {len(src_tree)} 个源文件，越界：{extra or '（无）'}"
          f"　允许名单：{'、'.join(sorted(CUTOUT_ALLOWED))}")
    p.both_ways("A2′ 判据能认出「多出来的主体生产口」",
                _producer_outside_allowlist,
                {"subject.py": "rgba, m = synth.remove_background(img)"},
                {"rogue.py": "rgba, m = synth.remove_background(img)"},
                clean_desc="调用口在允许名单内 → 不算越界",
                planted_desc="越界文件被抓出")

    # A3 —— 主图不许自己抠。它包住的是 synth.make_main_image，而那个函数**默认会抠一次**；
    #       只有显式传 force_passthrough=True 才是"用已抠好的主体"。
    renderer_texts = {f.name: f.read_text(encoding="utf-8")
                      for f in sorted(RENDERER_DIR.glob("*.py"))}
    p.both_ways(
        "A3 调 make_main_image 必须显式 force_passthrough=True",
        _main_calls_without_passthrough,
        renderer_texts,
        {"fake.py": "rep = synth.make_main_image(src_path=..., out_dir=..., slot=slot)\n"},
        clean_desc="主体只来自 ctx，不再抠一次",
        planted_desc="少传参数的那一行被抓出")

    # A4 —— 凡 needs 含 front 的坑位，其渲染器必须从 ctx 取主体。
    #       判据由**表**推出来，不是写死一个渲染器名单。
    front_slots = [s for s in cfg["slots"] if "front" in (s.get("needs") or [])]
    missing = []
    for slot in front_slots:
        f = RENDERER_DIR / f"{slot['renderer']}.py"
        if '"subject"' not in f.read_text(encoding="utf-8"):
            missing.append(f"坑位 {slot['id']}/{slot['renderer']}")
    p.one("A4 所有读 front 的渲染器都从 ctx['subject'] 取像素", not missing,
          "、".join(missing) if missing
          else f"{len(front_slots)} 个坑位全部走 ctx['subject']")


# ================================================================ B

def probe_b(p: Probes, cfg: dict) -> None:
    print("\nB. 生成层看不见主体（不变量 B）")

    slot = next(s for s in cfg["slots"] if s["id"] == SLOT_ID)
    catalog = _catalog(cfg)
    brand = load_brand()
    banned = [str(w) for w in (brand.get("forbidden_on_image") or [])]
    hint, _ = gbp.pick_hint(catalog, banned, SLOT_ID)
    prompt, negative = gbp.build_bg_prompt(slot, hint, banned)

    # B1 —— 真实请求体里没有图像字段。这是"结构保证"的直接证据。
    rep = imagegen.inclusion_report(prompt=prompt, negative_prompt=negative,
                                    model=imagegen.DEFAULT_MODEL, size="1600*1600",
                                    sent=True)
    p.one("B1 真实请求体里没有图像字段",
          rep["request_body_built"] and rep["request_image_fields"] == [],
          f"字段={rep['request_image_fields']}　"
          f"签名里的图像入参={rep['image_inputs_in_signature'] or '（无）'}")

    # B2 —— **反向对照就在这里**：植入含图像的请求体，字段路径必须被认出。
    #       这一条是 B 段的核心：它证明"泄漏是能被检出的"，
    #       否则 B3 的守卫只是一句永远为真的检查。
    leaky = {"input": {"messages": [{"role": "user", "content": [
        {"text": "空场景"}, {"image": "data:image/png;base64,AAAA"}]}]}}
    clean_body = {"input": {"messages": [{"role": "user", "content": [
        {"text": "空场景"}]}]}}
    p.both_ways("B2 含 data:image 的请求体必须被认出字段路径",
                imagegen._body_image_fields, clean_body, leaky,
                clean_desc="纯文本请求体",
                planted_desc="认出承载图像的那条路径")

    # B3 —— 守卫必须能被触发，且**不许误报**。
    fired = True
    try:
        gbp.assert_subject_excluded({"mode": "dashscope", "request_image_fields": []})
    except RuntimeError:
        fired = False               # 干净请求被判成违规 → 误报
    try:
        gbp.assert_subject_excluded({"mode": "dashscope",
                                     "request_image_fields": ["a.b.image"]})
        fired = False               # 该炸没炸
    except RuntimeError:
        pass
    quiet = True
    try:
        # 占位图（没 key，压根没发请求）→ 不变量 B **无从谈起**，不报错。
        # 这里若报错，就是把"没发生的事"当成"发生了坏事" —— 误报会让真报警贬值。
        gbp.assert_subject_excluded({"mode": "mock",
                                     "request_image_fields": ["x.image"]})
    except RuntimeError:
        quiet = False
    p.one("B3 守卫：真发请求且带图像字段 → 抛错；干净请求与占位图 → 不抛",
          fired and quiet,
          f"干净请求={'不抛' if fired else '**误报**'}　"
          f"带图像字段={'抛错' if fired else '**没抛**'}　"
          f"占位图={'不抛' if quiet else '**误报**'}")


# ================================================================ C

def probe_c(p: Probes, cfg: dict) -> None:
    print("\nC. 文字层不参与画面生成（不变量 C）")

    slot = next(s for s in cfg["slots"] if s["id"] == SLOT_ID)
    catalog = _catalog(cfg)
    brand = load_brand()
    banned = [str(w) for w in (brand.get("forbidden_on_image") or [])]
    hint, _ = gbp.pick_hint(catalog, banned, SLOT_ID)
    prompt, negative = gbp.build_bg_prompt(slot, hint, banned)
    both = prompt + "\n" + negative

    product = json.loads(PRODUCT.read_text(encoding="utf-8"))
    bullets = [str(b) for b in (product.get("bullets") or [])]
    specs = {str(k): str(v) for k, v in (product.get("specs") or {}).items()}

    def text_leaks(text: str) -> list[str]:
        hit = [f"规格 {k}={v}" for k, v in specs.items() if v and v in text]
        hit += [f"卖点 {b[:18]}…" for b in bullets if b and b in text]
        return hit

    # C1 —— 提示词（正向 + 负向）里不许出现任何卖点字面 / 规格数值。
    #       出现了就说明"文字进了画面生成"，错字与错数字会印在图上。
    _first_spec = next(iter(specs.values())) if specs else "22 cm"
    p.both_ways("C1 提示词里不许出现任何卖点字面 / 规格数值",
                text_leaks, both,
                both + f"，杯高 {_first_spec}，{bullets[0]}",
                clean_desc=f"扫了 {len(bullets)} 条卖点 + {len(specs)} 项规格",
                planted_desc="植入的规格与卖点都被抓出")

    def clause_missing(text: str) -> list[str]:
        out = []
        if gbp.NO_TEXT_CLAUSE not in text:
            out.append("缺禁字条款")
        if gbp.SUBJECT_EXCLUSION_CLAUSE not in text:
            out.append("缺产品排除条款")
        return out

    p.both_ways("C2 提示词无条件含禁字条款与产品排除条款",
                clause_missing, prompt,
                prompt.replace(gbp.NO_TEXT_CLAUSE, ""),
                clean_desc="两条都由代码追加，不由 catalog 的取景提示提供",
                planted_desc="抽掉禁字条款后立刻变红")
    p.one("C2 附带：取景提示本身不含这两条（它们是渲染器追加的，不是人写进数据的）",
          gbp.NO_TEXT_CLAUSE not in hint,
          f"hint=「{hint[:38]}…」" if len(hint) > 38 else f"hint=「{hint}」")

    # C3 —— 背景画面的唯一自由变量是**取景提示**，且它只来自 catalog（换场景 = 改数据）。
    hints = [str(h) for h in (catalog.get("bg_prompt_hints") or [])]
    p.one("C3 提示词素材只来自 catalog.bg_prompt_hints（换场景 = 改数据）",
          bool(hints) and hint in hints and prompt.startswith(hint),
          f"池里 {len(hints)} 条，按坑位号确定性取第 {SLOT_ID % max(1, len(hints))} 条")


# ================================================================ D

NO_MODEL_IMPORT = re.compile(r"\bimagegen\b|\bgenerate_image\s*\(")


def probe_d(p: Probes) -> None:
    print("\nD. 位置 1 零模型调用（不变量 D）")

    # D1 —— "零模型"这句话有唯一权威来源：registry 的声明。
    p.one("D1 registry 声明 compose_white 不调模型",
          registry.calls_model("compose_white") is False)

    # D2 —— 更要紧的是：那个文件里**根本没有通向模型的门**。
    #       声明可以是 false，而 import 一行 imagegen 就把它推翻了 ——
    #       所以判据必须是文本级的，并配植入对照。
    p.both_ways("D2 compose_white 里没有任何通向生成模型的入口",
                lambda t: sorted({m.group(0) for m in NO_MODEL_IMPORT.finditer(t)}),
                (RENDERER_DIR / "compose_white.py").read_text(encoding="utf-8"),
                "import imagegen\nimagegen.generate_image(p, n, out)\n",
                clean_desc="连 import 都没有",
                planted_desc="植入的 import 被认出")

    # D3 —— "七格里只有一格调模型"不是写死的判断，是数出来的。
    modelers = sorted(n for n in registry.known() if registry.calls_model(n))
    p.one("D3 全表只有 gen_bg_paste 一个渲染器声明调模型",
          modelers == ["gen_bg_paste"], f"数出来：{modelers or '（无）'}")


def _catalog(cfg: dict) -> dict:
    return yaml.safe_load((ROOT / cfg["catalog"]).read_text(encoding="utf-8")) or {}


def main() -> int:
    cfg = schema.assert_valid()
    registry.load_all()

    print("=" * 72)
    print("四条不变量 · 契约探针")
    print("=" * 72)
    print(f"表：{len(cfg['slots'])} 个坑位 · {len(registry.known())} 个渲染器　"
          f"（全部是静态/纯函数判据：不联网、不产图、不花钱）")

    p = Probes()
    probe_a(p, cfg)
    probe_b(p, cfg)
    probe_c(p, cfg)
    probe_d(p)

    print("\n" + "=" * 72)
    print(f"跑了 {p.checks} 条判据，其中 {p.paired} 条带反向对照"
          f"（植入违规样本后必须变红 —— 这是判据本身没瞎的证据）")
    if p.fails:
        print(f"\n{BAD} 有 {len(p.fails)} 条不变量判据不成立：")
        for f in p.fails:
            print(f"   {BAD} {f}")
        return 1
    print(f"{OK} 四条不变量全部有可执行判据，且判据本身被证明过能失败。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
