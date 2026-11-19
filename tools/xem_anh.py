"""Công cụ xem ảnh ứng viên (dùng Pillow; chỉ là công cụ xem, không phải validator).

    py -X utf8 tools/xem_anh.py <thư_mục_delivery> <candidates.json> --phan 1/4 --out <thư_mục_html>

Với mỗi ứng viên trong phần được chia: ghép [ảnh gốc | box detection | segment panoptic]
cạnh nhau. Box/segment được nêu trong ứng viên (trường "boxes" = chỉ số dòng 0-based,
"segments" = id segment) vẽ đậm màu đỏ/vàng, còn lại vẽ mờ. Ảnh nhỏ được phóng to.
Mở <out>/index.html để xem; ghi kết luận vào work/de_an/review_<mã>.csv.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

THING: set = set()
PALETTE = [(31, 119, 180), (44, 160, 44), (148, 103, 189), (140, 86, 75), (227, 119, 194),
           (127, 127, 127), (188, 189, 34), (23, 190, 207), (255, 127, 14), (174, 199, 232)]
HL_BOX = (255, 0, 0)
HL_SEG = (255, 215, 0)


def font(size: int):
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def load_classes(d: Path) -> dict[int, str]:
    out = {}
    for line in (d / "classes.txt").read_text(encoding="utf-8-sig").splitlines():
        p = line.strip().split(maxsplit=1)
        if len(p) == 2 and p[0].isdigit():
            out[int(p[0])] = p[1]
    return out


def load_panoptic(d: Path):
    pan = json.loads((d / "panoptic.json").read_text(encoding="utf-8-sig"))
    cats = {c["id"]: c["name"] for c in pan.get("categories", [])}
    global THING
    THING = {c["id"] for c in pan.get("categories", []) if c.get("isthing")}
    stems = {}
    for img in pan.get("images", []):
        stems[img["id"]] = Path(img.get("file_name", str(img["id"]))).stem
    segs = {}
    for ann in pan.get("annotations", []):
        stem = Path(ann.get("file_name", "")).stem or stems.get(ann.get("image_id"), "")
        segs[stem] = ann.get("segments_info", [])
    return cats, segs


def read_boxes(path: Path, w: int, h: int):
    boxes = []
    if not path.exists():
        return boxes
    for i, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines()):
        p = line.split()
        if len(p) < 5:
            continue
        try:
            c = int(float(p[0])); x, y, bw, bh = map(float, p[1:5])
        except ValueError:
            continue
        boxes.append((i, c, (x - bw / 2) * w, (y - bh / 2) * h, (x + bw / 2) * w, (y + bh / 2) * h))
    return boxes


def render(d: Path, cand: dict, classes, cats, segs, out_path: Path) -> str:
    stem = cand["target"]
    hl_boxes = set(cand.get("boxes") or [])
    hl_segs = set(cand.get("segments") or [])
    img_path = d / "images" / f"{stem}.jpg"
    mask_path = d / "masks" / f"{stem}.png"
    note = ""
    if img_path.exists():
        try:
            base = Image.open(img_path).convert("RGB")
        except OSError:
            base, note = None, "ẢNH HỎNG / không mở được"
    else:
        base, note = None, "THIẾU FILE ẢNH"
    mask = None
    if mask_path.exists():
        try:
            mask = Image.open(mask_path).convert("RGB")
        except OSError:
            note += " | mask không mở được"
    if base is None:
        if mask is None:
            return note or "không có ảnh"
        base = Image.new("RGB", mask.size, (60, 60, 60))
    w, h = base.size
    scale = 1
    while w * scale < 700:
        scale += 1
    W, H = w * scale, h * scale
    big = base.resize((W, H), Image.LANCZOS)
    f = font(max(12, 14))

    # Panel 2: box detection
    det = big.copy()
    dr = ImageDraw.Draw(det)
    for i, c, x1, y1, x2, y2 in read_boxes(d / "labels" / f"{stem}.txt", w, h):
        hl = i in hl_boxes
        col = HL_BOX if hl else PALETTE[c % len(PALETTE)]
        bx = [x1 * scale, y1 * scale, x2 * scale, y2 * scale]
        dr.rectangle(bx, outline=col, width=4 if hl else 2)
        txt = f"[{i + 1}] {classes.get(c, f'?{c}')}"
        tx, ty = max(0, bx[0]), max(0, bx[1] - 16)
        dr.rectangle([tx, ty, tx + 8 * len(txt), ty + 16], fill=col)
        dr.text((tx + 2, ty), txt, fill=(255, 255, 255), font=f)

    # Panel 3: segment panoptic
    seg_panel = big.copy()
    if mask is not None:
        if mask.size != (w, h):
            mask = mask.resize((w, h), Image.NEAREST)
        mpx = mask.load()
        info = {s["id"]: s for s in segs.get(stem, [])}
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        opx = overlay.load()
        edge = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        epx = edge.load()
        ids = [[0] * w for _ in range(h)]
        for yy in range(h):
            row = ids[yy]
            for xx in range(w):
                r, g, b = mpx[xx, yy]
                row[xx] = r + g * 256 + b * 65536
        for yy in range(h):
            for xx in range(w):
                sid = ids[yy][xx]
                if not sid:
                    continue
                s = info.get(sid)
                if s is None or (s.get("category_id") not in THING and sid not in hl_segs):
                    continue
                hl = sid in hl_segs
                col = HL_SEG if hl else PALETTE[sid % len(PALETTE)]
                opx[xx, yy] = col + ((120 if hl else 70),)
                border = (xx == 0 or yy == 0 or xx == w - 1 or yy == h - 1 or
                          ids[yy][xx - 1] != sid or ids[yy - 1][xx] != sid or
                          ids[yy][xx + 1] != sid or ids[yy + 1][xx] != sid)
                if border:
                    epx[xx, yy] = (255, 0, 0, 255) if hl else col + (255,)
        overlay = Image.alpha_composite(overlay, edge).resize((W, H), Image.NEAREST)
        seg_panel = Image.alpha_composite(seg_panel.convert("RGBA"), overlay).convert("RGB")
        ds = ImageDraw.Draw(seg_panel)
        for s in info.values():
            if not s.get("bbox") or (s.get("category_id") not in THING and s["id"] not in hl_segs):
                continue
            x, y, bw, bh = s["bbox"]
            hl = s["id"] in hl_segs
            name = cats.get(s.get("category_id"), f"?{s.get('category_id')}")
            txt = f"{name} #{s['id']}" + (" crowd" if s.get("iscrowd") else "")
            tx, ty = x * scale, y * scale
            col = HL_SEG if hl else (30, 30, 30)
            ds.rectangle([tx, ty, tx + 8 * len(txt), ty + 16], fill=col)
            ds.text((tx + 2, ty), txt, fill=(0, 0, 0) if hl else (255, 255, 255), font=f)
    else:
        note += " | không có mask"

    # Vùng quan tâm: hợp các box/segment được nêu, nới rộng 30%
    roi = []
    for i, c, x1, y1, x2, y2 in read_boxes(d / "labels" / f"{stem}.txt", w, h):
        if i in hl_boxes:
            roi.append((x1, y1, x2, y2))
    for s in segs.get(stem, []):
        if s["id"] in hl_segs and s.get("bbox"):
            x, y, bw, bh = s["bbox"]; roi.append((x, y, x + bw, y + bh))
    zoom = None
    if roi:
        x1 = min(r[0] for r in roi); y1 = min(r[1] for r in roi)
        x2 = max(r[2] for r in roi); y2 = max(r[3] for r in roi)
        mx, my = max(20, (x2 - x1) * 0.3), max(20, (y2 - y1) * 0.3)
        box = [int(max(0, x1 - mx) * scale), int(max(0, y1 - my) * scale),
               int(min(w, x2 + mx) * scale), int(min(h, y2 + my) * scale)]
        if box[2] - box[0] > 4 and box[3] - box[1] > 4:
            crops = [im.crop(box) for im in (big, det, seg_panel)]
            cw, ch = crops[0].size
            z = min(W / cw, (H * 1.2) / ch)
            crops = [c_.resize((max(1, int(cw * z)), max(1, int(ch * z))), Image.LANCZOS) for c_ in crops]
            zoom = crops
    zh = (zoom[0].size[1] + 24) if zoom else 0
    canvas = Image.new("RGB", (W * 3 + 20, H + 24 + zh), (255, 255, 255))
    if zoom:
        for j, c_ in enumerate(zoom):
            canvas.paste(c_, (j * (W + 10), H + 48))
        ImageDraw.Draw(canvas).text((4, H + 28), "PHÓNG TO vùng được nêu", fill=(200, 0, 0), font=f)
    canvas.paste(big, (0, 24)); canvas.paste(det, (W + 10, 24)); canvas.paste(seg_panel, (2 * W + 20, 24))
    dc = ImageDraw.Draw(canvas)
    dc.text((4, 4), f"{stem} gốc  (x{scale})", fill=(0, 0, 0), font=f)
    dc.text((W + 14, 4), "detection (labels) - đỏ = box được nêu, [n] = dòng", fill=(0, 0, 0), font=f)
    dc.text((2 * W + 24, 4), "panoptic (mask) - vàng = segment được nêu", fill=(0, 0, 0), font=f)
    canvas.save(out_path, quality=88)
    return note.strip(" |")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("delivery")
    ap.add_argument("candidates")
    ap.add_argument("--phan", default="1/1", help="phần k/n của hàng đợi, ví dụ 2/4")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    d = Path(args.delivery)
    data = json.loads(Path(args.candidates).read_text(encoding="utf-8-sig"))
    cands = data["candidates"] if isinstance(data, dict) else data
    k, n = (int(x) for x in args.phan.split("/"))
    per = -(-len(cands) // n) if cands else 0
    mine = cands[(k - 1) * per: k * per]
    out = Path(args.out); (out / "img").mkdir(parents=True, exist_ok=True)

    classes = load_classes(d)
    cats, segs = load_panoptic(d)
    rows = []
    for idx, c in enumerate(mine, (k - 1) * per + 1):
        fn = f"{idx:03d}_{c['target']}_{c['type']}.jpg"
        try:
            note = render(d, c, classes, cats, segs, out / "img" / fn)
        except Exception as exc:  # không để một ảnh lỗi làm hỏng cả hàng đợi
            note = f"lỗi vẽ: {exc}"
        ok = (out / "img" / fn).exists()
        rows.append(f"<section><h2>#{idx} {html.escape(c['target'])} — <code>{html.escape(c['type'])}</code></h2>"
                    f"<p class=d>{html.escape(str(c.get('detail', '')))}</p>"
                    + (f"<p class=w>{html.escape(note)}</p>" if note else "")
                    + (f"<a href='img/{fn}' target=_blank><img src='img/{fn}' loading=lazy></a>" if ok else "")
                    + f"<p class=r>Ghi vào CSV: <code>{html.escape(c['target'])},{html.escape(c['type'])},confirmed|rejected,&lt;thấy gì trong ảnh, ≥20 ký tự&gt;</code></p></section>")
        print(f"[{idx}] {c['target']} {c['type']} {note}")
    page = ("<!doctype html><meta charset=utf-8><title>Xem ảnh " + html.escape(args.phan) + "</title>"
            "<style>body{font-family:sans-serif;margin:16px;background:#f4f4f4}section{background:#fff;margin:0 0 24px;padding:12px;border-radius:6px}"
            "img{max-width:100%;border:1px solid #ccc}.d{color:#333}.w{color:#b00;font-weight:bold}.r{color:#555;font-size:13px}</style>"
            f"<h1>Phần {html.escape(args.phan)}: {len(mine)}/{len(cands)} ứng viên</h1>"
            "<p>Mở ảnh, nhìn vật thật rồi quyết định. Lệch lớp: ảnh cho biết bên nào sai (class_swap = detection sai, category_swap = panoptic sai). "
            "Lệch tự nhiên của COCO (bị che, crowd) thì rejected kèm lý do.</p>" + "".join(rows))
    (out / "index.html").write_text(page, encoding="utf-8")
    print(f"{len(mine)} ứng viên -> {out / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
