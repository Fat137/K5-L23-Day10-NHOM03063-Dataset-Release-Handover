#!/usr/bin/env python3
"""Công cụ xem ảnh và hỗ trợ review nhãn cho Day 10 lab (Pha 2 & Đề ẩn).

Sử dụng:
  1. Trực quan hóa một ảnh cụ thể (vẽ box detection, nhãn lớp, lưu ảnh hoặc mở xem):
     python scripts/review_tool.py --delivery runs/r3063007/delivery --image 000000000139 --save-rendered preview.jpg

  2. Sinh ứng dụng HTML Review Viewer tương tác (mở trên trình duyệt, không cần cài đặt thêm):
     python scripts/review_tool.py --delivery runs/r3063007/delivery --candidates runs/r3063007/candidates.json --export-html review_viewer.html

  3. Thêm một dòng ghi nhận review từ CLI vào review_log.csv:
     python scripts/review_tool.py --log --image 000000000139 --type class_swap --verdict confirmed --note "Xe tải mui kín nhưng gán nhầm sang car" --out-csv runs/r3063007/review_log.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def load_classes(delivery_dir: Path) -> dict[int, str]:
    """Đọc classes.txt trả về {class_id: tên_lớp}."""
    path = delivery_dir / "classes.txt"
    classes = {}
    if not path.is_file():
        return classes
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) == 2 and parts[0].isdigit():
            classes[int(parts[0])] = parts[1].strip()
    return classes


def load_yolo_boxes(label_path: Path, img_w: int, img_h: int) -> list[dict]:
    """Đọc file nhãn YOLO và quy đổi về tọa độ pixel (x1, y1, x2, y2)."""
    boxes = []
    if not label_path.is_file():
        return boxes
    for line in label_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 5:
            try:
                c = int(float(parts[0]))
                xc, yc, w, h = map(float, parts[1:5])
                x1 = int(round((xc - w / 2) * img_w))
                y1 = int(round((yc - h / 2) * img_h))
                x2 = int(round((xc + w / 2) * img_w))
                y2 = int(round((yc + h / 2) * img_h))
                boxes.append({
                    "class_id": c,
                    "x1": max(0, x1),
                    "y1": max(0, y1),
                    "x2": min(img_w, x2),
                    "y2": min(img_h, y2),
                    "norm": [xc, yc, w, h],
                })
            except ValueError:
                continue
    return boxes


def render_image(delivery_dir: Path, image_name: str, out_path: Path | None = None, show: bool = False):
    """Vẽ bounding box lên ảnh dùng Pillow."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("Lỗi: Pillow chưa được cài đặt. Hãy dùng chế độ --export-html để xem trên trình duyệt.", file=sys.stderr)
        return None

    img_path = delivery_dir / "images" / f"{image_name}.jpg"
    if not img_path.is_file():
        print(f"Lỗi: Không tìm thấy ảnh {img_path}", file=sys.stderr)
        return None

    img = Image.open(img_path).convert("RGB")
    w, h = img.size
    draw = ImageDraw.Draw(img)

    classes = load_classes(delivery_dir)
    label_path = delivery_dir / "labels" / f"{image_name}.txt"
    boxes = load_yolo_boxes(label_path, w, h)

    colors = ["#FF3B30", "#34C759", "#007AFF", "#FF9500", "#AF52DE", "#5856D6", "#FF2D55", "#5AC8FA"]

    for i, b in enumerate(boxes):
        color = colors[b["class_id"] % len(colors)]
        draw.rectangle([b["x1"], b["y1"], b["x2"], b["y2"]], outline=color, width=2)
        cname = classes.get(b["class_id"], str(b["class_id"]))
        text = f"{b['class_id']}: {cname}"
        draw.text((b["x1"] + 2, max(0, b["y1"] - 12)), text, fill=color)

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path)
        print(f"Đã lưu ảnh vẽ box tại: {out_path}")

    if show:
        img.show()

    return img


def append_review_log(out_csv: Path, image: str, err_type: str, verdict: str, note: str):
    """Ghi thêm một dòng vào review_log.csv."""
    verdict = verdict.strip().lower()
    if verdict not in ("confirmed", "rejected"):
        raise ValueError("verdict phải là 'confirmed' hoặc 'rejected'")

    note = note.strip()
    if len(note) < 20:
        print(f"CẢNH BÁO: Ghi chú dài {len(note)} ký tự (< 20 ký tự)! Theo tiêu chí H3 & Rubric, note cần >= 20 ký tự.", file=sys.stderr)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    file_exists = out_csv.is_file()

    with out_csv.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["image", "type", "verdict", "note"])
        writer.writerow([image.strip(), err_type.strip(), verdict, note])

    print(f"Đã ghi vào {out_csv}: image={image}, type={err_type}, verdict={verdict}")


