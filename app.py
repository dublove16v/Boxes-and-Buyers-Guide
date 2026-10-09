import base64
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

import db
from guide_html import guides_document, marks_for_year
from parse_boxes import parse_boxes_file, week_date_from_name
from parse_dms import parse_dms_file

ROOT = Path(__file__).resolve().parent
AS_OF = date.today().year

st.set_page_config(page_title="Boxes and Buyer's Guide Tool", layout="wide")


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
    if marks["as_is"]:
        return "As-Is"
    if marks["limited"]:
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
                "CHIP/BG": bool(flag.get("chip")),
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
shop = db.load_shop()
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
    st.header("Warranty blanks")
    labor = st.text_input("Labor %", shop["labor"])
    parts = st.text_input("Parts %", shop["parts"])
    systems = st.text_area("Systems covered", shop["systems"])
    duration = st.text_area("Duration", shop["duration"])
    if (labor, parts, systems, duration) != (
        shop["labor"],
        shop["parts"],
        shop["systems"],
        shop["duration"],
    ):
        db.save_shop(labor, parts, systems, duration)
        shop = {"labor": labor, "parts": parts, "systems": systems, "duration": duration}

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

week_cars = db.week_vehicles(picked)
cars = merge_stock(week_cars, dms_cars)
flags = db.flags_for(picked)
frame = sheet_frame(cars, flags)
live = [car for car in cars if not car["dead"]]
st.caption(
    f"{len(live)} coming in · {sum(1 for car in cars if car['dead'])} dead · "
    f"{sum(1 for car in live if flags.get(car['vin'], {}).get('here'))} here · "
    f"{sum(1 for car in live if flags.get(car['vin'], {}).get('chip'))} chip/bg"
)

edited = st.data_editor(
    frame,
    hide_index=True,
    width="stretch",
    column_config={
        "HERE": st.column_config.CheckboxColumn(required=True),
        "CHIP/BG": st.column_config.CheckboxColumn(required=True),
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
    key=f"grid-{picked}-{len(cars)}",
)

flag_rows = [
    {"vin": row["VIN"], "here": bool(row["HERE"]), "chip": bool(row["CHIP/BG"])}
    for _, row in edited.iterrows()
]
if flag_rows != [
    {"vin": car["vin"], "here": bool(flags.get(car["vin"], {}).get("here")), "chip": bool(flags.get(car["vin"], {}).get("chip"))}
    for car in cars
]:
    db.save_flags(picked, flag_rows)

chosen = edited[edited["Print"] == True]  # noqa: E712
by_vin = {car["vin"]: car for car in cars}
to_print = [by_vin[vin] for vin in chosen["VIN"].tolist() if vin in by_vin and not by_vin[vin]["dead"]]
if chosen.shape[0] and not to_print:
    st.warning("Dead deals stay on the list, but they are not printed.")
elif to_print:
    html = guides_document(to_print, shop, AS_OF)
    st.download_button(
        f"Download {len(to_print)} buyers guide{'s' if len(to_print) != 1 else ''}",
        data=html.encode(),
        file_name="buyers-guides.html",
        mime="text/html",
    )
    st.caption("Open the downloaded file. It sends itself to the printer. Use letter paper at 100% scale.")
else:
    st.caption("Check Print on the cars you want, then download the buyers guides.")
