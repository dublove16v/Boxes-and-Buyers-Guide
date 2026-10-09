import base64
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Checkbox boxes measured on the 8.5x11 scan of the shop form, as % of the page.
SPOTS = [
    {"key": "asIs", "left": 10.385, "top": 20.490, "width": 4.078, "height": 3.091, "large": True},
    {"key": "dealerWarranty", "left": 10.463, "top": 26.762, "width": 4.000, "height": 3.091, "large": True},
    {"key": "fullWarranty", "left": 13.272, "top": 30.964, "width": 1.529, "height": 1.182, "large": False},
    {"key": "limitedWarranty", "left": 12.353, "top": 33.447, "width": 1.529, "height": 1.182, "large": False},
    {"key": "duration30", "left": 50.512, "top": 41.944, "width": 1.451, "height": 0.939, "large": False},
    {"key": "duration60", "left": 50.790, "top": 44.278, "width": 1.451, "height": 0.939, "large": False},
    {"key": "durationAsIs", "left": 50.767, "top": 46.426, "width": 1.412, "height": 0.970, "large": False},
    {"key": "mfrStill", "left": 8.980, "top": 64.242, "width": 1.569, "height": 1.212, "large": False},
    {"key": "mfrUsed", "left": 8.980, "top": 67.364, "width": 1.569, "height": 1.212, "large": False},
    {"key": "otherUsed", "left": 8.941, "top": 69.576, "width": 1.569, "height": 1.212, "large": False},
    {"key": "serviceContract", "left": 10.403, "top": 75.689, "width": 1.569, "height": 1.182, "large": False},
]


def _font_face() -> str:
    regular = base64.b64encode((ROOT / "fonts" / "CenturyGothicPro.otf").read_bytes()).decode()
    bold = base64.b64encode((ROOT / "fonts" / "CenturyGothicPro-Bold.otf").read_bytes()).decode()
    return f"""
    @font-face {{
      font-family: "Century Gothic Pro";
      src: url(data:font/otf;base64,{regular}) format("opentype");
      font-weight: 400;
    }}
    @font-face {{
      font-family: "Century Gothic Pro";
      src: url(data:font/otf;base64,{bold}) format("opentype");
      font-weight: 700;
    }}
    """


def _template_src() -> str:
    path = ROOT / "forms" / "buyers-guide.jpg"
    if not path.exists():
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode()
    return f"data:image/jpeg;base64,{encoded}"


def marks_for_year(year: int | None, as_of: int) -> dict:
    blank = {
        "asIs": False,
        "dealerWarranty": False,
        "fullWarranty": False,
        "limitedWarranty": False,
        "duration30": False,
        "duration60": False,
        "durationAsIs": False,
        "serviceContract": False,
        "mfrStill": False,
        "mfrUsed": False,
        "otherUsed": False,
    }
    if year is None:
        return blank
    if as_of - year >= 10:
        blank["asIs"] = True
        blank["durationAsIs"] = True
        blank["serviceContract"] = True
        return blank
    blank["dealerWarranty"] = True
    blank["limitedWarranty"] = True
    blank["duration60"] = True
    blank["serviceContract"] = True
    return blank


def _esc(value) -> str:
    return html.escape("" if value is None else str(value))