def generate_html_viewer(delivery_dir: Path, candidates_path: Path | None, out_html: Path):
    """Sinh file HTML Review Viewer tương tác, chạy trực tiếp trên mọi trình duyệt."""
    classes = load_classes(delivery_dir)
    labels_dir = delivery_dir / "labels"
    images_dir = delivery_dir / "images"

    candidates = []
    if candidates_path and candidates_path.is_file():
        try:
            data = json.loads(candidates_path.read_text(encoding="utf-8"))
            candidates = data.get("candidates", [])
        except Exception as e:
            print(f"Cảnh báo khi đọc candidates.json: {e}", file=sys.stderr)

    # Nếu không có file candidates, lấy danh sách ảnh từ thư mục images
    if not candidates:
        if images_dir.is_dir():
            for p in sorted(images_dir.glob("*.jpg"))[:50]:
                candidates.append({"image": p.stem, "type": "candidate_inspection", "details": "Xem xét thủ công"})

    # Chuẩn bị dữ liệu JSON nhúng vào HTML
    items_data = []
    for cand in candidates:
        img_name = cand.get("image") or cand.get("target") or ""
        if not img_name:
            continue
        lbl_file = labels_dir / f"{img_name}.txt"
        img_file = images_dir / f"{img_name}.jpg"

        boxes = []
        if lbl_file.is_file():
            for line in lbl_file.read_text(encoding="utf-8").splitlines():
                parts = line.strip().split()
                if len(parts) >= 5:
                    try:
                        c = int(float(parts[0]))
                        boxes.append({
                            "class_id": c,
                            "class_name": classes.get(c, str(c)),
                            "norm": [float(p) for p in parts[1:5]],
                        })
                    except ValueError:
                        continue

        items_data.append({
            "image": img_name,
            "type": cand.get("type", "unknown"),
            "details": cand.get("details", cand.get("reason", "")),
            "boxes": boxes,
            "image_rel": f"images/{img_name}.jpg" if img_file.is_file() else "",
        })

    html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Day 10 Lab - Interactive Image Reviewer</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      margin: 0; padding: 0; display: flex; height: 100vh; background: #1e1e24; color: #f0f0f5;
    }}
    #sidebar {{
      width: 320px; background: #282830; border-right: 1px solid #3c3c46;
      display: flex; flex-direction: column; overflow: hidden;
    }}
    #sidebar-header {{
      padding: 16px; background: #1f1f26; border-bottom: 1px solid #3c3c46;
    }}
    #sidebar-header h2 {{ margin: 0 0 8px 0; font-size: 18px; color: #38bdf8; }}
    #search-box {{
      width: 100%; padding: 8px 12px; background: #141419; border: 1px solid #475569;
      color: #fff; border-radius: 6px; font-size: 14px;
    }}
    #items-list {{
      flex: 1; overflow-y: auto; list-style: none; margin: 0; padding: 0;
    }}
    .item {{
      padding: 12px 16px; border-bottom: 1px solid #343440; cursor: pointer; transition: 0.2s;
    }}
    .item:hover {{ background: #333340; }}
    .item.active {{ background: #0369a1; color: #fff; }}
    .item-title {{ font-weight: bold; font-size: 14px; display: flex; justify-content: space-between; }}
    .item-tag {{
      font-size: 11px; padding: 2px 6px; border-radius: 4px; background: #374151; color: #93c5fd;
    }}
    .item-status {{ font-size: 11px; margin-top: 4px; }}
    .status-confirmed {{ color: #4ade80; font-weight: bold; }}
    .status-rejected {{ color: #f87171; font-weight: bold; }}

    #main {{
      flex: 1; display: flex; flex-direction: column; overflow: hidden;
    }}
    #topbar {{
      padding: 12px 20px; background: #22222a; border-bottom: 1px solid #3c3c46;
      display: flex; justify-content: space-between; align-items: center;
    }}
    #canvas-container {{
      flex: 1; position: relative; overflow: hidden; background: #0f0f12;
      display: flex; align-items: center; justify-content: center;
    }}
    #review-canvas {{
      max-width: 95%; max-height: 95%; object-fit: contain; box-shadow: 0 4px 20px rgba(0,0,0,0.5);
    }}
    #controls-panel {{
      height: 220px; background: #22222a; border-top: 1px solid #3c3c46; padding: 16px 24px;
      display: flex; gap: 24px;
    }}
    .control-col {{ display: flex; flex-direction: column; }}
    .btn-group {{ display: flex; gap: 10px; margin-bottom: 10px; }}
    button {{
      padding: 10px 18px; border-radius: 6px; border: none; font-weight: 600; cursor: pointer;
      font-size: 14px; transition: 0.15s;
    }}
    .btn-confirm {{ background: #16a34a; color: white; }}
    .btn-confirm:hover {{ background: #15803d; }}
    .btn-reject {{ background: #dc2626; color: white; }}
    .btn-reject:hover {{ background: #b91c1c; }}
    .btn-export {{ background: #0284c7; color: white; }}
    .btn-export:hover {{ background: #0369a1; }}
    textarea {{
      width: 100%; height: 75px; background: #141419; border: 1px solid #475569;
      color: #fff; border-radius: 6px; padding: 8px; font-size: 13px; resize: none;
    }}
    .char-count {{ font-size: 12px; margin-top: 4px; }}
    .char-bad {{ color: #f87171; }}
    .char-good {{ color: #4ade80; }}
    .quick-notes {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }}
    .quick-note-btn {{
      padding: 4px 8px; font-size: 11px; background: #374151; color: #cbd5e1;
      border-radius: 4px; cursor: pointer; border: none;
    }}
    .quick-note-btn:hover {{ background: #4b5563; color: #fff; }}
  </style>
</head>
<body>
  <div id="sidebar">
    <div id="sidebar-header">
      <h2>Danh sách ứng viên review</h2>
      <input type="text" id="search-box" placeholder="Tìm ảnh hoặc loại lỗi..." oninput="filterItems()">
    </div>
    <ul id="items-list"></ul>
    <div style="padding: 12px; border-top: 1px solid #3c3c46;">
      <button class="btn-export" style="width: 100%;" onclick="exportCSV()">Tải file review_log.csv</button>
    </div>
  </div>

  <div id="main">
    <div id="topbar">
      <div>
        <span id="current-title" style="font-size: 16px; font-weight: bold;">Chưa chọn ảnh</span>
        <span id="current-type" class="item-tag" style="margin-left: 10px; display: none;"></span>
      </div>
      <div>
        <label><input type="checkbox" id="toggle-boxes" checked onchange="drawCurrent()"> Hiện Bounding Box</label>
        <span style="margin-left: 15px; color: #94a3b8; font-size: 13px;">Phóng to ảnh: lăn chuột hoặc mở ảnh gốc</span>
      </div>
    </div>

    <div id="canvas-container">
      <canvas id="review-canvas"></canvas>
    </div>

    <div id="controls-panel">
      <div class="control-col" style="flex: 1;">
        <label style="font-size: 13px; font-weight: bold; margin-bottom: 6px;">
          Ghi chú review (<span id="char-indicator" class="char-bad">0/20 ký tự</span> - Nói rõ thấy gì trong ảnh):
        </label>
        <textarea id="note-input" placeholder="Ví dụ: Xe tải mui kín chở hàng nhưng detection ghi nhầm thành car..." oninput="onNoteChange()"></textarea>
        <div class="quick-notes">
          <button class="quick-note-btn" onclick="setQuickNote('Xe tải mui kín chở hàng, nhãn detection ghi car')">Xe tải nhầm car</button>
          <button class="quick-note-btn" onclick="setQuickNote('Hai người đứng sát nhau, panoptic gộp chung một segment')">Gộp 2 người</button>
          <button class="quick-note-btn" onclick="setQuickNote('Vật bị che khuất tự nhiên trên 50%, không phải lỗi gán nhãn')">Lệch che khuất tự nhiên</button>
          <button class="quick-note-btn" onclick="setQuickNote('Box detection bị lệch khỏi vật thể trên 30% diện tích')">Box lệch khỏi vật</button>
        </div>
      </div>

      <div class="control-col" style="width: 260px; justify-content: center;">
        <div class="btn-group">
          <button class="btn-confirm" onclick="setVerdict('confirmed')">✓ Xác nhận lỗi (Confirmed)</button>
          <button class="btn-reject" onclick="setVerdict('rejected')">✗ Lệch tự nhiên (Rejected)</button>
        </div>
        <div id="verdict-status" style="font-size: 13px; text-align: center; color: #94a3b8;">Chưa đánh giá</div>
      </div>
    </div>
  </div>

  <script>
    const items = {json.dumps(items_data, ensure_ascii=False)};
    const reviews = {{}}; // image -> {{ verdict, note }}
    let currentIndex = 0;
    const canvas = document.getElementById('review-canvas');
    const ctx = canvas.getContext('2d');
    let loadedImage = null;

    function init() {{
      renderList();
      if (items.length > 0) {{
        selectItem(0);
      }}
    }}

    function renderList() {{
      const listEl = document.getElementById('items-list');
      listEl.innerHTML = '';
      const filter = document.getElementById('search-box').value.toLowerCase();

      items.forEach((it, idx) => {{
        if (filter && !it.image.toLowerCase().includes(filter) && !it.type.toLowerCase().includes(filter)) {{
          return;
        }}
        const li = document.createElement('li');
        li.className = 'item' + (idx === currentIndex ? ' active' : '');
        const rev = reviews[it.image];
        let statusHtml = '<div class="item-status">Chưa xem</div>';
        if (rev) {{
          statusHtml = rev.verdict === 'confirmed' 
            ? '<div class="item-status status-confirmed">✓ Confirmed</div>'
            : '<div class="item-status status-rejected">✗ Rejected</div>';
        }}
        li.innerHTML = `
          <div class="item-title">
            <span>${{it.image}}</span>
            <span class="item-tag">${{it.type}}</span>
          </div>
          ${{statusHtml}}
        `;
        li.onclick = () => selectItem(idx);
        listEl.appendChild(li);
      }});
    }}

    function selectItem(idx) {{
      currentIndex = idx;
      renderList();
      const it = items[idx];
      document.getElementById('current-title').textContent = it.image;
      const typeTag = document.getElementById('current-type');
      typeTag.textContent = it.type;
      typeTag.style.display = 'inline-block';

      const rev = reviews[it.image] || {{ verdict: '', note: '' }};
      document.getElementById('note-input').value = rev.note;
      onNoteChange();
      updateVerdictDisplay(rev.verdict);

      // Tải và vẽ ảnh
      loadedImage = new Image();
      loadedImage.src = it.image_rel;
      loadedImage.onload = () => {{
        canvas.width = loadedImage.naturalWidth;
        canvas.height = loadedImage.naturalHeight;
        drawCurrent();
      }};
      loadedImage.onerror = () => {{
        canvas.width = 600; canvas.height = 400;
        ctx.fillStyle = '#1e1e24'; ctx.fillRect(0, 0, 600, 400);
        ctx.fillStyle = '#94a3b8'; ctx.font = '16px sans-serif';
        ctx.fillText('Không tìm thấy ảnh: ' + it.image_rel, 50, 200);
      }};
    }}

    function drawCurrent() {{
      if (!loadedImage || !loadedImage.naturalWidth) return;
      ctx.drawImage(loadedImage, 0, 0);

      const showBoxes = document.getElementById('toggle-boxes').checked;
      if (!showBoxes) return;

      const it = items[currentIndex];
      const colors = ["#FF3B30", "#34C759", "#007AFF", "#FF9500", "#AF52DE", "#5856D6", "#FF2D55", "#5AC8FA"];

      it.boxes.forEach(b => {{
        const [xc, yc, w, h] = b.norm;
        const imgW = canvas.width;
        const imgH = canvas.height;
        const x1 = (xc - w / 2) * imgW;
        const y1 = (yc - h / 2) * imgH;
        const bw = w * imgW;
        const bh = h * imgH;

        const color = colors[b.class_id % colors.length];
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.strokeRect(x1, y1, bw, bh);

        ctx.fillStyle = color;
        ctx.font = 'bold 12px sans-serif';
        ctx.fillText(`${{b.class_id}}: ${{b.class_name}}`, x1 + 2, Math.max(14, y1 - 4));
      }});
    }}

    function onNoteChange() {{
      const note = document.getElementById('note-input').value;
      const count = note.length;
      const el = document.getElementById('char-indicator');
      el.textContent = `${{count}}/20 ký tự`;
      if (count >= 20) {{
        el.className = 'char-good';
      }} else {{
        el.className = 'char-bad';
      }}
      if (items[currentIndex]) {{
        const img = items[currentIndex].image;
        if (!reviews[img]) reviews[img] = {{ verdict: '', note: '' }};
        reviews[img].note = note;
      }}
    }}

    function setQuickNote(txt) {{
      document.getElementById('note-input').value = txt;
      onNoteChange();
    }}

    function setVerdict(v) {{
      const it = items[currentIndex];
      if (!it) return;
      const note = document.getElementById('note-input').value.trim();
      if (note.length < 20) {{
        alert('Cảnh báo tiêu chuẩn: Ghi chú review phải có ít nhất 20 ký tự (nói rõ thấy gì trong ảnh) theo yêu cầu của H3 & Rubric!');
      }}
      if (!reviews[it.image]) reviews[it.image] = {{ verdict: '', note: '' }};
      reviews[it.image].verdict = v;
      reviews[it.image].note = note;
      updateVerdictDisplay(v);
      renderList();
    }}

    function updateVerdictDisplay(v) {{
      const el = document.getElementById('verdict-status');
      if (v === 'confirmed') {{
        el.innerHTML = '<span class="status-confirmed">Đã xác nhận lỗi (Confirmed)</span>';
      }} else if (v === 'rejected') {{
        el.innerHTML = '<span class="status-rejected">Đã đánh dấu lệch tự nhiên (Rejected)</span>';
      }} else {{
        el.innerHTML = '<span>Chưa đánh giá</span>';
      }}
    }}

    function exportCSV() {{
      let csvContent = "image,type,verdict,note\\n";
      let count = 0;
      items.forEach(it => {{
        const rev = reviews[it.image];
        if (rev && rev.verdict) {{
          const cleanNote = '"' + (rev.note || '').replace(/"/g, '""') + '"';
          csvContent += `${{it.image}},${{it.type}},${{rev.verdict}},${{cleanNote}}\\n`;
          count++;
        }}
      }});
      if (count === 0) {{
        alert('Bạn chưa review ảnh nào!');
        return;
      }}
      const blob = new Blob([csvContent], {{ type: 'text/csv;charset=utf-8;' }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = "review_log.csv";
      a.click();
      URL.revokeObjectURL(url);
    }}

    function filterItems() {{
      renderList();
    }}

    window.onload = init;
  </script>
</body>
</html>
"""
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(html_content, encoding="utf-8")
    print(f"Đã xuất HTML Review Viewer tương tác tại: {out_html}")
    print("Mẹo: Bạn có thể mở trực tiếp file này trên Chrome/Edge để xem ảnh và review rất trực quan!")


def main() -> int:
    parser = argparse.ArgumentParser(description="Công cụ xem ảnh và review nhãn cho Day 10 lab")
    parser.add_argument("--delivery", required=True, help="Đường dẫn tới thư mục delivery")
    parser.add_argument("--image", help="Tên ảnh cần vẽ (không đuôi .jpg)")
    parser.add_argument("--save-rendered", help="Đường dẫn lưu ảnh đã vẽ box")
    parser.add_argument("--show", action="store_true", help="Hiển thị ảnh bằng trình xem ảnh hệ thống")
    parser.add_argument("--candidates", help="Đường dẫn file candidates.json để sinh HTML review")
    parser.add_argument("--export-html", help="Đường dẫn file .html đầu ra cho viewer tương tác")
    parser.add_argument("--log", action="store_true", help="Ghi trực tiếp kết quả review vào csv")
    parser.add_argument("--type", help="Loại lỗi khi ghi log")
    parser.add_argument("--verdict", help="confirmed hoặc rejected")
    parser.add_argument("--note", help="Ghi chú review (>= 20 ký tự)")
    parser.add_argument("--out-csv", help="Đường dẫn review_log.csv")
    args = parser.parse_args()

    delivery_dir = Path(args.delivery).resolve()

    if args.log:
        if not (args.image and args.type and args.verdict and args.out_csv):
            print("Lỗi: Chế độ --log cần --image, --type, --verdict, --out-csv", file=sys.stderr)
            return 1
        append_review_log(Path(args.out_csv), args.image, args.type, args.verdict, args.note or "")
        return 0

    if args.export_html:
        cand_path = Path(args.candidates).resolve() if args.candidates else None
        out_html = Path(args.export_html).resolve()
        generate_html_viewer(delivery_dir, cand_path, out_html)
        return 0

    if args.image:
        out_p = Path(args.save_rendered).resolve() if args.save_rendered else None
        render_image(delivery_dir, args.image, out_p, show=args.show)
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
