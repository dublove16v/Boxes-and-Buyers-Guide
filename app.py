import base64
import json
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Boxes and Buyer's Guide Tool", layout="wide")

try:
    import db
    from guide_html import guides_document, marks_for_year
    from parse_boxes import parse_boxes_file, week_date_from_name
    from parse_dms import parse_dms_file
except Exception as boot_error:
    import traceback

    detail = traceback.format_exc()
    for chunk in ("/mount/src/boxes-and-buyers-guide/", "/workspace/streamlit-app/", "/workspace/"):
        detail = detail.replace(chunk, "")
    st.error("The desk could not start.")
    st.code(detail[-4000:])
    st.caption(type(boot_error).__name__)
    st.stop()

ROOT = Path(__file__).resolve().parent
AS_OF = date.today().year


def print_launcher(document: str, vins: str, week_id: str, label: str) -> str:
    payload = json.dumps(document).replace("</", "<\\/")
    safe_label = (
        label.replace("&", "\u0026amp;")
        .replace("<", "\u0026lt;")
        .replace(">", "\u0026gt;")
    )
    return f"""<!doctype html>
<html>
<body style="margin:0;background:transparent;font-family:sans-serif;">
<button id="print-guides" type="button" style="height:2.4rem;padding:0 1rem;border:0;border-radius:0.5rem;background:#1f4d3a;color:#f4f1ea;font-weight:700;cursor:pointer;">{safe_label}</button>
<script>
const doc = {payload};
document.getElementById("print-guides").onclick = function () {{
  const w = window.open("", "_blank");
  if (!w) {{
    alert("Allow pop-ups for this site, then click Print again.");
    return;
  }}
  w.document.open();
  w.document.write(doc);
  w.document.close();
  setTimeout(function () {{ w.focus(); w.print(); }}, 400);
  try {{
    const url = new URL(window.parent.location.href);
    url.searchParams.set("printed", {json.dumps(vins)});
    url.searchParams.set("week", {json.dumps(week_id)});
    setTimeout(function () {{ window.parent.location.href = url.toString(); }}, 900);
  }} catch (err) {{}}
}};
</script>
</body>
</html>"""


def _font_css() -> str:
    regular = base64.b64encode((ROOT / "fonts" / "CenturyGothicPro.otf").read_bytes()).decode()
    bold = base64.b64encode((ROOT / "fonts" / "CenturyGothicPro-Bold.otf").read_bytes()).decode()
    return f"""
    <style>
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
    html, body, [class*="css"], .stApp, .stMarkdown, button, input, textarea, select {{
      font-family: "Century Gothic Pro", "Century Gothic", sans-serif;
    }}
    .app-title {{
      text-align: center;
      font-weight: 700;
      font-size: 2.4rem;
      letter-spacing: 0.03em;
      margin: 0;
    }}
    .app-sub {{ text-align: center; color: #5c564c; margin: 0.2rem 0 0.8rem; }}
    </style>
    """


def warranty_label(year: int | None) -> str:
    marks = marks_for_year(year, AS_OF)
    if marks["asIs"]:
        return "As-Is"
    if marks["limitedWarranty"]:
        return "Limited"
    return ""


def struck(text: str, dead: bool) -> str:
    if not dead or not text:
        return text
    return "".join(ch + "\u0336" for ch in text)


def sheet_frame(cars: list[dict], flags: dict[str, dict]) -> pd.DataFrame:
    rows = []
    for car in cars:
        flag = flags.get(car["vin"], {})
        rows.append(
            {
                "HERE": bool(flag.get("here")),
                "CHIP": bool(flag.get("chip")),
                "BG": bool(flag.get("bg")),
                "Print": False,
                "Day": car["day_label"],
                "Year": car["year"] or "",
                "Vehicle": struck(f"{car['year'] or ''} {car['make']} {car['model']}".strip(), car["dead"]),
                "VIN": car["vin"],
                "Color": car["color"],
                "Miles": car["odometer"],
                "Lane": car["lane"],
                "Lot": car["lot"],
                "Auction": car["auction"],
                "Guide": warranty_label(car["year"]),
                "Status": "Dead" if car["dead"] else "",
            }
        )
    return pd.DataFrame(rows)


