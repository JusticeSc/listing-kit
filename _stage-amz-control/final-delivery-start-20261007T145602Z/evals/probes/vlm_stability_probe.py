"""VLM 读数稳定性 —— 锁段的每个正向特征都来自它，它自己一致吗？

为什么必须验
------------
`slots-v4` §3.4 撞出：**正向断言会被模型执行，即使它是错的**（C1 把卖点写成
`coating applied to the entire outer surface`，商品被整片盖掉）。修法是"外观断言只许来自
参考图描述"—— 于是 VLM 读数成了锁段**唯一**的外观事实来源。
那么它读错一次，锁段就系统性写错一次。§3.4 实测它把棕色矮套判成占总高 `0.85–1.0`（实际约 `0.6`）。

原计划的"跨模型对照"**不可行** —— 三个候选里两个 403。本探针把这件事本身变成脚本产出：
先探测模型可用性，再把对照降级为**同模型重复读**。

判据（可证伪）
--------------
- 若同一张图连读 N 次，关键字段（各段起止比例 / 颜色 / 结构布尔）**不一致**
  ⇒ 锁段的事实基础是不可复现的，必须固定 `temperature=0` 或改由人判。
- 若按结构报数字（本探针的提问方式）比自由散文（`VLM_INSTRUCT`）更稳
  ⇒ 结论是"提问方式要结构化"，不只是"换个温度"。

用法
----
    python evals/probes/vlm_stability_probe.py --dry-run          # 不花钱
    python evals/probes/vlm_stability_probe.py                    # N=3，默认温度
    python evals/probes/vlm_stability_probe.py --n 3 --temperature 0

退出码：0 跑完 · 2 无 key（**未发起请求**）· 3 调用失败 · 5 全部输出无法解析
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import prompt_enhance_probe as pe  # 复用 call_chat / data_uri / extract_json（单一出处）

REF = pe.DEFAULT_REF
OUT = HERE / "vlm_stability"

# 提问方式：**要求结构化 JSON**。这本身就是被测变量之一 ——
# 自由散文（pe.VLM_INSTRUCT）无法逐字段比对，只能人肉读。
ASK = """Look ONLY at the product in this image (ignore background, props and any watermark).
Answer with ONE JSON object and nothing else. Keys exactly these:

{
  "product_type": "noun phrase",
  "height_to_width_ratio": "x.xx:1",
  "sections_top_to_bottom": [
    {"name": "...", "starts_at_height_frac": "0.00", "ends_at_height_frac": "1.00",
     "colour": "...", "finish": "..."}
  ],
  "lid_layers": ["...", "..."],
  "has_handle": false,
  "has_spout": false,
  "has_second_cap": false,
  "has_printed_text_or_logo": false,
  "prop_present": ["..."],
  "uncertain": ["..."]
}

