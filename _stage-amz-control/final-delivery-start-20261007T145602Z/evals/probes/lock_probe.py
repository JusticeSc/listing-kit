"""锁探针 · **实验性质，不进 pipeline**（2026-09-22）

问题
----
v4 设计的地基是一句嘱咐：「给模型商品参考图 + 一段锁段提示词，它就别改商品」。
三库都没有能证明"锁住了"的程序判据 —— 库 A 有客观机检，B/C 没有。
所以这是**未验证前提**，不是设计的一部分。

本探针只回答一件事：**同一张参考图 + 同一段提示词，出 n 张，商品变了没有。**

它为什么故意不碰 `src/imagegen.py`
-----------------------------------
`image_inputs_in_signature()` 现在返回 `[]` —— 这是不变量「生成层看不见主体」的**唯一证据**，
也被 `evals/golden/slot04.json` 逐值冻着（`"image_inputs_in_signature": []`）。
所以实验代码放 `evals/probes/`，不放进 `src/`：一旦有人给 pipeline 的 `generate_image`
加了参考图参数，那个函数会立刻把这件事报出来（守卫按设计工作），而不是被我这次实验悄悄变旧。

机器判不了什么（如实说，别假装有检测器）
----------------------------------------
机器能算出的只有「n 张彼此差多少」（自洽性；差异 ⊇ 商品差异，是**上界**不是判据）。
「模型有没有改商品」是主观项 —— 形态照 E0 的 `ATTEST_ITEMS`：**机器判不了的项要求签字**，
不写启发式假检测器。所以产物 = 一张源图对照图 + 一份事实清单，供人 200% 比对。

用法
----
    python evals/probes/lock_probe.py --dry-run     # 只打印将要发出的请求体（base64 截断），不花钱
    python evals/probes/lock_probe.py --arm advice       # 臂 A：笼统嘱咐式锁段，n=3
    python evals/probes/lock_probe.py --arm enumerated   # 臂 B：逐特征枚举 + 显式否定，n=3
    python evals/probes/lock_probe.py --arm enumerated --prompt-extend   # 测 prompt_extend 会不会改写锁段
    python evals/probes/lock_probe.py --prompt-file <f> --tag d_compiler # 整段来自编译器产出

两条臂**除锁段外一切相同**（同一模型 / 场景 / 负面词 / n / size），是单变量对照。
产物落 `evals/probes/lock_out/<arm>_<model>/`。

退出码：0 拿到 n 张 · 2 无 key（**未发起请求**，不是失败）· 3 调用失败 · 4 产物不齐
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
from pathlib import Path

import requests
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IMAGE = ROOT / "examples" / "input" / "cup_source.jpg"
DEFAULT_OUT = ROOT / "evals" / "probes" / "lock_out"

MULTIMODAL_URL = ("https://dashscope.aliyuncs.com/api/v1"
                  "/services/aigc/multimodal-generation/generation")
IMAGE_GEN_URL = ("https://dashscope.aliyuncs.com/api/v1"
                 "/services/aigc/image-generation/generation")

# (endpoint, model) 候选。**逐个试，第一个成功即停** —— 每次成功都花钱，不做矩阵实验。
CANDIDATES: list[tuple[str, str]] = [
    (MULTIMODAL_URL, "qwen-image-2.0-pro"),
    (MULTIMODAL_URL, "qwen-image-edit-plus"),
    (MULTIMODAL_URL, "qwen-image-edit"),
    (IMAGE_GEN_URL, "qwen-image-2.0-pro"),
]

# 两条臂 = 两种锁段写法。**单变量**：除锁段外一切相同（模型 / 场景 / 负面 / n / size）。
ARMS: dict[str, dict] = {
    # 臂 A「嘱咐式」：笼统说"不得改动"。这是 v4 §3 保真段的第一版写法。
    "advice": {
        "why": "笼统嘱咐 —— '一律不得改动'。看模型听不听话。",
        "lock": ("严格保留参考图中这件商品本身：外形轮廓、比例尺寸、颜色、材质纹理、"
                 "图案的位置与数量、把手与杯口的结构一律不得改动、不得美化、"
                 "不得替换成相似商品，只允许改变它周围的环境。"),
        "scene": ("把参考图中的商品原样放进一张简洁明亮的现代厨房台面场景：浅灰石材台面，"
                  "浅色墙面，柔和自然光从左前方照入，画面干净、留白充足、居中构图，"
                  "正方形构图，高清专业商品摄影布光。"),
        "neg": ("文字, 字母, 数字, 汉字, 水印, logo, 标志, 签名, 标签, 价格, 边框, 二维码, "
                "促销角标, 变形, 畸变, 低质量, 模糊, 多余的手指, 重复的物体, "
                "另一个杯子, 相似商品, 竞品"),
    },
    # 臂 B「逐特征枚举 + 显式否定」：照库 B 738 行 prompt 的做法 ——
    # 把商品特征写成**可逐条核对**的清单，并把已知失败模式（自造把手）显式否掉。
    # prompt 用英文：库 B 的纪律（避免中英混入导致模型误解指令）。
    "enumerated": {
        "why": "逐特征枚举 + 显式否定已知失败模式 —— 这是'提示词增强'的实操形态。",
        "lock": ("Product fidelity is mandatory. The reference image shows ONE product: a tall "
                 "cylindrical vacuum-insulated drink flask. Reproduce its exact attributes "
                 "without any change: (1) a seamless brushed stainless-steel body occupying "
                 "the upper two thirds; (2) a matte dark-brown/black silicone sleeve wrapping "
                 "the lower third, slightly wider at the soft base; (3) a screw-on lid assembly "
                 "in dark charcoal, with a stepped ridged rim and a narrow band around it; "
                 "(4) the flask is TALL and SLIM, height-to-diameter ratio about 3:1. "
                 "HARD CONSTRAINTS - the product has NO handle, NO side grip, NO spout, NO "
                 "straw, NO second cap, NO straw lid, NO belt, NO printed pattern, NO label, "
                 "NO text, NO engraving. Do not add any of these. Do not restyle, do not "
                 "beautify, do not substitute a similar-looking flask. Only the surroundings "
                 "change."),
        "scene": ("Place that exact flask into a clean bright modern kitchen counter scene: "
                  "light grey stone countertop, pale wall, soft natural daylight from the front "
                  "left, generous empty space, centred composition, square 1:1 framing, "
                  "high-end product photography lighting."),
        "neg": ("text, letters, numbers, watermark, logo, signature, label, price tag, border, "
                "qr code, handle, side grip, carrying handle, spout, straw, extra cap, "
                "distortion, deformed, duplicate object, second flask, similar product, "
                "low quality, blurry, people, hands, illustration, 3d render"),
    },
}
DEFAULT_ARM = "advice"


# ----------------------------------------------------------------- 图像工具（零新依赖）
def data_uri(path: Path) -> str:
    mime = {".png": "image/png", ".webp": "image/webp",
            ".bmp": "image/bmp"}.get(path.suffix.lower(), "image/jpeg")
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def dhash(path: Path, bits: int = 16) -> list[int]:
    """差值哈希。用途**只有一个**：量"两张图差多少"。"""
    g = Image.open(path).convert("L").resize((bits + 1, bits), Image.LANCZOS)
    px = list(g.tobytes())          # 不用 getdata()：Pillow 14 起弃用，别留会到期的写法
    row = bits + 1
    return [int(px[y * row + x] > px[y * row + x + 1])
            for y in range(bits) for x in range(bits)]


def hamming(a: list[int], b: list[int]) -> int:
    return sum(x != y for x, y in zip(a, b))


def contact_sheet(files: list[Path], out: Path, cell: int = 520) -> Path:
    """源图 + n 张产物并排，带编号标签。给人 200% 比对用。"""
    imgs = [Image.open(p).convert("RGB") for p in files]
    imgs = [im.resize((cell, int(cell * im.height / im.width)), Image.LANCZOS)
            for im in imgs]
    h = max(im.height for im in imgs) + 34
    sheet = Image.new("RGB", (cell * len(imgs), h), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    for i, (im, p) in enumerate(zip(imgs, files)):
        sheet.paste(im, (i * cell, 34))
        tag = "SOURCE" if i == 0 else f"#{i}"
        d.text((i * cell + 10, 10), f"{tag}  {p.name}", fill=(20, 20, 20))
        if i:
            d.line([(i * cell, 0), (i * cell, h)], fill=(210, 210, 210), width=1)
    sheet.save(out, "JPEG", quality=90)
    return out


# ----------------------------------------------------------------- 调用
def build_body(endpoint: str, model: str, ref: Path, prompt: str,
               negative: str, n: int, size: str | None,
               prompt_extend: bool) -> dict:
    params: dict = {"n": n, "negative_prompt": negative, "watermark": False,
                    "prompt_extend": prompt_extend}
    if size:
        params["size"] = size
    content: list[dict] = [{"image": data_uri(ref)}]
    if endpoint == MULTIMODAL_URL:
        content.append({"text": prompt})
        body = {"model": model,
                "input": {"messages": [{"role": "user", "content": content}]},
                "parameters": params}
    else:
        # image-generation 族的 messages 形状不同：图与文各自成条
        body = {"model": model,
                "input": {"messages": [{"role": "user", "content": content},
                                       {"role": "user", "content": [{"text": prompt}]}]},
                "parameters": params}
    return body


def extract_images(result: dict) -> list[str]:
    """同步与异步两种返回形状都取，换模型不必改解析。"""
    out = result.get("output") or {}
    urls: list[str] = []
    for r in (out.get("results") or []):
        if isinstance(r, dict) and r.get("url"):
            urls.append(r["url"])
    for ch in (out.get("choices") or []):
        for c in ((ch.get("message") or {}).get("content") or []):
            if isinstance(c, dict) and c.get("image"):
                urls.append(c["image"])
    return urls


def post_retry(url: str, headers: dict, body: dict, attempts: int = 3):
    last = None
    for i in range(attempts):
        try:
            return requests.post(url, headers=headers, json=body, timeout=120)
        except Exception as exc:            # 网络抖动不该让一张已付费的图白跑
            last = exc
            if i < attempts - 1:
                time.sleep(3 * (i + 1))
    raise RuntimeError(f"提交连续 {attempts} 次失败: {last}") from last


def poll(task_id: str, headers: dict, timeout_s: int = 300) -> dict:
    url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
    deadline = time.time() + timeout_s
    last: dict = {}
    while time.time() < deadline:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        last = r.json()
        status = ((last.get("output") or {}).get("task_status") or "").upper()
        if status in ("SUCCEEDED", "SUCCESS"):
            return last
        if status in ("FAILED", "CANCELED", "UNKNOWN"):
            raise RuntimeError(f"任务失败: {last}")
        time.sleep(3)
    raise TimeoutError(f"轮询超时({timeout_s}s): {last}")


def run_once(args) -> int:
    ref = Path(args.image)
    if not ref.exists():
        print(f"[x] 参考图不存在: {ref}")
        return 4
    key = os.getenv("DASHSCOPE_API_KEY") or ""
    if not key and not args.dry_run:
        print("[!] 未配置 DASHSCOPE_API_KEY —— **未发起任何请求**（这不是失败）")
        return 2

    arm = ARMS[args.arm]
    # 三种取提示词的方式，**用途不同，别混**：
    #   arm          —— 两条人写臂的原文（A/B 单变量对照）
    #   --lock-file  —— 只替换锁段，场景段与负面词仍取 --arm 的（C1/C2 只换"锁段由谁写"）
    #   --prompt-file—— 整段提示词直接来自文件（编译器的产出含锁段+场景段，不能再拼一次场景段，
    #                   否则同一段场景会出现两次，那就不是"编译器产出"的对照了）
    lock = arm["lock"]
    lock_source = f"arm:{args.arm}"
    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8").strip()
        lock = prompt
        lock_source = f"prompt-file:{args.prompt_file}"
    else:
        if args.lock_file:
            lock = Path(args.lock_file).read_text(encoding="utf-8").strip()
            lock_source = f"file:{args.lock_file}"
        prompt = lock + " " + arm["scene"]
    # 目录名 = 这次实验的身份。**必须能把不同臂分开**：
    # 曾经只用 `arm + "__filelock"`，结果两臂（C1 text / C2 vision）都落到同一个目录、
    # r1..r3 互相覆盖，臂 B 的原始产物也在隔壁等着被踩。--tag 是那次教训的产物。
    tag = args.tag or (args.arm
                       + ("__filelock" if args.lock_file else "")
                       + ("__promptfile" if args.prompt_file else ""))
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    tried: list[dict] = []
    for endpoint, model in CANDIDATES:
        out_dir = out_root / f"{tag}_{model}"
        out_dir.mkdir(parents=True, exist_ok=True)
        body = build_body(endpoint, model, ref, prompt, arm["neg"], args.n,
                          args.size, args.prompt_extend)
        if args.dry_run:
            shown = json.loads(json.dumps(body))
            for c in shown["input"]["messages"][0]["content"]:
                if "image" in c:
                    c["image"] = c["image"][:48] + f"...({len(c['image'])} chars)"
            print(f"--- dry-run · {model} · {endpoint}")
            print(json.dumps(shown, ensure_ascii=False, indent=2))
            print(f"\n参考图 {ref.name} {ref.stat().st_size} 字节 · 提示词 {len(prompt)} 字 · n={args.n}")
            return 0

        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        t0 = time.time()
        r = post_retry(endpoint, headers, body)
        elapsed = round(time.time() - t0, 1)
        if r.status_code != 200:
            tried.append({"model": model, "endpoint": endpoint,
                          "status": r.status_code, "error": r.text[:300]})
            print(f"[~] {model} HTTP {r.status_code} —— 试下一个候选")
            continue

        payload = r.json()
        task_id = (payload.get("output") or {}).get("task_id")
        if task_id:                      # 异步族
            payload = poll(task_id, headers)
        urls = extract_images(payload)
        if not urls:
            tried.append({"model": model, "endpoint": endpoint, "status": 200,
                          "error": f"未返回图片: {json.dumps(payload)[:300]}"})
            print(f"[~] {model} 返回 200 但无图片 —— 试下一个候选")
            continue

        files: list[Path] = []
        for i, u in enumerate(urls, 1):
            dst = out_dir / f"{model}_r{i}.png"
            if u.startswith("http"):
                ir = requests.get(u, timeout=120)
                ir.raise_for_status()
                Image.open(io.BytesIO(ir.content)).convert("RGB").save(dst)
            else:                        # 直接回 base64
                raw = base64.b64decode(u.split(",", 1)[-1])
                Image.open(io.BytesIO(raw)).convert("RGB").save(dst)
            files.append(dst)

        hashes = {p.name: dhash(p) for p in files}
        names = [p.name for p in files]
        pair = [{"a": names[i], "b": names[j],
                 "hamming": hamming(hashes[names[i]], hashes[names[j]]),
                 "bits": len(hashes[names[i]])}
                for i in range(len(names)) for j in range(i + 1, len(names))]
        src_h = dhash(ref)
        vs_source = [{"file": n, "hamming_vs_source": hamming(hashes[n], src_h),
                      "bits": len(src_h),
                      "note": "非判据：源图是白底单品，产物是场景图，这个数必然大"} for n in names]

        sheet = contact_sheet([ref] + files, out_dir / "contact_sheet.jpg")
        report = {
            "probe": "lock_probe",
            "purpose": "同一参考图+同一锁段出 n 张 —— 商品有没有被改（**判断项在人**）",
            "arm": args.arm, "arm_why": arm["why"],
            "model": model, "endpoint": endpoint, "task_id": task_id,
            "n_requested": args.n, "n_received": len(files),
            "size": args.size, "prompt_extend": args.prompt_extend,
            "elapsed_s": elapsed,
            "reference": {"path": str(ref), "dhash": src_h},
            "files": [str(p) for p in files],
            "contact_sheet": str(sheet),
            "pairwise_hamming": pair,
            "vs_source_hamming": vs_source,
            "prompt_lock": lock, "lock_source": lock_source,
            "lock_chars": len(lock),
            "prompt_scene": arm["scene"],
            "negative_prompt": arm["neg"],
            "attest_required": {
                "by": "", "date": "", "confirmed": [],
                "items": ["轮廓一致", "图案位置与数量一致", "颜色一致",
                          "材质纹理一致", "比例一致", "无自造文字/水印"],
                "why": "机器判不了的项要求签字，不写启发式检测器（照 E0 ATTEST_ITEMS）",
            },
        }
        (out_dir / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        print(f"[ok] {model} · {len(files)} 张 · {elapsed}s · 落盘 {out_dir}")
        print(f"     对照图 {sheet.name}（SOURCE + {len(files)} 张，并排）")
        print(f"     自洽性（两两 dHash 距离/256，**上界**）: "
              + " · ".join(f"{p['a'][-8:]}↔{p['b'][-8:]}={p['hamming']}" for p in pair))
        print("     ★ 商品有没有被改 —— 机器判不了，请人看对照图并签字")
        return 0

    (out_dir / "tried.json").write_text(
        json.dumps(tried, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[x] 全部候选失败（{len(tried)} 个）。逐个响应已落盘 {out_dir / 'tried.json'}")
    for t in tried:
        print(f"    {t['model']} @ {t['endpoint'].rsplit('/', 2)[-2]}/ → {t['status']}: {t['error'][:120]}")
    return 3


def main() -> int:
    ap = argparse.ArgumentParser(description="锁探针（实验，不进 pipeline）")
    ap.add_argument("--image", default=str(DEFAULT_IMAGE))
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--size", default="1600*1600")
    ap.add_argument("--model", default=None, help="指定则只试这一个（与 CANDIDATES 里的端点配对）")
    ap.add_argument("--arm", default=DEFAULT_ARM, choices=sorted(ARMS),
                    help="锁段写法：advice=笼统嘱咐 / enumerated=逐特征枚举+显式否定")
    ap.add_argument("--prompt-extend", action="store_true",
                    help="开则模型会改写提示词（**锁段可能被改写**，默认关）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--lock-file", default=None,
                    help="只替换锁段（场景段与负面词仍取 --arm）。用它与 --arm 做「只换锁段」对照")
    ap.add_argument("--tag", default=None,
                    help="产物目录名。**用了 --lock-file / --prompt-file 就必须给**，"
                         "否则不同臂会互相覆盖")
    ap.add_argument("--prompt-file", default=None,
                    help="整段提示词直接取自文件（不再拼 --lock-file / --arm 的场景段）。"
                         "编译器的产出含锁段+场景段，必须走这个而不是 --lock-file")
    args = ap.parse_args()
    if args.model:
        global CANDIDATES
        CANDIDATES = [(MULTIMODAL_URL, args.model)]
    return run_once(args)


if __name__ == "__main__":
    raise SystemExit(main())