def merge_stock(week_cars: list[dict], stock: list[dict]) -> list[dict]:
    vins = {car["vin"] for car in week_cars}
    extra = [car for car in stock if car["vin"] not in vins]
    return week_cars + extra


st.markdown(_font_css(), unsafe_allow_html=True)
st.markdown('<h1 class="app-title">Boxes and Buyer\'s Guide Tool</h1>', unsafe_allow_html=True)
st.markdown(
    f'<p class="app-sub">{AS_OF - 9} and newer prints a limited dealer warranty. {AS_OF - 10} and older prints As-Is and a service contract.</p>',
    unsafe_allow_html=True,
)

imported = db.import_seed_csvs()
if imported:
    st.toast(f"Loaded {imported} weeks from the boxes folder.")

weeks = db.list_weeks()
dms_name, dms_cars = db.load_dms()

with st.sidebar:
    st.header("This week")
    boxes_file = st.file_uploader("Boxes sheet", type=["xlsx", "xls", "csv"])
    if boxes_file is not None and st.session_state.get("boxes_token") != (getattr(boxes_file, "file_id", None) or boxes_file.name):
        cars = parse_boxes_file(boxes_file.getvalue(), boxes_file.name)
        if not cars:
            st.error("That file did not have any cars. Upload the weekly boxes sheet.")
        else:
            name = Path(boxes_file.name).stem
            week_id = db.save_week(name, week_date_from_name(name), cars)
            st.session_state["boxes_token"] = getattr(boxes_file, "file_id", None) or boxes_file.name
            st.session_state["week_id"] = week_id
            st.rerun()
    dms_file = st.file_uploader("DealerTrack report", type=["xlsx", "xls", "csv"])
    if dms_file is not None and st.session_state.get("dms_token") != (getattr(dms_file, "file_id", None) or dms_file.name):
        stock = parse_dms_file(dms_file.getvalue(), dms_file.name, AS_OF)
        if not stock:
            st.error("No vehicles found in that DealerTrack report.")
        else:
            db.save_dms(dms_file.name, stock)
            st.session_state["dms_token"] = getattr(dms_file, "file_id", None) or dms_file.name
            st.rerun()
    if dms_name:
        st.caption(f"{dms_name} · {len(dms_cars)} in stock")

if not weeks:
    st.info("Upload this week's boxes sheet to start the list. Cars crossed off on the sheet stay on the list as dead deals.")
    st.stop()

labels = {week["id"]: week["name"] for week in weeks}
default_id = st.session_state.get("week_id") or weeks[0]["id"]
if default_id not in labels:
    default_id = weeks[0]["id"]
picked = st.selectbox(
    "Buying week",
    options=list(labels),
    index=list(labels).index(default_id),
    format_func=lambda week_id: labels[week_id],
)
st.session_state["week_id"] = picked

printed = st.query_params.get("printed", "")
printed_week = st.query_params.get("week", "")
if printed and printed_week == picked:
    already = db.flags_for(picked)
    rows = []
    for vin in [part for part in printed.split(",") if part]:
        flag = already.get(vin, {})
        rows.append(
            {
                "vin": vin,
                "here": bool(flag.get("here")),
                "chip": bool(flag.get("chip")),
                "bg": True,
            }
        )
    if rows:
        db.save_flags(picked, rows)
    st.query_params.clear()
    st.rerun()

week_cars = db.week_vehicles(picked)
cars = merge_stock(week_cars, dms_cars)
flags = db.flags_for(picked)
show = st.radio(
    "Show",
    ["All", "Here, no chip", "Here, no BG"],
    horizontal=True,
)
shown = []
dead = [car for car in cars if car["dead"]]
for car in cars:
    if car["dead"]:
        continue
    flag = flags.get(car["vin"], {})
    if show == "Here, no chip" and not (flag.get("here") and not flag.get("chip")):
        continue
    if show == "Here, no BG" and not (flag.get("here") and not flag.get("bg")):
        continue
    shown.append(car)
