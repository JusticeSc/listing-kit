"""提示词增强探针 · **实验性质，不进 pipeline**（2026-09-22）

问题
----
v4 的"提示词引擎"是心脏，但**项目里一个文本 LLM 封装都没有** ⇒ "提示词增强"今天没有载体。
而手写 820 字枚举锁段虽然有效（见 §3.3 臂 B），却**不可扩展**：换一件商品就要人重新看过图手写。

本探针测的是：**这段锁段能不能由模型写出来？**

两臂（单变量 = 给 LLM 的输入）：
    C1 `text`   只给商品文本资料（title / bullets / specs）        → 测「文本够不够」
    C2 `vision` 文本资料 + **VLM 对参考图的属性描述**              → 测「加一步读图够不够」

第三臂（单变量 = 编译器不同，2026-09-22 追加）：
    D  `compiler` 用户给的**通用 Prompt Compiler**（L1）+ 本域 context（L2）
      → 输入 = **已知会失败的那版粗提示词**（臂 A 的 84 字嘱咐 + 场景段），
        问：一个带纪律的通用编译器能不能把粗版救回来、并产出纯英文可直接送模型的提示词。
      编译结果走 `lock_probe.py --prompt-file`（整段替换，不拼场景段）。

两臂的下游完全同参数（`lock_probe.py --arm enumerated --lock-file`），
所以 A / B / C1 / C2 四臂**只差"锁段由谁写"**：
    A  人写的 84 字嘱咐式 · B  人写的 820 字枚举式 · C1/C2  模型写的枚举式

它同时验三件事
--------------
1. **元提示词值多少分** —— 不与任何人的版本比，只与 B（人看过图手写的 820 字）比。
2. **`unknowns` 是不是空** —— 这是"文本资料够不够写锁段"的机器可读读数（判据，不是感觉）。
3. **产出能不能被程序校验** —— 长度 / 编号特征 / HARD CONSTRAINTS / NO 否定段。
   散文没法校验；校验不了的产出只能人肉看，那就退回臂 A 的处境。

用法
----
    python evals/probes/prompt_enhance_probe.py --arm vision --dry-run   # 只看将发什么，不花钱
    python evals/probes/prompt_enhance_probe.py --arm text               # C1：只跑 LLM，不跑生图
    python evals/probes/prompt_enhance_probe.py --arm vision --run-image # C2：跑完再接生图 n=3

退出码：0 通过校验 · 2 无 key（未发起请求）· 3 调用失败 · 5 产出未过校验（**不是错误，是结果**）
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
KIT = HERE.parents[1]
ASSETS = HERE / "prompt_enhance"

CHAT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
TEXT_MODELS = ["qwen-plus-latest", "qwen-plus", "qwen-max"]
VISION_MODELS = ["qwen-vl-max-latest", "qwen-vl-plus-latest", "qwen-vl-max"]

DEFAULT_FACTS = KIT / "examples" / "product_fullset.json"
DEFAULT_REF = KIT / "examples" / "input" / "cup_source.jpg"

VLM_INSTRUCT = """Describe ONLY the product in this image, as a checklist of visible physical
attributes, so that another model could reproduce the product exactly without seeing the image.

Cover, in this order:
1. overall form and proportion - give an estimated height:width ratio
2. section by section, top to bottom: material and surface finish, and where each section
   starts and ends as a fraction of the total height
3. the colour of each section
4. lid / cap / opening structure, described layer by layer
5. anything else visible that a reproduction must keep

Then a final paragraph listing what this product does NOT have, explicitly saying for each of
these whether it is absent: handle, side grip, spout, straw, second cap, printed pattern,
label, text, logo, decoration.

