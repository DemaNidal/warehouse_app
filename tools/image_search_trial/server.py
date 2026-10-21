# -*- coding: utf-8 -*-
"""A page to try the photo search on, and nothing more.

Runs on its own port, in its own process, bound to this machine only. It
reads the product table to name what it finds and never writes to it, so
the warehouse system on port 5000 is untouched and unaware. Stop it with
Ctrl+C; delete the folder to undo the experiment entirely.

    tools\\image_search_trial\\try.bat
"""

import base64
import io
import os
import sys
import time

# The Windows console here is cp1255, so an Arabic print is a crash before
# the server ever starts. Reconfigure both streams first, ahead of anything
# that might speak.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from flask import Flask, render_template_string, request
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PROJECT)
os.chdir(PROJECT)

from search import Finder                          # noqa: E402
from app import app as warehouse                   # noqa: E402
from models import Product                         # noqa: E402
from utils.storage import image_url                # noqa: E402

PORT = 5001
MAX_BYTES = 12 * 1024 * 1024

trial = Flask(__name__)
trial.config["MAX_CONTENT_LENGTH"] = MAX_BYTES

print("بحمّل الموديل… (ثانيتين، مرة وحدة)")
started = time.time()
FINDER = Finder()
print(f"جاهز — {len(FINDER.ids)} منتج بالفهرس، {time.time() - started:.1f}s")


def describe(product_ids):
    """Names and photos for what came back, read fresh from the catalogue."""
    with warehouse.app_context():
        found = {p.id: p for p in Product.query.filter(
            Product.id.in_(product_ids)
        ).all()}
        return {
            product_id: {
                "name": product.name,
                "size": product.size_data.name if product.size_data else None,
                "neck": product.neck_size.name if product.neck_size else None,
                "colour": product.color.name if product.color else None,
                "category": (product.category.name
                             if product.category else None),
                "quantity": product.total_quantity,
                "url": image_url(product.image) if product.image else None,
            }
            for product_id, product in found.items()
        }