frame = sheet_frame(shown, flags)
live = [car for car in cars if not car["dead"]]
st.caption(
    f"{len(live)} coming in · {sum(1 for car in cars if car['dead'])} dead · "
    f"{sum(1 for car in live if flags.get(car['vin'], {}).get('here'))} here · "
    f"{sum(1 for car in live if flags.get(car['vin'], {}).get('chip'))} chip · "
    f"{sum(1 for car in live if flags.get(car['vin'], {}).get('bg'))} bg"
)

edited = st.data_editor(
    frame,
    hide_index=True,
    width="stretch",
    column_config={
        "HERE": st.column_config.CheckboxColumn(required=True),
        "CHIP": st.column_config.CheckboxColumn(required=True),
        "BG": st.column_config.CheckboxColumn(required=True),
        "Print": st.column_config.CheckboxColumn(required=True),
        "Day": st.column_config.TextColumn(disabled=True),
        "Year": st.column_config.TextColumn(disabled=True),
        "Vehicle": st.column_config.TextColumn(disabled=True),
        "VIN": st.column_config.TextColumn(disabled=True),
        "Color": st.column_config.TextColumn(disabled=True),
        "Miles": st.column_config.TextColumn(disabled=True),
        "Lane": st.column_config.TextColumn(disabled=True),
        "Lot": st.column_config.TextColumn(disabled=True),
        "Auction": st.column_config.TextColumn(disabled=True),
        "Guide": st.column_config.TextColumn(disabled=True),
        "Status": st.column_config.TextColumn(disabled=True),
    },
    key=f"grid-{picked}-{show}-{len(shown)}",
)

flag_rows = [
    {"vin": row["VIN"], "here": bool(row["HERE"]), "chip": bool(row["CHIP"]), "bg": bool(row["BG"])}
    for _, row in edited.iterrows()
]
expected = [
    {
        "vin": car["vin"],
        "here": bool(flags.get(car["vin"], {}).get("here")),
        "chip": bool(flags.get(car["vin"], {}).get("chip")),
        "bg": bool(flags.get(car["vin"], {}).get("bg")),
    }
    for car in shown
]
if flag_rows != expected:
    db.save_flags(picked, flag_rows)
    flags = db.flags_for(picked)

chosen = edited[edited["Print"] == True]  # noqa: E712
by_vin = {car["vin"]: car for car in cars}
to_print = [by_vin[vin] for vin in chosen["VIN"].tolist() if vin in by_vin and not by_vin[vin]["dead"]]
if chosen.shape[0] and not to_print:
    st.warning("Dead deals stay on the list, but they are not printed.")
elif to_print:
    html = guides_document(to_print, AS_OF)
    label = f"Print {len(to_print)} buyers guide{'s' if len(to_print) != 1 else ''}"
    st.iframe(print_launcher(html, ",".join(car["vin"] for car in to_print), picked, label), height=48)
    st.caption("Prints the make, model, year, VIN, purchase location, and X marks onto the blank form. Letter paper, 100% scale, no margins. Allow the pop-up. BG is checked when the print window opens.")
else:
    st.caption("Check Print on the cars you want, then print the buyers guides.")

if dead and show == "All":
    st.markdown("**Dead deals**")
    st.caption("Crossed off on the boxes sheet. Greyed out, not selectable, and left out of the filters.")
    dead_rows = []
    for car in dead:
        dead_rows.append(
            {
                "Day": struck(car["day_label"], True),
                "Vehicle": struck(f"{car['year'] or ''} {car['make']} {car['model']}".strip(), True),
                "VIN": struck(car["vin"], True),
                "Color": struck(car["color"], True),
                "Miles": struck(car["odometer"], True),
                "Lane": struck(car["lane"], True),
                "Lot": struck(car["lot"], True),
                "Auction": struck(car["auction"], True),
            }
        )
    dead_frame = pd.DataFrame(dead_rows)
    st.dataframe(
        dead_frame.style.set_properties(**{"color": "#8a8175", "text-decoration": "line-through"}),
        hide_index=True,
        width="stretch",
    )