Plain text, English, no preamble, no markdown."""


def call_chat(model: str, messages: list[dict], key: str,
              timeout: int = 180) -> tuple[str, dict]:
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {"model": model, "messages": messages}
    last = ""
    for i in range(3):
        try:
            r = requests.post(CHAT_URL, headers=headers, json=body, timeout=timeout)
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"
            if i < 2:
                time.sleep(3 * (i + 1))
            continue
        if r.status_code == 200:
            d = r.json()
            return d["choices"][0]["message"]["content"], d.get("usage") or {}
        last = f"HTTP {r.status_code}: {r.text[:300]}"
        if r.status_code in (400, 404):     # 模型名不对 → 直接换下一个，不重试
            break
    raise RuntimeError(f"{model} 调用失败: {last}")


def call_any(models: list[str], messages: list[dict], key: str) -> tuple[str, str, dict, list]:
    tried: list[dict] = []
    for m in models:
        try:
            txt, usage = call_chat(m, messages, key)
            return txt, m, usage, tried
        except Exception as exc:
            tried.append({"model": m, "error": str(exc)[:200]})
    raise RuntimeError(f"全部候选失败: {tried}")


def data_uri(path: Path) -> str:
    mime = {".png": "image/png", ".webp": "image/webp"}.get(path.suffix.lower(),
                                                            "image/jpeg")
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def load_meta() -> tuple[str, str]:
    """从 meta_lock_prompt.md 里抽出 SYSTEM 与 USER 两个围栏块（**不复制粘贴，读了才是真的**）。"""
    text = (ASSETS / "meta_lock_prompt.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```\n(.*?)```", text, flags=re.S)
    if len(blocks) < 2:
        raise RuntimeError("meta_lock_prompt.md 里找不到 SYSTEM / USER 两个围栏块")
    return blocks[0].strip(), blocks[1].strip()


def _named_blocks(path: Path) -> dict[str, str]:
    """取 ```NAME ... ``` 形式的具名块。

    为什么用具名而不是按顺序数：这个文件里同时装着 L1 编译器（用户原文，不许动）
    与 L2 本域 context（我加的）。**分不清哪块是谁的，就没法在改判时归因。**
    也刻意不嵌套围栏 —— 嵌套会让"第一个 ``` 到下一个 ```"这种数法错位。
    """
    text = path.read_text(encoding="utf-8")
    return {name: body.strip()
            for name, body in re.findall(r"```([A-Z]+)\n(.*?)```", text, flags=re.S)}


def load_compiler() -> tuple[str, str]:
    blocks = _named_blocks(ASSETS / "meta_compiler_v1.md")
    for k in ("COMPILER", "CONTEXT"):
        if k not in blocks:
            raise RuntimeError(f"meta_compiler_v1.md 里找不到 {k} 块")
    return blocks["COMPILER"], blocks["CONTEXT"]


def render_facts(product: dict, image_desc: str | None) -> str:
    lines = [f"title: {product.get('title', '')}"]
    if product.get("bullets"):
        lines.append("selling points (NOT physical features, do not turn these into "
                     "appearance claims):")
        lines += [f"  - {b}" for b in product["bullets"]]
    if product.get("specs"):
        lines.append("specs:")
        lines += [f"  {k}: {v}" for k, v in product["specs"].items()]
    if image_desc:
        lines += ["", "description of the reference image (produced by a vision model, "
                      "treat as observed fact):", image_desc.strip()]
    else:
        lines += ["", "(no description of the reference image is available)"]
    return "\n".join(lines)


def load_modes() -> list[dict]:
    doc = json.loads((ASSETS / "failure_modes.json").read_text(encoding="utf-8"))
    return doc["modes"]


def render_failure_modes() -> str:
    return "\n".join(f"- [{m['id']}] {m['pattern']}  → 必须否掉: {m['negation']}"
                     for m in load_modes())


# 否定语境窗口。**判据锚点在这里**：一个特征名只有落在否定语境里才算"被否掉"；
# 单纯出现不算。标记词英中各一套 —— 要判的是"否掉了没有"，不是"用哪种语言否掉的"。
NEG_MARK = (r"(?:\bNO\b|\bno\b|\bwithout\b|\bnot\b|\babsence of\b"
            r"|不得|不要|无需|没有|不含|禁止|无)")
NEG_CTX = re.compile(NEG_MARK + r"[^.;。；]{0,120}", re.I)


def head_hit(head: str, hay: str) -> bool:
    """锚点是否命中。**英文走词边界、中文走子串** —— 不是随手写的两套：

    英文若用子串，`text` 会命中 `texture`、`cap` 会命中 `capacity` ⇒ 假绿；
    中文没有词边界概念（`无把手` 里 `无` 与 `把` 都是 \\w，`\\b把手\\b` 匹配不上）⇒ 子串才对。
    """
    h = head.lower()
    if re.fullmatch(r"[a-z0-9 \-]+", h):
        return re.search(r"\b" + re.escape(h) + r"\b", hay) is not None
    return h in hay


def _balanced_from(raw: str, i: int) -> str | None:
    """从 raw[i]（应为 `{`）起找**与之配对**的右括号，返回该子串；不平衡返回 None。"""
    depth, in_str, esc = 0, False, False
    for j in range(i, len(raw)):
        ch = raw[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return raw[i:j + 1]
    return None


def extract_json(raw: str) -> dict:
    """抠出**第一个能解析成 dict 的平衡 JSON 对象**。

    与 v1 的差别：v1 用 `rfind("}")` 赌"最后一个右括号就是配对的"，一崩即死。
    v2 从**每个** `{` 起点各试一次：配对 → 解析 → 成功即返回；失败就试下一个。
    这样正文里的 `the set {a,b}` 会被跳过而不是把整段带走。
    """
    for i, ch in enumerate(raw):
        if ch != "{":
            continue
        chunk = _balanced_from(raw, i)
        if chunk is None:
            continue                      # 截断/不平衡 → 换个起点
        try:
            got = json.loads(chunk)
        except Exception:
            continue                      # 不是合法 JSON（如 `{a, b}`、单引号）→ 换个起点
        if isinstance(got, dict):
            return got
    raise ValueError(f"没有找到能解析的 JSON 对象:\\n{raw[:400]}")

# 日中韩统一表意文字 + 全角标点。**只在"最终提示词"这一段上判**，
# 不判整份产出 —— 编译器用中文写「关键增强点」是正常的（那是给人看的），
# 但提示词本身混中文会被图像模型当成要画进画面的内容（库 B `generate.py:194` 的纪律）。
CJK = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]")


def parse_compiled(raw: str) -> tuple[str, dict]:
    """从通用编译器的产出里取出 (最终提示词, 溯源 JSON)。

    编译器按它自己的输出契约交两节：`## 增强后的提示词` 与 `## 关键增强点`；
    本域额外要求它在中间插一节 `## 溯源`（见 meta_compiler_v1.md 的 L2）。
    **按标题切、不按顺序猜** —— 顺序会随模型变，标题是它自己的契约。
    """
    m = re.search(r"^##\s*增强后的提示词\s*$", raw, flags=re.M)
    if not m:
        raise ValueError("产出里没有 `## 增强后的提示词` 这一节")
    rest = raw[m.end():]
    nxt = re.search(r"^##\s*", rest, flags=re.M)
    prompt = (rest[:nxt.start()] if nxt else rest).strip()

    trace: dict = {}
    t = re.search(r"^##\s*溯源\s*$", raw, flags=re.M)
    if t:
        tail = raw[t.end():]
        n2 = re.search(r"^##\s*", tail, flags=re.M)
        seg = tail[:n2.start()] if n2 else tail
        try:
            trace = extract_json(seg)
        except Exception:
            trace = {}
    if not prompt:
        raise ValueError("`## 增强后的提示词` 这一节是空的")
    return prompt, trace


def validate(out: dict, modes: list[dict]) -> tuple[list[str], list[str]]:
    """**判据**（不是感觉）。返回 (problems, advisories)。

    分两档，因为这两档性质不同：
      problems   —— 语义性质不达标（覆盖不了已知失败模式 / 锁段是空话）⇒ 产出是废的
      advisories —— 形状建议（有没有 `HARD CONSTRAINTS` 标题）⇒ **不影响结论**

    ★ 这里踩过一次假红：v0.1 的判据检查字面标题 `HARD CONSTRAINTS`，
    而 C1 臂交的锁段**语义完全达标**（6 条失败模式逐条显式否掉），只是没写那个标题，
    判据报"缺这一节" ⇒ 差点把「模型没做到」写进结论。
    **标题是形状，否认是性质。测形状会把合格产出判死，那是拿判据制造假红。**
    """
    problems: list[str] = []
    advisories: list[str] = []
    lock = (out.get("lock_segment") or "").strip()
    if not lock:
        problems.append("lock_segment 为空")
        return problems, advisories
    if len(lock) < 300:
        problems.append(f"lock_segment 太短（{len(lock)} 字 < 300）—— 大概率是笼统嘱咐句，"
                        "臂 A 实测这种写法会被模型自造结构")
    if not re.search(r"\(1\)|\b1\)|\b1\.", lock):
        problems.append("lock_segment 里没有编号枚举特征 —— 无法逐条核对")

    neg_ctx = " ".join(NEG_CTX.findall(lock)).lower()
    missing: list[str] = []
    for m in modes:
        kind = m.get("check", "negation")
        hay = neg_ctx if kind == "negation" else lock.lower()
        if not any(head_hit(h, hay) for h in m.get("check_heads", [])):
            missing.append(f"{m['id']}/{kind}")
    if missing:
        problems.append(f"未覆盖失败模式 {missing} —— "
                        "新增类失败要求在否定语境里被显式否掉，改动类要求正向定量断言")

    if "HARD CONSTRAINTS" not in lock.upper():
        advisories.append("没有 `HARD CONSTRAINTS` 标题（只影响机器定位否定段；语义覆盖已按上文判定）")
    hit = CJK.findall(lock)
    if hit:
        problems.append(f"最终提示词里出现 {len(hit)} 个中日韩字符（如 {'、'.join(hit[:6])}）—— "
                        "图像模型会把中文当画面内容（库 B `generate.py:194` 的纪律：禁中英混写）")
    if not out.get("used_facts"):
        problems.append("used_facts 为空 —— 无法追溯特征出处（等于允许编造）")
    return problems, advisories


def revalidate() -> int:
    """**零调用**：按当前判据重算已落盘产出，并附正反两组对照。

    为什么需要它：**判据本身也是判据。** 改过 `validate()` 之后，旧产物的结论会静默变化 ——
    不重算，你就分不清"上次那个红"是产出坏还是判据坏（v0.1 的 `HARD CONSTRAINTS` 标题检查
    就是这么制造出一条假红的）。两条对照是证伪用的：
      正向（必须绿）· 臂 B 人写枚举段 ⇒ 证明判据不会把合格的判死
      反向（必须红）· 合成的笼统嘱咐句 ⇒ 证明判据还红得起来，不是恒绿
    """
    sys.path.insert(0, str(HERE))
    import lock_probe as lp          # 同目录实验脚本，直接取两条人写臂的原文
    modes = load_modes()
    rows: list[tuple[str, str, str]] = []

    cases = [
        ("对照·正向 | 臂 B 人写·枚举 820 字（须绿）", lp.ARMS["enumerated"]["lock"],
         ["从 reference 抽出的特征清单"]),
        ("对照·反向 | 合成·笼统嘱咐（须红）",
         "Keep the product exactly as shown in the reference image. "
         "Do not change it. Put it in a nice scene.", ["无"]),
        ("对照·反向 | 合成·中文提示词（须红·测 CJK 判据）",
         "商品保真段：保留参考图中这件商品的全部外观特征，(1) 不锈钢杯身占上部三分之二，"
         "(2) 深棕色硅胶套包住下部三分之一。HARD CONSTRAINTS: NO handle, NO spout, "
         "NO second cap, NO belt, NO label, NO text. Preserve the exact height-to-width "
         "ratio, keep the lid assembly's layered structure unchanged, and do not substitute "
         "a similar-looking flask.", ["无"]),
        ("实评 | 臂 A 人写·嘱咐 84 字（须红·多因）", lp.ARMS["advice"]["lock"], ["无"]),
    ]
    for name, lock, used in cases:
        p, adv = validate({"lock_segment": lock, "used_facts": used}, modes)
        rows.append((name, "红" if p else "绿", "；".join(p) or "-"))

    for arm in ("text", "vision", "compiler"):
        f = ASSETS / arm / "lock_segment.txt"
        if not f.exists():
            continue
        lock = f.read_text(encoding="utf-8").strip()
        used: list = []
        rep = ASSETS / arm / "report.json"
        if rep.exists():
            try:
                used = (json.loads(rep.read_text(encoding="utf-8")) or {}).get("used_facts") or []
            except Exception:
                used = []
        p, adv = validate({"lock_segment": lock, "used_facts": used}, modes)
        rows.append((f"实评 | C-{arm}（模型写）{len(lock)} 字", "红" if p else "绿",
                     "；".join(p + adv) or "-"))

    w = max(len(r[0]) for r in rows)
    print("=== 按当前判据重算已落盘产出（零调用）===")
    for name, verdict, why in rows:
        print(f"  {name.ljust(w)}  → {verdict}   {why}")
    print("\n  判据口径：只认**前置存在否定**（`NO X` / `without X` / `无 X`）。")
    print("  『X 不得改动』这类后置否定**不算** —— 它在语义上不等于「没有 X」；")
    print("  认了它就会把「锁段自己给模型安上了 X 的前提」判成合格。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="提示词增强探针（实验，不进 pipeline）")
    ap.add_argument("--arm", choices=["text", "vision", "compiler"],
                    help="text=只给文本资料 / vision=文本资料+VLM 读图 / "
                         "compiler=通用编译器(L1)+本域 context(L2)，输入是臂 A 那版粗提示词")
    ap.add_argument("--revalidate", action="store_true",
                    help="**零调用**：按当前判据重算已落盘产出 + 正反两组对照")
    ap.add_argument("--facts", default=str(DEFAULT_FACTS))
    ap.add_argument("--ref", default=str(DEFAULT_REF))
    ap.add_argument("--out", default=str(ASSETS))
    ap.add_argument("--run-image", action="store_true",
                    help="过校验后接生图 n=3（走 lock_probe.py --lock-file）")
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.revalidate:
        return revalidate()
    if not args.arm:
        print("[x] 必须给 --arm（或用 --revalidate）")
        return 2

    out_dir = Path(args.out) / args.arm
    out_dir.mkdir(parents=True, exist_ok=True)
    product = json.loads(Path(args.facts).read_text(encoding="utf-8"))
    modes = load_modes()
    fmodes = render_failure_modes()

    # compiler 臂也**必须**读图 —— 它编译的是保真段，没有参考图描述就会重演 C1 的失败
    # （把卖点当外观事实）。这不是"顺便加的步骤"，是 L2 里"外观断言只能来自图像"的必然要求。
    need_vlm = args.arm in ("vision", "compiler")

    key = os.getenv("DASHSCOPE_API_KEY") or ""
    if not key and not args.dry_run:
        print("[!] 未配置 DASHSCOPE_API_KEY —— **未发起任何请求**（这不是失败）")
        return 2

    raw_prompt = None
    if args.arm == "compiler":
        sys.path.insert(0, str(HERE))
        import lock_probe as lp            # 单一出处：臂 D 的输入就是臂 A 的原文，不会失同步
        raw_prompt = lp.ARMS["advice"]["lock"] + " " + lp.ARMS["advice"]["scene"]
        compiler, context_tpl = load_compiler()
        system, user_tpl = "", ""
    else:
        system, user_tpl = load_meta()
        compiler, context_tpl = "", ""

    # ---- 第 1 步（vision / compiler 臂）：让 VLM 读参考图 -----------------------------
    image_desc = None
    vlm_meta: dict = {}
    if need_vlm:
        msg = [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": data_uri(Path(args.ref))}},
            {"type": "text", "text": VLM_INSTRUCT}]}]
    else:
        msg = None

    def build_messages(desc: str | None) -> list[dict]:
        facts = render_facts(product, desc)
        if args.arm == "compiler":
            ctx = (context_tpl.replace("{{FACTS}}", facts)
                   .replace("{{FAILURE_MODES}}", fmodes))
            body = (compiler.replace("{{RAW_PROMPT}}", raw_prompt)
                    .replace("{{TARGET_MODEL}}", "qwen-image-2.0-pro（图像生成模型）")
                    .replace("{{CONTEXT}}", ctx))
            return [{"role": "system", "content": body},
                    {"role": "user", "content": "按你的规则编译上面这个提示词。"}]
        user = user_tpl.replace("{{FACTS}}", facts).replace("{{FAILURE_MODES}}", fmodes)
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    messages = build_messages(None)

    if args.dry_run:
        print(f"=== arm {args.arm} · dry-run ===")
        print(f"VLM step: {'YES' if need_vlm else 'no'}")
        print(f"system {len(messages[0]['content'])} 字符 · user {len(messages[1]['content'])} 字符")
        print(f"失败模式 {len(fmodes)} 字符")
        if raw_prompt is not None:
            print(f"\n--- 待编译的粗版提示词（{len(raw_prompt)} 字，来自臂 A）---\n{raw_prompt}")
        else:
            print("\n--- facts ---\n" + render_facts(product, None))
        return 0

    if need_vlm:
        t0 = time.time()
        image_desc, vm, vusage, vtried = call_any(VISION_MODELS, msg, key)
        vlm_meta = {"model": vm, "elapsed_s": round(time.time() - t0, 1),
                    "usage": vusage, "tried": vtried,
                    "characters": len(image_desc)}
        (out_dir / "image_description.txt").write_text(image_desc + "\n", encoding="utf-8")
        print(f"[ok] VLM {vm} 读完参考图 · {vlm_meta['elapsed_s']}s · "
              f"{len(image_desc)} 字 → image_description.txt")

    # ---- 第 2 步：LLM 写锁段 / 编译器编译 -------------------------------------------
    messages = build_messages(image_desc)
    t0 = time.time()
    raw, model, usage, tried = call_any(TEXT_MODELS, messages, key)
    elapsed = round(time.time() - t0, 1)
    (out_dir / "llm_raw.txt").write_text(raw + "\n", encoding="utf-8")

    if args.arm == "compiler":
        try:
            lock, trace = parse_compiled(raw)
        except Exception as exc:
            (out_dir / "report.json").write_text(json.dumps(
                {"arm": args.arm, "stage": "parse", "error": str(exc), "raw": raw},
                ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"[x] 编译器产出解析失败：{exc}")
            return 5
        parsed = {"lock_segment": lock,
                  "used_facts": trace.get("used_facts") or ["（编译器未交 溯源 节）"],
                  "unknowns": trace.get("unknowns") or []}
    else:
        try:
            parsed = extract_json(raw)
        except Exception as exc:
            (out_dir / "report.json").write_text(json.dumps(
                {"arm": args.arm, "stage": "parse", "error": str(exc), "raw": raw},
                ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"[x] 输出不是合法 JSON：{exc}")
            return 5

    problems, advisories = validate(parsed, modes)
    lock = (parsed.get("lock_segment") or "").strip()
    unknowns = parsed.get("unknowns") or []
    report = {
        "probe": "prompt_enhance",
        "arm": args.arm,
        "arm_meaning": {"text": "只给文本资料",
                        "vision": "文本资料 + VLM 读图描述",
                        "compiler": ("通用编译器 L1（用户原文）+ 本域 context L2；"
                                     "输入 = 臂 A 那版 84 字粗提示词")}[args.arm],
        "raw_prompt_chars": len(raw_prompt) if raw_prompt else None,
        "text_model": model, "text_elapsed_s": elapsed, "text_usage": usage,
        "text_tried": tried,
        "vlm": vlm_meta or None,
        "lock_chars": len(lock),
        "comparison_baseline": {"arm_B_human_lock_chars": 820},
        "used_facts": parsed.get("used_facts"),
        "unknowns": unknowns,
        "unknowns_count": len(unknowns),
        "validation_problems": problems,
        "validation_advisories": advisories,
        "validation_passed": not problems,
        "lock_segment": lock,
        "facts_chars": len(render_facts(product, image_desc)),
    }
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "lock_segment.txt").write_text(lock + "\n", encoding="utf-8")

    print(f"[ok] LLM {model} · {elapsed}s · 锁段 {len(lock)} 字（臂 B 人手写的是 820 字）")
    print(f"     unknowns {len(unknowns)} 条" + (f"：{unknowns}" if unknowns else " ← 文本资料够用"))
    if problems:
        print("[!] 未过校验（**这是结果，不是崩溃**）：")
        for p in problems:
            print(f"    - {p}")
    else:
        print("     校验通过：有编号特征 / 逐条否掉已知失败模式 / used_facts 非空")
    for a in advisories:
        print(f"     （建议项，不影响结论）{a}")

    if not problems and args.run_image:
        out_root = HERE / "lock_out"
        if args.arm == "compiler":
            # 编译器的产出**含锁段 + 场景段**，所以必须走 --prompt-file（整段替换）。
            # 走 --lock-file 会把场景段再拼一次，那测的就不是编译器的产出了。
            cmd = [sys.executable, str(HERE / "lock_probe.py"),
                   "--prompt-file", str(out_dir / "lock_segment.txt"),
                   "--tag", "d_compiler", "--n", str(args.n), "--out", str(out_root)]
        else:
            cmd = [sys.executable, str(HERE / "lock_probe.py"),
                   "--arm", "enumerated",
                   "--lock-file", str(out_dir / "lock_segment.txt"),
                   "--tag", f"c_{args.arm}",       # ← 两臂必须不同目录，否则 r1..r3 互相覆盖
                   "--n", str(args.n), "--out", str(out_root)]
        print(f"\n→ 接生图：{' '.join(cmd[-6:])}")
        r = subprocess.run(cmd, capture_output=True)
        print(r.stdout.decode("utf-8", "replace").strip())
        if r.returncode != 0:
            print(r.stderr.decode("utf-8", "replace")[-800:])
            return r.returncode
    return 0 if not problems else 5


if __name__ == "__main__":
    raise SystemExit(main())