def _page(car: dict, marks: dict, nudge_x: float, nudge_y: float, template: str) -> str:
    model = (car.get("model") or "").strip()
    year = "" if car.get("year") is None else str(car["year"])
    location = (car.get("auction") or "").strip()
    ink = []
    if location:
        ink.append(f'<p class="guide-location">{_esc(location)}</p>')
    ink.append(
        f'<p class="guide-value" style="left:9.8%;top:13.99%;width:20%">{_esc(car.get("make"))}</p>'
    )
    ink.append(
        f'<p class="guide-value" style="left:31.5%;top:13.99%;width:16%">{_esc(model)}</p>'
    )
    ink.append(
        f'<p class="guide-value" style="left:47.3%;top:13.99%;width:10%">{_esc(year)}</p>'
    )
    ink.append(
        f'<p class="guide-value guide-vin" style="left:68%;top:13.99%;width:28%">{_esc((car.get("vin") or "").upper())}</p>'
    )
    for spot in SPOTS:
        if not marks.get(spot["key"]):
            continue
        klass = "guide-x guide-x-lg" if spot["large"] else "guide-x"
        ink.append(
            f'<span class="{klass}" style="left:{spot["left"]}%;top:{spot["top"]}%;width:{spot["width"]}%;height:{spot["height"]}%">X</span>'
        )
    image = f'<img class="guide-template" src="{template}" alt="">' if template else ""
    return f"""
    <article class="guide" style="--nudge-x:{nudge_x:.2f}in;--nudge-y:{nudge_y:.2f}in">
      {image}
      <div class="guide-ink">
        {''.join(ink)}
      </div>
    </article>
    """


def guides_document(cars: list[dict], as_of: int, nudge_x: float = 0, nudge_y: float = 0) -> str:
    template = _template_src()
    pages = [
        _page(car, marks_for_year(car.get("year"), as_of), nudge_x, nudge_y, template)
        for car in cars
    ]
    body = "\n".join(pages)
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Buyers Guides</title>
<style>
{_font_face()}
@page {{ size: letter; margin: 0; }}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; background: #fff; }}
.guide {{
  position: relative;
  width: 8.5in;
  height: 11in;
  overflow: hidden;
  background: white;
  color: #111;
  font-family: "Century Gothic Pro", "Century Gothic", sans-serif;
  break-after: page;
  page-break-after: always;
}}
.guide:last-child {{ break-after: auto; page-break-after: auto; }}
.guide-template {{
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: fill;
}}
.guide-ink {{
  position: absolute;
  inset: 0;
  transform: translate(var(--nudge-x, 0in), var(--nudge-y, 0in));
}}
.guide-value {{
  position: absolute;
  margin: 0;
  font-size: 10pt;
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
  overflow: hidden;
}}
.guide-vin {{ font-size: 9pt; letter-spacing: 0.02em; }}
.guide-location {{
  position: absolute;
  top: 0.18in;
  right: 0.22in;
  max-width: 3.6in;
  margin: 0;
  text-align: right;
  font-size: 11pt;
  font-weight: 700;
  line-height: 1.1;
}}
.guide-x {{
  position: absolute;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  line-height: 1;
  font-size: 9pt;
}}
.guide-x-lg {{ font-size: 20pt; }}
@media print {{
  .guide-template {{ display: none !important; }}
}}
@media screen {{
  body {{ background: #e7e2d8; }}
  .guide {{ margin: 0.2in auto; box-shadow: 0 8px 24px rgba(0,0,0,0.12); }}
}}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def print_launcher(document: str, vins: str, week_id: str, label: str) -> str:
    payload = json.dumps(document).replace("</", "<\\/")
    return f"""
    <button id="print-guides" type="button" style="height:2.4rem;padding:0 1rem;border:0;border-radius:0.5rem;background:#1f4d3a;color:#f4f1ea;font-weight:700;cursor:pointer;">
      {html.escape(label)}
    </button>
    <script>
    const doc = {payload};
    document.getElementById("print-guides").addEventListener("click", () => {{
      const w = window.open("", "_blank");
      if (!w) {{
        alert("Allow pop-ups for this site, then click Print again.");
        return;
      }}
      w.document.open();
      w.document.write(doc);
      w.document.close();
      const url = new URL(window.location.href);
      url.searchParams.set("printed", {json.dumps(vins)});
      url.searchParams.set("week", {json.dumps(week_id)});
      setTimeout(() => w.print(), 400);
      setTimeout(() => {{
        window.location.href = url.toString();
      }}, 900);
    }});
    </script>
    """
