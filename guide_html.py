import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STAMP = "#1c1915"


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


def marks_for_year(year: int | None, as_of: int) -> dict:
    blank = {
        "as_is": False,
        "dealer": False,
        "full": False,
        "limited": False,
        "service": False,
    }
    if year is None:
        return blank
    if as_of - year >= 10:
        blank["as_is"] = True
        blank["service"] = True
        return blank
    blank["dealer"] = True
    blank["limited"] = True
    return blank


def _box(on: bool, large: bool) -> str:
    size = "0.28in" if large else "0.16in"
    font = "16pt" if large else "10pt"
    mark = "X" if on else ""
    return (
        f'<span class="mark" style="width:{size};height:{size};font-size:{font}">{mark}</span>'
    )


def _blank(value: str) -> str:
    shown = value.strip() or "&nbsp;&nbsp;&nbsp;"
    return f'<span class="blank">{shown}</span>'


def one_guide(car: dict, marks: dict, shop: dict) -> str:
    show_percents = marks["limited"]
    labor = shop["labor"].strip() if show_percents else ""
    parts = shop["parts"].strip() if show_percents else ""
    systems = shop["systems"].strip() if marks["dealer"] else ""
    duration = shop["duration"].strip() if marks["dealer"] else ""
    model = " ".join(part for part in (car.get("model") or "", car.get("trim") or "") if part)
    year = "" if car.get("year") is None else str(car["year"])
    return f"""
    <article class="guide">
      <h1>BUYERS GUIDE</h1>
      <p class="center"><b>IMPORTANT:</b> Spoken promises are difficult to enforce. Ask the dealer to put all promises in writing. Keep this form.</p>
      <hr>
      <div class="grid">
        <div><span>VEHICLE MAKE</span><strong>{_esc(car.get("make"))}</strong></div>
        <div><span>MODEL</span><strong>{_esc(model)}</strong></div>
        <div><span>YEAR</span><strong>{_esc(year)}</strong></div>
        <div><span>VEHICLE IDENTIFICATION NUMBER (VIN)</span><strong>{_esc(car.get("vin"))}</strong></div>
      </div>
      <hr>
      <h2>WARRANTIES FOR THIS VEHICLE:</h2>
      <div class="option">{_box(marks["as_is"], True)}<div>
        <p class="title">AS IS - NO DEALER WARRANTY</p>
        <p class="note">THE DEALER DOES NOT PROVIDE A WARRANTY FOR ANY REPAIRS AFTER SALE.</p>
      </div></div>
      <div class="option">{_box(marks["dealer"], True)}<p class="title">DEALER WARRANTY</p></div>
      <div class="sub">
        <div class="option">{_box(marks["full"], False)}<p class="fine"><b>FULL WARRANTY.</b></p></div>
        <div class="option">{_box(marks["limited"], False)}<p class="fine"><b>LIMITED WARRANTY.</b> The dealer will pay {_blank(labor)}% of the labor and {_blank(parts)}% of the parts for the covered systems that fail during the warranty period. Ask the dealer for a copy of the warranty, and for any documents that explain warranty coverage, exclusions, and the dealer's repair obligations. <i>Implied warranties</i> under your state's laws may give you additional rights.</p></div>
      </div>
      <div class="systems">
        <div>SYSTEMS COVERED:{f"<p>{_esc(systems)}</p>" if systems else ""}</div>
        <div>DURATION:{f"<p>{_esc(duration)}</p>" if duration else ""}</div>
      </div>
      <hr>
      <h2>NON-DEALER WARRANTIES FOR THIS VEHICLE:</h2>
      <div class="option">{_box(False, False)}<p class="fine"><b>MANUFACTURER'S WARRANTY STILL APPLIES.</b> The manufacturer's original warranty has not expired on some components of the vehicle.</p></div>
      <div class="option">{_box(False, False)}<p class="fine"><b>MANUFACTURER'S USED VEHICLE WARRANTY APPLIES.</b></p></div>
      <div class="option">{_box(False, False)}<p class="fine"><b>OTHER USED VEHICLE WARRANTY APPLIES.</b></p></div>
      <p class="fine">Ask the dealer for a copy of the warranty document and an explanation of warranty coverage, exclusions, and repair obligations.</p>
      <div class="option">{_box(marks["service"], False)}<p class="fine"><b>SERVICE CONTRACT.</b> A service contract on this vehicle is available for an extra charge. Ask for details about coverage, deductible, price, and exclusions. If you buy a service contract within 90 days of your purchase of this vehicle, <i>implied warranties</i> under your state's laws may give you additional rights.</p></div>
      <hr>
      <p class="lead">ASK THE DEALER IF YOUR MECHANIC CAN INSPECT THE VEHICLE ON OR OFF THE LOT.</p>
      <p class="fine"><b>OBTAIN A VEHICLE HISTORY REPORT AND CHECK FOR OPEN SAFETY RECALLS.</b> For information on how to obtain a vehicle history report, visit ftc.gov/usedcars. To check for open safety recalls, visit safercar.gov. You will need the vehicle identification number (VIN) shown above to make the best use of the resources on these sites.</p>
      <p class="lead">SEE OTHER SIDE for important additional information, including a list of major defects that may occur in used motor vehicles.</p>
      <p class="spanish">Si el concesionario gestiona la venta en español, pídale una copia de la Guía del Comprador en español.</p>
    </article>
    """