All fractions and ratios as strings with two decimals, measured on the product's own
bounding box (top of product = 0.00, bottom of product = 1.00). No markdown, no commentary."""

# 逐字段比对时，哪些字段是"判据字段"（不一致就说明锁段的事实基础不稳）
KEY_FIELDS = ["product_type", "height_to_width_ratio", "has_handle", "has_spout",
              "has_second_cap", "has_printed_text_or_logo"]


def norm(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v).strip().lower()


def sections_sig(secs) -> str:
    """把分节压成一个可比的签名字符串：数量 + 各段起止 + 颜色。"""
    if not isinstance(secs, list):
        return f"<{type(secs).__name__}>"
    parts = []
    for s in secs:
        if not isinstance(s, dict):
            continue
        parts.append(f"{s.get('starts_at_height_frac')}-{s.get('ends_at_height_frac')}:{norm(s.get('colour'))}")
    return f"n={len(secs)} | " + " | ".join(parts)


def probe_models(key: str) -> list[dict]:
    """模型可用性探测：把"跨模型对照不可行"变成脚本自己产出的证据。"""
    res = []
    brief = [{"role": "user", "content": "hi"}]
    for m in pe.VISION_MODELS:
        try:
            pe.call_chat(m, brief, key, timeout=30)
            res.append({"model": m, "usable": True, "error": None})
        except Exception as exc:
            res.append({"model": m, "usable": False, "error": str(exc)[:120]})
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description="VLM 读数稳定性探针（同模型重复读）")
    ap.add_argument("--ref", default=str(REF))
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--temperature", type=float, default=None,
                    help="不传 = 沿用服务端默认（与现状一致）")
    ap.add_argument("--model", default=None, help="只用这一个（默认按 VISION_MODELS 逐个试）")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    msg = [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": pe.data_uri(Path(args.ref))}},
        {"type": "text", "text": ASK}]}]

    if args.dry_run:
        print("[dry-run] 将发出的请求：")
        print(f"  ref   {args.ref}")
        print(f"  模型  {args.model or pe.VISION_MODELS}")
        print(f"  n     {args.n}   temperature={args.temperature}")
        print(f"  提问  {len(ASK)} 字符，要求单 JSON 对象、字段固定")
        print(f"  字段  {KEY_FIELDS}")
        print("  注意：真实调用会重复 N 次**同一张图 + 同一提问**（单变量 = 采样噪声）")
        return 0

    key = os.getenv("DASHSCOPE_API_KEY") or ""
    if not key:
        print("[!] 未配置 DASHSCOPE_API_KEY —— **未发起任何请求**（这不是失败）")
        return 2

    print("模型可用性探测：")
    avail = probe_models(key)
    for a in avail:
        print(f"  {'OK ' if a['usable'] else 'NO '} {a['model']:24s} {a['error'] or ''}")
    usable = [a["model"] for a in avail if a["usable"]]
    if args.model:
        usable = [args.model]
    if not usable:
        print("[x] 没有任何可用的 VLM")
        return 3

    runs = []
    for i in range(args.n):
        models = usable
        t0 = time.time()
        raw = model = None
        tried = []
        for m in models:
            try:
                if args.temperature is None:
                    raw, usage = pe.call_chat(m, msg, key)
                else:
                    import requests
                    body = {"model": m, "messages": msg, "temperature": args.temperature}
                    r = requests.post(pe.CHAT_URL,
                                      headers={"Authorization": f"Bearer {key}",
                                               "Content-Type": "application/json"},
                                      json=body, timeout=180)
                    r.raise_for_status()
                    d = r.json()
                    raw, usage = d["choices"][0]["message"]["content"], d.get("usage") or {}
                model = m
                break
            except Exception as exc:
                tried.append({"model": m, "error": str(exc)[:160]})
        if raw is None:
            print(f"[x] 第 {i+1} 次全部失败：{tried}")
            return 3
        el = round(time.time() - t0, 1)
        (out_dir / f"run{i+1:02d}_raw.txt").write_text(raw + "\n", encoding="utf-8")
        try:
            parsed = pe.extract_json(raw)
            err = None
        except Exception as exc:
            parsed, err = None, str(exc)[:200]
        runs.append({"run": i + 1, "model": model, "elapsed_s": el, "usage": usage,
                     "tried": tried, "parse_error": err, "parsed": parsed})
        print(f"[ok] run{i+1} · {model} · {el}s · "
              f"{'解析成功' if parsed else '**解析失败** ' + str(err)}")

    ok = [r for r in runs if r["parsed"]]
    if not ok:
        print("[x] 全部输出无法解析 —— 这本身是结果（JSON 稳健性）")
        return 5

    print(f"\n一致性（N={len(ok)} 次成功解析）：")
    report = {"probe": "vlm_stability", "ref": args.ref, "n_requested": args.n,
              "temperature": args.temperature, "model_availability": avail,
              "runs": runs, "agreement": {}}

    field_rows = {}
    for f in KEY_FIELDS:
        vals = [norm(r["parsed"].get(f)) for r in ok]
        uniq = sorted(set(vals))
        field_rows[f] = vals
        mark = "一致" if len(uniq) == 1 else f"**不一致 {len(uniq)} 种**"
        print(f"  {f:26s} {mark:18s} {uniq}")
    report["agreement"]["key_fields"] = field_rows

    ssec = [sections_sig(r["parsed"].get("sections_top_to_bottom")) for r in ok]
    print(f"\n  分节签名（判据字段，最要紧）：")
    for i, s in enumerate(ssec):
        print(f"    run{i+1}: {s}")
    report["agreement"]["sections_signature"] = ssec
    report["agreement"]["sections_identical"] = len(set(ssec)) == 1

    # 数字量单独看：矮套起点这类"实测出过错"的量
    fracs = []
    for r in ok:
        secs = r["parsed"].get("sections_top_to_bottom") or []
        fracs.append([s.get("starts_at_height_frac") for s in secs if isinstance(s, dict)])
    report["agreement"]["section_start_fracs"] = fracs
    print(f"\n  各段起点比例：")
    for i, f in enumerate(fracs):
        print(f"    run{i+1}: {f}")

    report["agreement"]["all_fields_identical"] = all(
        len(set(v)) == 1 for v in field_rows.values()) and report["agreement"]["sections_identical"]
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                        encoding="utf-8")
    print(f"\n[ok] 落盘 {out_dir/'report.json'}")
    print(f"     全部关键字段一致：{report['agreement']['all_fields_identical']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
