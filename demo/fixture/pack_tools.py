# -*- coding: utf-8 -*-
"""参考包只读校验器与人读预览（D0.4）。

    python demo/fixture/pack_tools.py verify  --project .
    python demo/fixture/pack_tools.py preview --project .

verify  只读：缺文件、哈希漂移、尺寸不符、免责声明缺失、机器判据缺派生记录，一律拒绝 READY，
        并指名确切对象。它不修改任何资产 —— 「校验失败顺手修一下」正是把证据变成传说的做法。
preview 是全文件里唯一会写的动作，且只写 pack/preview.html；内容完全由 manifest 决定，
        所以同样的 manifest 必然生成同样的页面（可被哈希核对）。

退出码：0 READY / 2 结构或文件问题 / 3 哈希与绑定漂移 / 4 事实卡与派生记录不一致
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

PACK_SUB = "evals/product-demo/fixture-design/pack"
CARD_SUB = "demo/fixture/aster-01/product.json"
DERIV_SUB = "demo/fixture/aster-01/threshold-derivation.json"
FIXTURE_SUB = "demo/fixture"
PROV_NAME = "pack-provenance.json"
MANIFEST_NAME = "reference-manifest.json"
PREVIEW_NAME = "preview.html"
# 下面三个是**本夹具工具的默认包**（CLI 不带 --pack 时的默认值）；产品层不接受
# 这些常量当身份 —— 参考包由商品包里的 reference_pack.json 声明（见 demo/core/packages.py）。
PROV_SUB = PACK_SUB + "/" + PROV_NAME
MANIFEST_SUB = PACK_SUB + "/" + MANIFEST_NAME
PREVIEW_SUB = PACK_SUB + "/" + PREVIEW_NAME

REQUIRED_FACTS = ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8"]
REQUIRED_VIEWS = ["front-full", "upper-closeup", "lower-detail"]
MIN_LONG_SIDE = 1024

EXIT_READY, EXIT_STRUCTURAL, EXIT_DRIFT, EXIT_CONTENT = 0, 2, 3, 4


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def png_info(path: Path):
    with Image.open(path) as im:
        im.verify()
    with Image.open(path) as im:
        return list(im.size), im.format


def verify(root: Path, pack_sub: str = PACK_SUB) -> tuple[int, dict]:
    """校验一个冻结参考包。pack_sub 由调用方给 —— 商品包声明它用哪个包。"""
    rep: dict = {"structural": [], "drift": [], "content": [], "notes": []}
    pack = root / pack_sub

    def structural(msg):
        rep["structural"].append(msg)

    def drift(msg):
        rep["drift"].append(msg)

    def content(msg):
        rep["content"].append(msg)

    prov_path, man_path = pack / PROV_NAME, pack / MANIFEST_NAME
    for p, label in ((prov_path, "pack-provenance.json"), (man_path, "reference-manifest.json")):
        if not p.exists():
            structural("缺文件：" + p.relative_to(root).as_posix())
    if rep["structural"]:
        return EXIT_STRUCTURAL, rep

    prov, man = load_json(prov_path), load_json(man_path)

    # ── 视图：存在 → 哈希 → 尺寸。三层按顺序报，不跳级 ──
    prov_by_id = {v["view_id"]: v for v in prov.get("views", [])}
    man_by_id = {v["view_id"]: v for v in man.get("views", [])}
    for vid in REQUIRED_VIEWS:
        if vid not in man_by_id:
            structural("manifest 缺必需视图：" + vid)
        if vid not in prov_by_id:
            structural("provenance 缺必需视图：" + vid)
    for vid, mv in man_by_id.items():
        p = root / mv["file"]
        if not p.exists():
            structural("缺视图文件：" + mv["file"])
            continue
        actual = sha256_file(p)
        if actual != mv["sha256"]:
            drift("视图哈希漂移：" + mv["file"] + " manifest=" + mv["sha256"][:16]
                  + " 实际=" + actual[:16])
        pv = prov_by_id.get(vid)
        if pv and pv.get("sha256") != mv.get("sha256"):
            drift("provenance 与 manifest 对 " + vid + " 的哈希不一致")
        try:
            size, fmt = png_info(p)
        except Exception as exc:  # 解码失败就是结构问题，不是漂移
            structural("无法解码：" + mv["file"] + "（" + type(exc).__name__ + "）")
            continue
        if size != mv.get("image_size"):
            structural("尺寸与 manifest 不符：" + mv["file"] + " 记录=" + str(mv.get("image_size"))
                       + " 实际=" + str(size))
        if max(size) < MIN_LONG_SIDE:
            structural("长边不足：" + mv["file"] + " = " + str(max(size)) + " < " + str(MIN_LONG_SIDE))
        if fmt != "PNG":
            structural("格式不是 PNG：" + mv["file"] + " = " + str(fmt))

    # ── 参考板 ──
    board = man.get("board", {})
    bp = root / str(board.get("file", ""))
    if not board.get("file") or not bp.exists():
        structural("缺参考板：" + str(board.get("file")))
    else:
        if sha256_file(bp) != board.get("sha256"):
            drift("参考板哈希漂移：" + str(board["file"]))
        try:
            if png_info(bp)[0] != board.get("image_size"):
                structural("参考板尺寸与 manifest 不符：" + str(board["file"]))
        except Exception as exc:
            structural("参考板无法解码：" + type(exc).__name__)

    # ── 事实卡 ──
    fc = man.get("fact_card", {})
    cp = root / str(fc.get("file", ""))
    card = None
    if not fc.get("file") or not cp.exists():
        structural("缺事实卡：" + str(fc.get("file")))
    else:
        if sha256_file(cp) != fc.get("sha256"):
            drift("事实卡哈希漂移：" + str(fc["file"]))
        card = load_json(cp)
        if card.get("version") != fc.get("version"):
            drift("事实卡版本与 manifest 不符：卡=" + str(card.get("version"))
                  + " manifest=" + str(fc.get("version")))
        ids = [f.get("id") for f in card.get("facts", [])]
        if ids != REQUIRED_FACTS:
            content("事实 id 不是 F1–F8 的完整有序集合：" + str(ids))
        if not card.get("unknowns"):
            content("事实卡没有登记未知字段（Unknown 不能省）")
        if card.get("fact_source") != fc.get("fact_source"):
            content("fact_source 不一致：卡=" + str(card.get("fact_source"))
                    + " manifest=" + str(fc.get("fact_source")))

    # ── 阈值派生：卡里的每个机器判据都要有派生记录，反之派生记录也不许指向已删的判据 ──
    dv = man.get("threshold_derivation", {})
    dp = root / str(dv.get("file", ""))
    deriv = None
    if not dv.get("file") or not dp.exists():
        structural("缺阈值派生记录：" + str(dv.get("file")))
    else:
        if sha256_file(dp) != dv.get("sha256"):
            drift("阈值派生记录哈希漂移：" + str(dv["file"]))
        deriv = load_json(dp)
    if card is not None and deriv is not None:
        have = {(e["fact"], e["metric"]) for e in deriv.get("entries", []) if e.get("gating")}
        for fact in card.get("facts", []):
            for chk in fact.get("machine_checks") or []:
                if (fact["id"], chk["metric"]) not in have:
                    content("机器判据缺派生记录：" + fact["id"] + "/" + chk["metric"])
        card_keys = {(f["id"], c["metric"]) for f in card.get("facts", [])
                     for c in (f.get("machine_checks") or [])}
        for key in sorted(have - card_keys):
            content("派生记录指向已不存在的判据：" + key[0] + "/" + key[1])

    # ── 免责声明：provenance 与 manifest 必须一致且非空 ──
    pd, md = str(prov.get("disclaimer") or ""), str(man.get("disclaimer") or "")
    if not pd or not md:
        content("免责声明缺失：provenance=" + repr(pd) + " manifest=" + repr(md))
    elif pd != md:
        content("免责声明不一致：provenance=" + repr(pd) + " manifest=" + repr(md))

    # ── 预览页 ──
    pp = pack / PREVIEW_NAME
    if not pp.exists():
        structural("缺预览页：" + pack_sub + "/" + PREVIEW_NAME + "（先跑 preview）")
    else:
        text = pp.read_text(encoding="utf-8")
        if md and md not in text:
            content("预览页缺免责声明：" + pack_sub + "/" + PREVIEW_NAME)
        for mv in man_by_id.values():
            if os.path.basename(mv["file"]) not in text:
                structural("预览页没有引用视图：" + mv["file"])

    if rep["content"]:
        return EXIT_CONTENT, rep
    if rep["drift"]:
        return EXIT_DRIFT, rep
    if rep["structural"]:
        return EXIT_STRUCTURAL, rep
    return EXIT_READY, rep


def render_preview(man: dict, prov: dict, card: dict, deriv: dict) -> str:
    """页面内容只由 manifest / 卡 / 派生记录决定，不含当前时间 —— 同样的输入必然产出同样的字节。"""
    esc = html.escape

    rows = []
    for v in man["views"]:
        w, h = v["image_size"]
        rows.append(
            "<tr><td><code>" + esc(v["view_id"]) + "</code></td><td>" + esc(v["role"])
            + "</td><td>" + str(w) + "×" + str(h) + "</td><td><code>"
            + esc(v["sha256"][:16]) + "</code></td></tr>")

    gates = []
    for e in deriv["entries"]:
        if not e.get("gating"):
            continue
        gates.append("<tr><td>" + esc(e["fact"]) + "</td><td><code>" + esc(e["metric"])
                     + "</code></td><td><code>" + esc(json.dumps(e["pass"], ensure_ascii=False))
                     + "</code></td><td><code>" + esc(json.dumps(e["sample"], ensure_ascii=False))
                     + "</code></td></tr>")

    diagnostics = []
    for e in deriv["entries"]:
        if e.get("gating"):
            continue
        diagnostics.append("<tr><td>" + esc(e["fact"]) + "</td><td><code>" + esc(e["metric"])
                           + "</code></td><td><code>"
                           + esc(json.dumps(e["sample"], ensure_ascii=False)) + "</code></td></tr>")

    gaps = "".join("<li><b>" + esc(g["fact"]) + "</b> 缺「" + esc(g["missing"]) + "」→ "
                   + esc(str(g.get("assigned_to", ""))) + "</li>" for g in deriv.get("gaps", []))
    unknowns = "".join("<li><b>" + esc(u["field"]) + "</b> = Unknown（" + esc(u["why"]) + "）</li>"
                       for u in card.get("unknowns", []))
    boundaries = "".join("<li>" + esc(b) + "</li>" for b in man.get("boundaries", []))

    disclaimer = esc(man["disclaimer"])
    board = esc(os.path.basename(man["board"]["file"]))

    return "\n".join([
        "<!doctype html>",
        '<html lang="zh-CN"><head><meta charset="utf-8">',
        "<title>" + esc(man["display_name"]) + " 参考包预览</title>",
        "<style>body{font-family:system-ui,'Microsoft YaHei',sans-serif;max-width:1100px;"
        "margin:24px auto;padding:0 16px;color:#222;line-height:1.5}"
        ".warn{background:#fff3f0;border-left:6px solid #c0392b;padding:10px 14px;font-weight:600}"
        "table{border-collapse:collapse;width:100%;margin:12px 0}"
        "th,td{border:1px solid #ddd;padding:6px 8px;font-size:14px;text-align:left}"
        "th{background:#f5f5f5}img{max-width:100%;border:1px solid #ddd}"
        "code{background:#f6f6f6;padding:1px 4px}</style></head><body>",
        "<h1>" + esc(man["display_name"]) + " 参考包预览</h1>",
        '<p class="warn">' + disclaimer + "</p>",
        "<p>SKU <code>" + esc(man["product_sku"]) + "</code> · 媒体类别 <code>"
        + esc(man["media_class"]) + "</code> · 包版本 <code>" + esc(man["pack"]["pack_version"])
        + "</code> · manifest <code>" + esc(man["manifest_version"]) + "</code></p>",
        "<h2>人读参考板</h2>",
        '<img src="' + board + '" alt="reference board">',
        "<h2>三个模型输入视图</h2>",
        "<table><tr><th>视图</th><th>职责</th><th>尺寸</th><th>sha256(前16)</th></tr>"
        + "".join(rows) + "</table>",
        "<h2>视图原图</h2>",
        "".join('<figure><img src="' + esc(os.path.basename(v["file"]))
                + '" alt="' + esc(v["view_id"]) + '"><figcaption><code>' + esc(v["view_id"])
                + "</code> · " + esc(v["role"]) + "</figcaption></figure>" for v in man["views"]),
        "<h2>机器判据与验收档（每个阈值都有派生记录）</h2>",
        "<table><tr><th>事实</th><th>判据</th><th>通过档</th><th>A/B/C 现场样本</th></tr>"
        + "".join(gates) + "</table>",
        "<h2>登记读数（不参与判定）</h2>",
        "<table><tr><th>事实</th><th>读数</th><th>A/B/C 现场样本</th></tr>"
        + "".join(diagnostics) + "</table>",
        "<h2>机器判据尚未覆盖的项</h2><ul>" + gaps + "</ul>",
        "<h2>未知字段（保持 Unknown）</h2><ul>" + unknowns + "</ul>",
        "<h2>本包不能证明什么</h2><ul>" + boundaries + "</ul>",
        "<p>生成方式：<code>python demo/fixture/pack_tools.py preview --project .</code>；"
        "核对：<code>python demo/fixture/pack_tools.py verify --project .</code></p>",
        "</body></html>",
        "",
    ])


def _sandbox_copy(root: Path, dest: Path) -> None:
    """把参考包与**全部商品数据包**复制进沙箱。

    沙箱必须是一个能被包解析器解析的迷你项目：只复制数据（包目录整体复制，跳过
    __pycache__），不复制 .py —— 反例注入改的是数据，不是代码。
    """
    shutil.copytree(root / PACK_SUB, dest / PACK_SUB)
    src = root / FIXTURE_SUB
    for d in sorted(p for p in src.iterdir() if p.is_dir() and p.name != "__pycache__"):
        shutil.copytree(d, dest / FIXTURE_SUB / d.name,
                        ignore=shutil.ignore_patterns("__pycache__"))


def _drop_disclaimer(d: Path) -> None:
    man = load_json(d / MANIFEST_SUB)
    man.pop("disclaimer", None)
    (d / MANIFEST_SUB).write_text(json.dumps(man, ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8")


def _drop_view(d: Path) -> None:
    man = load_json(d / MANIFEST_SUB)
    (d / man["views"][0]["file"]).unlink()


def _append_byte(d: Path) -> None:
    """在 PNG 尾部追加一个字节：IEND 之后的内容被解码器忽略，所以尺寸不变、只有哈希变了。"""
    man = load_json(d / MANIFEST_SUB)
    with (d / man["views"][1]["file"]).open("ab") as fh:
        fh.write(b"\x00")


def _drop_derivation(d: Path) -> None:
    """删掉一条机器判据的派生记录，并把 manifest 里的派生文件哈希同步改掉 ——
    只留「判据缺派生」这一个问题，否则这一向会同时撞上哈希漂移，变成两报。"""
    der = load_json(d / DERIV_SUB)
    for i, e in enumerate(der["entries"]):
        if e.get("gating"):
            der["entries"].pop(i)
            break
    (d / DERIV_SUB).write_text(json.dumps(der, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    man = load_json(d / MANIFEST_SUB)
    man["threshold_derivation"]["sha256"] = sha256_file(d / DERIV_SUB)
    (d / MANIFEST_SUB).write_text(json.dumps(man, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def self_test(root: Path, keep: bool = False) -> int:
    """把参考包复制到临时沙箱里植入违规，逐向核对校验器是否只报该报的那一类。"""
    tool = Path(__file__).resolve()
    base = Path(tempfile.mkdtemp(prefix="pack_selftest_"))
    cases = [
        ("A 基线（不改）", None, EXIT_READY),
        ("B 删掉一个视图文件", _drop_view, EXIT_STRUCTURAL),
        ("C 在视图尾部追加一个字节", _append_byte, EXIT_DRIFT),
        ("D 抹掉 manifest 的免责声明", _drop_disclaimer, EXIT_CONTENT),
        ("E 删掉一条机器判据的派生记录", _drop_derivation, EXIT_CONTENT),
    ]
    bad = 0
    for i, (name, mutate, want) in enumerate(cases):
        d = base / ("case" + str(i))
        d.mkdir(parents=True, exist_ok=True)
        _sandbox_copy(root, d)
        if mutate is not None:
            mutate(d)
        p = subprocess.run([sys.executable, str(tool), "verify", "--project", str(d)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        ok = p.returncode == want
        if not ok:
            bad += 1
        print(("OK  " if ok else "FAIL") + " " + name + " → rc=" + str(p.returncode)
              + "（期望 " + str(want) + "）")
        if not ok:
            print("     " + (p.stdout or "").strip().replace("\n", "\n     ")[:600])
    if keep:
        print("沙箱保留在 " + str(base))
    else:
        tmp_root = Path(tempfile.gettempdir()).resolve()
        if tmp_root in base.resolve().parents:
            shutil.rmtree(base, ignore_errors=True)
        else:
            print("沙箱不在临时目录下，拒绝删除：" + str(base))
    print("OK：5 向全部与预期一致，且每向只报该报的那一类" if bad == 0
          else "FAIL：" + str(bad) + " / 5 向与预期不符 —— 校验器的判据有问题")
    return 0 if bad == 0 else 1


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["verify", "preview", "self-test"])
    ap.add_argument("--project", required=True)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--keep", action="store_true", help="self-test 保留沙箱，便于人工查看")
    args = ap.parse_args()
    root = Path(args.project).resolve()

    if args.mode == "self-test":
        return self_test(root, keep=args.keep)

    if args.mode == "preview":
        man = load_json(root / MANIFEST_SUB)
        prov = load_json(root / PROV_SUB)
        card = load_json(root / CARD_SUB)
        deriv = load_json(root / DERIV_SUB)
        out = root / PREVIEW_SUB
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_preview(man, prov, card, deriv), encoding="utf-8")
        print("wrote " + PREVIEW_SUB + " sha256=" + sha256_file(out)[:16])
        return 0

    code, rep = verify(root)
    if args.json:
        print(json.dumps({"exit": code, "report": rep}, ensure_ascii=False, indent=2))
    else:
        for kind in ("structural", "drift", "content"):
            for msg in rep[kind]:
                print("FAIL[" + kind + "] " + msg)
        if code == 0:
            print("READY: 参考包与 manifest、事实卡、派生记录一致")
        else:
            print("NOT_READY exit=" + str(code)
                  + " structural=" + str(len(rep["structural"]))
                  + " drift=" + str(len(rep["drift"]))
                  + " content=" + str(len(rep["content"])))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