def _esc(value) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&")
        .replace("<", "<")
        .replace(">", ">")
    )


def guides_document(cars: list[dict], shop: dict, as_of: int) -> str:
    pages = []
    for car in cars:
        pages.append(one_guide(car, marks_for_year(car.get("year"), as_of), shop))
    body = "\n".join(pages)
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Buyers Guides</title>
<style>
{_font_face()}
@page {{ size: letter; margin: 0.3in; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: #fff; color: {STAMP}; font-family: "Century Gothic Pro", "Century Gothic", sans-serif; }}
.guide {{
  width: 7.9in; min-height: 10.2in; padding: 0.16in;
  border: 3px solid {STAMP}; outline: 1px solid {STAMP}; outline-offset: -7px;
  page-break-after: always; display: flex; flex-direction: column; gap: 0.06in;
}}
.guide:last-child {{ page-break-after: auto; }}
h1 {{ margin: 0; text-align: center; font-size: 22pt; letter-spacing: 0.04em; line-height: 1; }}
h2 {{ margin: 0; font-size: 8.5pt; letter-spacing: 0.04em; }}
hr {{ border: 0; border-top: 1.5px solid {STAMP}; margin: 0; width: 100%; }}
.center {{ margin: 0; text-align: center; font-size: 8pt; line-height: 1.25; }}
.grid {{ display: grid; grid-template-columns: 1.25fr 1.35fr 0.48fr 1.85fr; gap: 0.1in; }}
.grid span {{ display: block; font-size: 6.5pt; font-weight: 700; letter-spacing: 0.03em; }}
.grid strong {{ display: block; min-height: 0.32in; border-bottom: 1.25px solid {STAMP}; font-size: 11pt; }}
.option {{ display: grid; grid-template-columns: auto 1fr; gap: 0.08in; align-items: start; }}
.sub {{ margin-left: 0.36in; display: flex; flex-direction: column; gap: 0.04in; }}
.mark {{ display: inline-flex; align-items: center; justify-content: center; border: 1.75px solid {STAMP}; font-weight: 700; line-height: 1; }}
.title {{ margin: 0; font-size: 13pt; font-weight: 700; line-height: 1.05; }}
.note {{ margin: 0; font-size: 7.5pt; font-weight: 700; line-height: 1.2; }}
.fine {{ margin: 0; font-size: 7.4pt; line-height: 1.22; }}
.blank {{ display: inline-block; min-width: 0.38in; border-bottom: 1px solid {STAMP}; text-align: center; font-weight: 700; }}
.systems {{ display: grid; grid-template-columns: 1.7fr 0.9fr; min-height: 1.15in; border: 1.5px solid {STAMP}; flex: 1; }}
.systems div {{ padding: 0.04in 0.08in; font-size: 8pt; font-weight: 700; }}
.systems div + div {{ border-left: 1.5px solid {STAMP}; }}
.systems p {{ margin: 0.04in 0 0; font-size: 9pt; white-space: pre-wrap; }}
.lead {{ margin: 0; font-size: 7.6pt; font-weight: 700; line-height: 1.25; }}
.spanish {{ margin: 0; font-size: 8pt; font-style: italic; }}
@media screen {{ body {{ background: #e7e2d8; }} .guide {{ margin: 0.3in auto; background: white; }} }}
</style>
</head>
<body>
{body}
<script>window.addEventListener("load", () => setTimeout(() => window.print(), 300));</script>
</body>
</html>
"""
