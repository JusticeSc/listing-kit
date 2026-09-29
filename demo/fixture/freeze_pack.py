# -*- coding: utf-8 -*-
"""D0.2 参考包冻结器 —— 确定性、零模型调用。

做四件事：
  1. 把三个已生成视图逐字节复制进 pack/（内容相同则幂等跳过，内容不同则拒绝覆盖）
  2. 复制后重新计算源与目标的 sha256 并逐条比对，同时核对 meta 里声明的哈希
  3. 生成 2x3 人读参考板：上排三视图，下排局部重采样放大并标注「插值放大、不新增信息」
  4. 写 pack-provenance.json，来源字段全部从各 meta.json 读取，不手写 task id

边界：本步骤只证明「字节复制正确、长边达标、来源可追溯」。
      「无文字/水印」是人工视觉判断：本脚本只把状态与确认记录写进 provenance，
     不代替人做这个判断，也不再把它写死在参考板上。
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CST = timezone(timedelta(hours=8))
MIN_LONG_SIDE = 1024

# ── 「无文字/水印」这项人工判断的状态与确认记录 ──
# 本脚本是**生成器**，不代替人做判断；它只把这份记录写进 pack-provenance.json。
# 确认一旦发生就是历史事实，所以写成常量：重跑本脚本不会改变它。
HUMAN_REVIEW = {
    "item": "no_visible_text_or_watermark",
    "status": "confirmed_by_initiator_2026-09-25",
    "scope": "三张视图里的商品外表面（不含参考板自身的标注文字）",
    "reviewer_role": "项目发起人",
    "confirmed_at": "2026-09-25T23:54:55+08:00",
    "basis": "发起人看过三张视图与操作者复核结论后回复「同意你的判断，继续尽最大努力交付最终产品」",
    "operator_review": "操作者逐张目视复核：未在商品外表发现文字、数字、Logo、标签或水印",
    "machine_corroboration": "三张视图来源元数据 watermark_flag=false（模型自报，仅作佐证，不是独立核验）",
    "does_not_prove": "不证明真实商品、不证明 Amazon 实际审核通过",
}
PACK_SUBDIR = Path("evals/product-demo/fixture-design/pack")
SOURCE_SUBDIR = Path("evals/product-demo/fixture-design")

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhl.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
]

VIEWS = [
    {
        "view_id": "front-full",
        "dest": "01-front-full.png",
        "role": "正面闭盖全身（F1/F2/F6 主证据）",
        "image": "C/raw.png",
        "meta": "C/meta.json",
        "crop": [0.28, 0.06, 0.72, 0.50],
    },
    {
        "view_id": "upper-closeup",
        "dest": "02-upper-closeup.png",
        "role": "上部与杯盖近景（F4/F5 主证据）",
        "image": "ref-02-upper-closeup/raw.png",
        "meta": "ref-02-upper-closeup/meta.json",
        "crop": [0.16, 0.06, 0.84, 0.74],
    },
    {
        "view_id": "lower-detail",
        "dest": "03-lower-detail.png",
        "role": "防滑套与底部近景（F3/F6 主证据）",
        "image": "ref-03-lower-detail/raw.png",
        "meta": "ref-03-lower-detail/meta.json",
        "crop": [0.16, 0.30, 0.84, 0.98],
    },
]

CELL = 420
GAP = 24
MARGIN = 36
LABEL_H = 34
TITLE_H = 58
CAPTION_H = 92


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stamp() -> str:
    return datetime.now(CST).replace(microsecond=0).isoformat()


def pick_font(size: int):
    for cand in FONT_CANDIDATES:
        p = Path(cand)
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except OSError:
                continue
    raise SystemExit("找不到可用的中文字体，试过：" + "、".join(FONT_CANDIDATES))


def resample():
    return getattr(Image, "Resampling", Image).LANCZOS


def fit(img: Image.Image, cell: int) -> Image.Image:
    """等比缩放并居中留白。参考板用于人眼判断比例，绝不能拉伸。"""
    w, h = img.size
    s = min(cell / w, cell / h)
    nw, nh = max(1, int(round(w * s))), max(1, int(round(h * s)))
    out = Image.new("RGB", (cell, cell), (255, 255, 255))
    out.paste(img.resize((nw, nh), resample()), ((cell - nw) // 2, (cell - nh) // 2))
    return out


def load_meta(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def freeze_views(root: Path, pack: Path) -> list[dict]:
    """逐字节复制并对哈希；目标已存在且内容不同时拒绝覆盖，不让「重跑」变成改证据。"""
    src_dir = root / SOURCE_SUBDIR
    pack.mkdir(parents=True, exist_ok=True)
    out = []
    for spec in VIEWS:
        src_img = src_dir / spec["image"]
        src_meta = src_dir / spec["meta"]
        if not src_img.exists():
            raise SystemExit("缺源视图：" + str(src_img))
        if not src_meta.exists():
            raise SystemExit("缺来源 meta：" + str(src_meta))

        src_sha = sha256_file(src_img)
        meta = load_meta(src_meta)
        declared = meta.get("image_sha256")
        if declared and declared != src_sha:
            raise SystemExit("meta 声明的 image_sha256 与源文件实际不符：" + spec["view_id"])

        dst = pack / spec["dest"]
        action = "copied"
        if dst.exists():
            if sha256_file(dst) == src_sha:
                action = "unchanged"
            else:
                raise SystemExit("目标已存在且内容不同，拒绝覆盖：" + str(dst))
        if action == "copied":
            dst.write_bytes(src_img.read_bytes())

        dst_sha = sha256_file(dst)
        if dst_sha != src_sha:
            raise SystemExit("复制后哈希不一致：" + str(dst))

        with Image.open(dst) as im:
            im.verify()
        with Image.open(dst) as im:
            size = list(im.size)
            fmt = im.format
        long_side = max(size)
        if long_side < MIN_LONG_SIDE:
            raise SystemExit(spec["view_id"] + " 长边 " + str(long_side) + " < " + str(MIN_LONG_SIDE))

        out.append({
            "view_id": spec["view_id"],
            "role": spec["role"],
            "file": (PACK_SUBDIR / spec["dest"]).as_posix(),
            "bytes": dst.stat().st_size,
            "sha256": dst_sha,
            "image_format": fmt,
            "image_size": size,
            "long_side": long_side,
            "copy_action": action,
            "crop": spec["crop"],
            "source": {
                "image_path": src_img.relative_to(root).as_posix(),
                "image_sha256_recomputed": src_sha,
                "meta_path": src_meta.relative_to(root).as_posix(),
                "meta_sha256": sha256_file(src_meta),
                "action_id": meta.get("action_id"),
                "task_id": meta.get("task_id"),
                "mode": meta.get("mode"),
                "seed": meta.get("seed"),
                "prompt_sha256": meta.get("prompt_sha256"),
                "reference_sha256": meta.get("reference_sha256"),
                "size_used": meta.get("size_used") or meta.get("size_requested"),
                "watermark_flag": meta.get("watermark"),
                "submitted_at": meta.get("submitted_at"),
                "finished_at": meta.get("finished_at"),
            },
        })
    return out


def build_board(root: Path, pack: Path, views: list[dict]) -> dict:
    font_title = pick_font(30)
    font_label = pick_font(20)
    font_small = pick_font(17)

    width = MARGIN * 2 + CELL * 3 + GAP * 2
    row_h = CELL + LABEL_H
    height = MARGIN + TITLE_H + row_h + GAP + row_h + CAPTION_H + MARGIN
    board = Image.new("RGB", (width, height), (255, 255, 255))
    d = ImageDraw.Draw(board)

    d.text((MARGIN, MARGIN - 8), "Aster 01 参考包 · 人读参考板", font=font_title, fill=(20, 20, 20))
    d.text((MARGIN, MARGIN + 32),
           "虚构演示商品 · 不用于真实上架 · 由 qwen-image-3.0 生成",
           font=font_small, fill=(150, 40, 40))

    y1 = MARGIN + TITLE_H
    y2 = y1 + row_h + GAP
    ratios = []
    for i, v in enumerate(views):
        x = MARGIN + i * (CELL + GAP)
        img = Image.open(root / v["file"]).convert("RGB")
        board.paste(fit(img, CELL), (x, y1))
        d.text((x, y1 + CELL + 6), "上：" + v["view_id"] + "（原图缩放）",
               font=font_label, fill=(20, 20, 20))

        w, h = img.size
        left, top, right, bottom = v["crop"]
        box = (int(left * w), int(top * h), int(right * w), int(bottom * h))
        crop_px = max(1, box[2] - box[0])
        ratio = w / crop_px
        ratios.append(ratio)
        board.paste(fit(img.crop(box), CELL), (x, y2))
        d.text((x, y2 + CELL + 6),
               "下：局部裁剪 · 相对上排 ×" + format(ratio, ".1f") + "（插值）",
               font=font_label, fill=(20, 20, 20))

    cap_y = y2 + row_h + 10
    d.text((MARGIN, cap_y),
           "下排是把上排原图裁剪后重采样放大的局部，只用于人眼读细节；插值不新增任何信息，不得当作新证据。",
           font=font_small, fill=(60, 60, 60))
    d.text((MARGIN, cap_y + 24),
           "三视图的来源、task id、seed 与哈希见同目录 pack-provenance.json；本板不构成对真实商品的任何声明。",
           font=font_small, fill=(60, 60, 60))
    d.text((MARGIN, cap_y + 48),
           "「无文字 / 无水印」属人工视觉判断；状态与确认记录见 pack-provenance.json，"
           "本板不代替该项确认。",
           font=font_small, fill=(150, 40, 40))

    out = pack / "reference-board.png"
    board.save(out, format="PNG", optimize=True)
    return {
        "file": (PACK_SUBDIR / "reference-board.png").as_posix(),
        "sha256": sha256_file(out),
        "bytes": out.stat().st_size,
        "image_size": [width, height],
        "layout": "2x3",
        "relative_magnification": [round(r, 2) for r in ratios],
    }


def check(root: Path) -> int:
    """只读核对：任何漂移都指名道姓，不改文件。供 D0.4 校验器复用。"""
    pack = root / PACK_SUBDIR
    man = pack / "pack-provenance.json"
    if not man.exists():
        print("缺 pack-provenance.json")
        return 2
    data = json.loads(man.read_text(encoding="utf-8"))
    bad = []
    for v in data["views"]:
        p = root / v["file"]
        if not p.exists():
            bad.append(v["file"] + " 缺失")
        elif sha256_file(p) != v["sha256"]:
            bad.append(v["file"] + " 哈希漂移")
    b = root / data["board"]["file"]
    if not b.exists():
        bad.append(data["board"]["file"] + " 缺失")
    elif sha256_file(b) != data["board"]["sha256"]:
        bad.append(data["board"]["file"] + " 哈希漂移")
    for item in bad:
        print("FAIL " + item)
    print("CHECK_OK: pack matches provenance" if not bad
          else "CHECK_FAIL: " + str(len(bad)) + " drift item(s)")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--check", action="store_true", help="只读核对，不写任何文件")
    args = ap.parse_args()
    root = Path(args.project).resolve()

    if args.check:
        return check(root)

    pack = root / PACK_SUBDIR
    views = freeze_views(root, pack)
    board = build_board(root, pack, views)
    provenance = {
        "schema": "demo-reference-pack-provenance/1",
        "pack_version": "2026-09-25.1",
        "frozen_at": stamp(),
        "product_sku": "demo-tumbler-aster-01",
        "media_class": "fictional_demo_fixture",
        "disclaimer": "虚构演示商品 / 不用于真实上架",
        "generator_model": "qwen-image-3.0",
        "billable_calls_in_this_step": 0,
        "views": views,
        "board": board,
        "checks": {
            "byte_identical_copy": True,
            "meta_declared_sha_matches_source": True,
            "long_side_ge_1024": True,
            "no_visible_text_or_watermark": HUMAN_REVIEW["status"],
        },
        "human_review": HUMAN_REVIEW,
        "boundaries": [
            "三张视图均由 image_to_image 从 C/raw.png 派生，不是同一设计的独立拍摄；跨视图一致性仍须人工核对",
            "本包不证明 qwen-image-3.0 能保住这些事实，那是 Phase 1",
            "不证明真实商品、真实运营提效或 Amazon 审核通过",
        ],
    }
    (pack / "pack-provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for v in views:
        print(v["view_id"].ljust(16) + " " + v["copy_action"].ljust(9) + " "
              + str(v["image_size"]) + " " + v["sha256"][:16])
    print("board sha256=" + board["sha256"][:16] + " size=" + str(board["image_size"]))
    print("provenance=" + (PACK_SUBDIR / "pack-provenance.json").as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