PAGE = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>تجربة البحث بالصورة</title>
<style>
 :root{--line:#e6e9ef;--dim:#8b94a3}
 *{box-sizing:border-box}
 body{font-family:system-ui,"Segoe UI",sans-serif;margin:0;background:#f7f9fc;
      color:#1f2937}
 .wrap{max-width:1100px;margin:0 auto;padding:22px 18px 60px}
 h1{font-size:1.25rem;margin:0 0 4px}
 .sub{color:#5a6472;font-size:.88rem;margin:0 0 20px;line-height:1.8}
 .panel{background:#fff;border:1px solid var(--line);border-radius:16px;
        padding:18px;margin-bottom:20px}
 .drop{display:block;width:100%;border:2px dashed #c6cedb;border-radius:14px;padding:30px 18px;
       text-align:center;background:#fbfcfe;cursor:pointer;transition:.15s}
 .drop:hover,.drop.over{border-color:#0d6efd;background:#f2f7ff}
 .drop p{margin:6px 0;color:#5a6472;font-size:.92rem}
 .drop b{font-size:1rem;color:#1f2937}
 input[type=file]{display:none}
 .opts{display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin-top:14px;
       font-size:.88rem;color:#5a6472}
 button{background:#0d6efd;color:#fff;border:0;border-radius:10px;
        padding:10px 22px;font-size:.95rem;cursor:pointer}
 button:disabled{background:#9db8e8;cursor:default}
 .result{display:flex;gap:20px;align-items:flex-start;flex-wrap:wrap}
 .shot{flex:0 0 210px}
 .shot img{width:100%;border-radius:12px;background:#f1f4f9;
           aspect-ratio:3/4;object-fit:contain}
 .shot .note{font-size:.76rem;color:var(--dim);margin-top:8px;line-height:1.7}
 .grid{flex:1;min-width:300px;display:grid;gap:12px;
       grid-template-columns:repeat(auto-fill,minmax(145px,1fr))}
 .card{border:1px solid var(--line);border-radius:12px;overflow:hidden;
       background:#fff;text-decoration:none;color:inherit;display:block}
 .card:hover{border-color:#b9c3d4;box-shadow:0 6px 16px rgba(18,38,63,.08)}
 .card img{width:100%;aspect-ratio:1;object-fit:contain;background:#f6f8fb}
 .meta{padding:8px 9px;font-size:.76rem;line-height:1.55}
 .meta .score{color:#0d6efd;font-weight:700;font-size:.82rem}
 .meta .name{font-weight:700;display:block}
 .meta small{color:var(--dim);display:block}
 .rank{float:left;background:#eef1f6;border-radius:6px;padding:0 6px;
       font-size:.7rem;color:#5a6472}
 .warn{background:#fff8e1;border:1px solid #ffe08a;border-radius:10px;
       padding:12px 14px;font-size:.84rem;line-height:1.9;margin-top:16px}
 .warn b{color:#8a5a00}
 .err{background:#fde8e8;border:1px solid #f5b5b5;color:#9b1c1c;
      border-radius:10px;padding:12px 14px;font-size:.88rem}
</style>
</head>
<body>
<div class="wrap">

  <h1>تجربة البحث بالصورة</h1>
  <p class="sub">
    أداة منفصلة على المنفذ {{ port }} — ما بتمسّ نظام المخازن ولا بتكتب عليه.
    بتقرأ أسماء المنتجات بس.
  </p>

  <form class="panel" method="POST" enctype="multipart/form-data"
        id="form">
    <label class="drop" id="drop">
      <input type="file" name="photo" accept="image/*" id="file" required>
      <b>اسحبي صورة لهون، أو اضغطي للاختيار</b>
      <p id="chosen">JPG أو PNG أو WEBP · حتى 12 ميغا</p>
    </label>

    <div class="opts">
      <label>
        <input type="checkbox" name="crop" value="1"
               {% if crop %}checked{% endif %}>
        جرّبي القصّ على الجسم
        <small style="color:#8b94a3">(تأثيرها ضعيف — شوفي الملاحظة تحت)</small>
      </label>
      <button type="submit" id="go">ابحثي</button>
    </div>
  </form>

  {% if error %}<div class="panel err">{{ error }}</div>{% endif %}

  {% if results %}
  <div class="panel">
    <div class="result">

      <div class="shot">
        <img src="{{ shot }}" alt="">
        <div class="note">
          {{ "لقيت الجسم وقصّيت عليه" if found else
             ("ما قدرت أميّز الجسم عن الخلفية — استعملت وسط الصورة"
              if crop else "بلا قصّ") }}<br>
          {{ "%.0f"|format(elapsed * 1000) }} مللي ثانية
        </div>
      </div>

      <div class="grid">
        {% for item in results %}
        <a class="card" href="http://localhost:5000/product/{{ item.id }}"
           target="_blank">
          {% if item.url %}<img src="{{ item.url }}" loading="lazy" alt="">{% endif %}
          <div class="meta">
            <span class="rank">{{ loop.index }}</span>
            <span class="score">{{ "%.3f"|format(item.score) }}</span>
            <span class="name">{{ item.name }}</span>
            <small>{{ item.size or '—' }} · {{ item.colour or '—' }}</small>
            <small>{{ item.category or '—' }} · {{ item.quantity }} حبة</small>
          </div>
        </a>
        {% endfor %}
      </div>

    </div>

    <div class="warn">
      <b>اقري النتيجة كقائمة قصيرة، مش كجواب.</b>
      الصورة ما بتحمل الحجم: نفس العبوة بـ250 مل و1 لتر تشابههم 0.943، فبيرجعوا
      ورا بعض وما في طريقة تفرّق بينهم من الصورة. اللي بيحسم كلمة وحدة منك.<br>
      وخيار «القصّ على الجسم» فوق: قِسته وطلع ضعيف — بصورك الخلفية كرتون بتدرّجات
      وشريط لاصق وظلال، فالقصّ بيشيل شريط من فوق وتحت بس وما بيعزل القطعة. خلّيه
      مفتوح أو مسكّر، الفرق بالمراتب ضجيج مش تحسين.
    </div>
  </div>
  {% endif %}

</div>

<script>
 const file = document.getElementById('file');
 const drop = document.getElementById('drop');
 const chosen = document.getElementById('chosen');

 file.addEventListener('change', function () {
   if (file.files.length) { chosen.textContent = file.files[0].name; }
 });

 ['dragenter', 'dragover'].forEach(function (name) {
   drop.addEventListener(name, function (event) {
     event.preventDefault();
     drop.classList.add('over');
   });
 });
 ['dragleave', 'drop'].forEach(function (name) {
   drop.addEventListener(name, function (event) {
     event.preventDefault();
     drop.classList.remove('over');
   });
 });
 drop.addEventListener('drop', function (event) {
   if (event.dataTransfer.files.length) {
     file.files = event.dataTransfer.files;
     chosen.textContent = file.files[0].name;
   }
 });

 document.getElementById('form').addEventListener('submit', function () {
   const go = document.getElementById('go');
   go.disabled = true;
   go.textContent = 'بفتّش…';
 });
</script>
</body>
</html>"""


@trial.route("/", methods=["GET", "POST"])
def home():
    crop = True
    if request.method == "GET":
        return render_template_string(PAGE, results=None, error=None,
                                      crop=crop, port=PORT)

    crop = request.form.get("crop") == "1"
    upload = request.files.get("photo")
    if upload is None or not upload.filename:
        return render_template_string(PAGE, results=None, crop=crop,
                                      port=PORT, error="ما اخترتِ صورة.")

    raw = upload.read()
    try:
        photo = Image.open(io.BytesIO(raw))
        photo.load()
    except Exception:                                      # noqa: BLE001
        return render_template_string(
            PAGE, results=None, crop=crop, port=PORT,
            error="ما قدرت أقرأ الملف كصورة.",
        )

    started = time.time()
    hits, found = FINDER.search(photo, limit=12, crop_to_object=crop)
    elapsed = time.time() - started

    details = describe([product_id for product_id, _ in hits])
    results = [
        {"id": product_id, "score": score, **details[product_id]}
        for product_id, score in hits if product_id in details
    ]

    # shown back as a data URI: the upload is never written to disk
    preview = io.BytesIO()
    photo.convert("RGB").save(preview, "JPEG", quality=70)
    shot = ("data:image/jpeg;base64,"
            + base64.b64encode(preview.getvalue()).decode())

    return render_template_string(
        PAGE, results=results, shot=shot, found=found, crop=crop,
        elapsed=elapsed, error=None, port=PORT,
    )


if __name__ == "__main__":
    print(f"\n  افتحي: http://localhost:{PORT}")
    print("  للإيقاف: Ctrl+C\n")
    # 127.0.0.1 on purpose: there is no login on this page, so it must not
    # be reachable from the network the way the warehouse system is
    trial.run(host="127.0.0.1", port=PORT, debug=False)
