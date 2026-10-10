import base64
import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Boxes and Buyer's Guide Tool", page_icon="static/logo.png", layout="wide")

try:
    import db
    from guide_html import guides_document, marks_for_year
    from key_advantage import key_advantage_cars, key_advantage_txt, stock_kind
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

AUCTION_COLORS = {
    "manheim new jersey": "#1d4e89",
    "manheim pennsylvania": "#1f7a4d",
    "bel air auto auction": "#b45309",
    "manheim albany": "#6d28d9",
    "manheim new york": "#0f766e",
    "waverly": "#9a3412",
    "manheim new england": "#1e3a8a",
    "manheim maryland": "#9f1239",
    "manheim ny metro skyline": "#0369a1",
    "manheim rochester": "#7c3aed",
    "harrisburg": "#a16207",
    "manheim palm beach": "#c2410c",
    "manheim orlando": "#0e7490",
    "manheim baltimore-washington": "#7f1d1d",
    "manheim dallas": "#3f6212",
    "manheim tampa": "#be123c",
    "manheim chicago": "#312e81",
    "mycentral auction": "#365314",
    "trade": "#44403c",
}
AUCTION_FALLBACK = ("#1d4e89", "#1f7a4d", "#b45309", "#6d28d9", "#0f766e", "#9a3412", "#9f1239", "#0369a1")


def auction_color(name: str) -> str:
    key = re.sub(r"\s+", " ", str(name or "")).strip().lower().replace("wavlery", "waverly")
    if not key:
        return "#1c1915"
    if key in AUCTION_COLORS:
        return AUCTION_COLORS[key]
    return AUCTION_FALLBACK[sum(ord(char) for char in key) % len(AUCTION_FALLBACK)]


def auction_html(name: str) -> str:
    text = str(name or "").strip()
    if not text:
        return ""
    return f'<span style="color:{auction_color(text)};font-weight:700">{html.escape(text)}</span>'


def boxes_download_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url.strip())
    host = parsed.netloc.lower()
    if "docs.google.com" in host and "/spreadsheets/" in parsed.path and "/d/" in parsed.path:
        file_id = parsed.path.split("/d/", 1)[1].split("/", 1)[0]
        return f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx"
    if "drive.google.com" in host or "drive.usercontent.google.com" in host:
        file_id = ""
        if "/d/" in parsed.path:
            file_id = parsed.path.split("/d/", 1)[1].split("/", 1)[0]
        else:
            file_id = urllib.parse.parse_qs(parsed.query).get("id", [""])[0]
        if file_id:
            return f"https://drive.google.com/uc?export=download&id={file_id}"
    return url.strip()


def fetch_boxes(url: str) -> tuple[bytes, str]:
    request = urllib.request.Request(boxes_download_url(url), headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read()
        disposition = response.headers.get("Content-Disposition", "")
    sniff = data[:40].lstrip().lower()
    if sniff.startswith(b"<!doctype") or sniff.startswith(b"<html"):
        raise RuntimeError("Share that file as anyone with the link, then paste the link again.")
    name = "boxes.xlsx"
    match = re.search(r"filename\*?=(?:UTF-8''|\"?)([^\";]+)", disposition, re.I)
    if match:
        name = urllib.parse.unquote(match.group(1)).strip().strip('"')
    if Path(name).suffix.lower() not in {".xlsx", ".xls", ".csv"}:
        name = f"{Path(name).stem or 'boxes'}.xlsx"
    return data, name


def pull_boxes_link() -> str:
    saved = db.load_boxes_link()
    url = str(saved.get("url") or "").strip()
    if not url:
        return "empty"
    pulled_at = str(saved.get("pulled_at") or "")
    if saved.get("digest") and pulled_at:
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(pulled_at)
        except ValueError:
            age = None
        if age is not None and age.total_seconds() < 25:
            return "same"
    try:
        data, filename = fetch_boxes(url)
    except Exception as exc:
        message = str(exc).strip() or "Could not open that boxes link."
        db.save_boxes_link(url, str(saved.get("name") or ""), str(saved.get("digest") or ""), message[:240])
        return "error"
    digest = hashlib.sha256(data).hexdigest()
    if digest == saved.get("digest"):
        if saved.get("error"):
            db.save_boxes_link(url, str(saved.get("name") or ""), digest, "")
        return "same"
    cars = parse_boxes_file(data, filename)
    if not cars:
        db.save_boxes_link(url, Path(filename).stem, str(saved.get("digest") or ""), "That link did not have any cars.")
        return "error"
    name = Path(filename).stem
    week_id = db.save_week(name, week_date_from_name(name), cars)
    db.save_boxes_link(url, name, digest, "")
    st.session_state["week_id"] = week_id
    return "updated"


def print_launcher(document: str) -> str:
    payload = json.dumps(document).replace("</", "<\\/")
    return f"""<!doctype html>
<html>
<body style="margin:0;background:transparent;font-family:sans-serif;">
<script>
const doc = {payload};
const w = window.open("", "_blank");
if (!w) {{
  document.body.textContent = "Allow pop-ups for this site, then click Print again.";
}} else {{
  w.document.open();
  w.document.write(doc);
  w.document.close();
  setTimeout(function () {{ w.focus(); w.print(); }}, 400);
}}
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
    html, body, .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stSidebar"],
    [data-testid="stMarkdown"],
    [data-testid="stHeading"],
    [data-testid="stWidgetLabel"],
    [data-testid="stCaptionContainer"],
    [data-testid="stDataFrame"],
    [data-testid="stSelectbox"],
    [data-testid="stRadio"],
    [data-testid="stCheckbox"],
    [data-testid="stTextInput"],
    [data-testid="stFileUploader"],
    [data-testid="stDownloadButton"],
    label, p, button, input, textarea, select, .stMarkdown, .stCaption {{
      font-family: "Century Gothic Pro", "Century Gothic", sans-serif !important;
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


def car_line(car: dict) -> str:
    vin = str(car.get("vin") or "").upper()
    title = " ".join(
        part
        for part in (str(car.get("year") or ""), car.get("make") or "", car.get("model") or "")
        if str(part).strip()
    )
    bits = [title, vin[-6:] if vin else "", car.get("color") or ""]
    stock = str(car.get("stock") or "").strip()
    if stock:
        bits.append(stock)
    return " · ".join(bit for bit in bits if bit)


def matches_search(car: dict, query: str) -> bool:
    if not query.strip():
        return True
    blob = " ".join(
        str(car.get(key) or "")
        for key in ("year", "make", "model", "vin", "color", "day_label", "auction", "stock")
    ).lower()
    return query.strip().lower() in blob


def flag_box(label: str, key: str, default: bool) -> bool:
    if key not in st.session_state:
        st.session_state[key] = bool(default)
    return st.checkbox(label, key=key)


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
                "Year": car["year"] or "",
                "Vehicle": f"{car['make']} {car['model']}".strip(),
                "VIN": car["vin"],
                "Day": car["day_label"],
                "Color": car["color"],
                "Miles": car["odometer"],
                "Lane": car["lane"],
                "Lot": car["lot"],
                "Auction": car["auction"],
                "Guide": warranty_label(car["year"]),
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
db.apply_dead_catalog()
db.apply_highlight_flags()
if imported:
    st.toast(f"Loaded {imported} weeks from the boxes folder.")

weeks = db.list_weeks()
dms_name, dms_cars = db.load_dms()
added_intake = db.sync_intake(dms_cars)
if added_intake:
    st.toast(f"Added {added_intake} to Trades & Purchases.")
    weeks = db.list_weeks()
boxes_weeks = [week for week in weeks if week["id"] != db.INTAKE_ID]


@st.fragment(run_every="30s")
def watch_boxes_link() -> None:
    if pull_boxes_link() == "updated":
        st.toast("Updated the boxes list.")
        st.rerun(scope="app")


watch_boxes_link()

with st.sidebar:
    st.header("This week")
    saved_link = db.load_boxes_link()
    if "boxes-link-input" not in st.session_state:
        st.session_state["boxes-link-input"] = saved_link["url"]
    link = st.text_input(
        "Boxes link",
        key="boxes-link-input",
        help="Google Sheet or Drive file, shared as anyone with the link. Changes load on their own.",
    )
    if link.strip() != saved_link["url"]:
        db.save_boxes_link(link.strip())
        st.rerun()
    if saved_link["error"]:
        st.caption(saved_link["error"])
    elif saved_link["url"]:
        st.caption(f"Watching {saved_link['name'] or 'the boxes list'}.")
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
    dms_file = st.file_uploader(
        "DealerTrack report",
        type=["xlsx", "xls", "csv"],
        help="Trades are stock numbers ending in T or TL. Purchases end in P or PL.",
    )
    if dms_file is not None and st.session_state.get("dms_token") != (getattr(dms_file, "file_id", None) or dms_file.name):
        stock = parse_dms_file(dms_file.getvalue(), dms_file.name, AS_OF)
        if not stock:
            st.error("No vehicles found in that DealerTrack report.")
        else:
            db.save_dms(dms_file.name, stock)
            st.session_state["dms_token"] = getattr(dms_file, "file_id", None) or dms_file.name
            st.rerun()
    if dms_name:
        purchase_on_report = sum(1 for car in dms_cars if stock_kind(str(car.get("stock") or "")) == "Purchase")
        trade_on_report = sum(1 for car in dms_cars if stock_kind(str(car.get("stock") or "")) == "Trade")
        st.caption(f"{dms_name} · {purchase_on_report} purchases (P/PL) · {trade_on_report} trades (T/TL)")
    latest_boxes = db.week_vehicles(boxes_weeks[0]["id"]) if boxes_weeks else []
    export_cars = key_advantage_cars(dms_cars, latest_boxes)
    export_body, export_count = key_advantage_txt(export_cars)
    purchase_count = sum(1 for car in export_cars if car.get("intake") == "Purchase" and key_advantage_txt([car])[1])
    trade_count = sum(1 for car in export_cars if car.get("intake") == "Trade" and key_advantage_txt([car])[1])
    export_label = boxes_weeks[0]["name"] if boxes_weeks else (Path(dms_name).stem if dms_name else "KeyAdvantage")
    export_name = re.sub(r"[^A-Za-z0-9._-]+", "_", export_label).strip("_") or "KeyAdvantage"
    st.download_button(
        f"Export Key Advantage ({export_count})",
        data=export_body.encode("utf-8"),
        file_name=f"{export_name}_KeyAdvantage.txt",
        mime="text/plain",
        disabled=export_count == 0,
    )
    if export_count:
        st.caption(f"Newest boxes list and DealerTrack report. {purchase_count} purchases · {trade_count} trades.")
    else:
        st.caption("Upload a boxes sheet and a DealerTrack report to export.")

if not weeks:
    st.info("Upload this week's boxes sheet to start the list. Cars crossed off on the sheet stay on the list as dead deals.")
    st.stop()

boxes_weeks = [week for week in weeks if week["id"] != db.INTAKE_ID]
intake_week = next((week for week in weeks if week["id"] == db.INTAKE_ID), None)
ordered_weeks = ([intake_week] if intake_week else []) + boxes_weeks
labels = {week["id"]: week["name"] for week in ordered_weeks}
default_id = st.session_state.get("week_id") or (boxes_weeks[0]["id"] if boxes_weeks else ordered_weeks[0]["id"])
if default_id not in labels:
    default_id = boxes_weeks[0]["id"] if boxes_weeks else ordered_weeks[0]["id"]
picked = st.selectbox(
    "Buying week",
    options=list(labels),
    index=list(labels).index(default_id),
    format_func=lambda week_id: labels[week_id],
)
st.session_state["week_id"] = picked
if picked == db.INTAKE_ID:
    st.caption("Running list of trades (T/TL) and purchased cars (P/PL). Uploading a DealerTrack report adds new ones. They stay off the boxes weeks.")

search = st.text_input(
    "Search",
    placeholder="Year, make, model, VIN, or color",
    label_visibility="collapsed",
    key="car-search",
)

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
    layout = st.query_params.get("layout", "")
    st.query_params.clear()
    if layout:
        st.query_params["layout"] = layout
    st.rerun()

week_cars = db.week_vehicles(picked)
cars = week_cars
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
    if not matches_search(car, search):
        continue
    shown.append(car)
dead_shown = [car for car in dead if matches_search(car, search)] if show == "All" else []
live = [car for car in cars if not car["dead"]]
st.caption(
    f"{len(live)} coming in · {len(dead)} dead · "
    f"{sum(1 for car in live if flags.get(car['vin'], {}).get('here'))} here · "
    f"{sum(1 for car in live if flags.get(car['vin'], {}).get('chip'))} chip · "
    f"{sum(1 for car in live if flags.get(car['vin'], {}).get('bg'))} bg"
)

st.markdown(
    """
    <style>
    div[data-testid="stVerticalBlockBorderWrapper"] {
      padding: 0.2rem 0.55rem 0.05rem;
      margin-bottom: 0.2rem;
    }
    div[data-testid="stCheckbox"] { min-height: 0; }
    </style>
    """,
    unsafe_allow_html=True,
)
st.html(
    """
    <script>
    (function () {
      const want = window.innerWidth <= 720 ? "mobile" : "desktop";
      const url = new URL(window.location.href);
      if (url.searchParams.get("layout") === want) return;
      url.searchParams.set("layout", want);
      window.location.replace(url.toString());
    })();
    </script>
    """,
    unsafe_allow_javascript=True,
)
mobile = st.query_params.get("layout") == "mobile"

nonce = st.session_state.get("print_nonce", 0)
for vin in st.session_state.pop("clear_print", []):
    st.session_state.pop(f"print-{picked}-{vin}", None)
flag_rows = []
to_print = []

if mobile:
    def car_card(car: dict, dead_deal: bool) -> None:
        line = car_line(car)
        with st.container(border=True):
            if dead_deal:
                st.markdown(
                    f'<p style="margin:0;color:#8c3a32;font-weight:700;text-decoration:line-through;">{html.escape(line)}</p>'
                    + (f'<p style="margin:0;line-height:1.2;">{auction_html(car.get("auction") or "")}</p>' if car.get("auction") else "")
                    + '<p style="margin:0.1rem 0 0;color:#8c3a32;font-size:0.8rem;">Dead deal</p>',
                    unsafe_allow_html=True,
                )
                return
            flag = flags.get(car["vin"], {})
            with st.container(horizontal=True, gap="xsmall", wrap=False, horizontal_alignment="left"):
                here = flag_box("Here", f"here-{picked}-{car['vin']}-{nonce}", bool(flag.get("here")))
                chip = flag_box("Chip", f"chip-{picked}-{car['vin']}-{nonce}", bool(flag.get("chip")))
                bg = flag_box("BG", f"bg-{picked}-{car['vin']}-{nonce}", bool(flag.get("bg")))
                selected = flag_box("Print", f"print-{picked}-{car['vin']}", False)
            st.markdown(
                f'<p style="margin:0.05rem 0 0;font-weight:700;line-height:1.2;">{html.escape(line)}</p>'
                + (f'<p style="margin:0;line-height:1.2;">{auction_html(car.get("auction") or "")}</p>' if car.get("auction") else ""),
                unsafe_allow_html=True,
            )
            flag_rows.append({"vin": car["vin"], "here": here, "chip": chip, "bg": bg})
            if selected:
                to_print.append(car)

    if not shown and not dead_shown:
        st.caption("Nothing matches that search." if search.strip() else "No cars on this list.")
    for car in shown:
        car_card(car, False)
    for car in dead_shown:
        car_card(car, True)
else:
    if shown:
        frame = sheet_frame(shown, flags)
        edited = st.data_editor(
            frame.style.map(lambda value: f"color: {auction_color(value)}; font-weight: 700", subset=["Auction"]),
            hide_index=True,
            width="stretch",
            column_order=[
                "HERE",
                "CHIP",
                "BG",
                "Print",
                "Year",
                "Vehicle",
                "VIN",
                "Day",
                "Color",
                "Miles",
                "Lane",
                "Lot",
                "Auction",
                "Guide",
            ],
            column_config={
                "HERE": st.column_config.CheckboxColumn(required=True),
                "CHIP": st.column_config.CheckboxColumn(required=True),
                "BG": st.column_config.CheckboxColumn(required=True),
                "Print": st.column_config.CheckboxColumn(required=True),
                "Year": st.column_config.TextColumn(disabled=True, width="small"),
                "Vehicle": st.column_config.TextColumn(disabled=True),
                "VIN": st.column_config.TextColumn(disabled=True),
                "Day": st.column_config.TextColumn(disabled=True),
                "Color": st.column_config.TextColumn(disabled=True, width="small"),
                "Miles": st.column_config.TextColumn(disabled=True, width="small"),
                "Lane": st.column_config.TextColumn(disabled=True, width="small"),
                "Lot": st.column_config.TextColumn(disabled=True, width="small"),
                "Auction": st.column_config.TextColumn(disabled=True),
                "Guide": st.column_config.TextColumn(disabled=True, width="small"),
            },
            key=f"grid-{picked}-{show}-{len(shown)}-{nonce}",
        )
        by_vin = {car["vin"]: car for car in shown}
        for _, row in edited.iterrows():
            flag_rows.append(
                {
                    "vin": row["VIN"],
                    "here": bool(row["HERE"]),
                    "chip": bool(row["CHIP"]),
                    "bg": bool(row["BG"]),
                }
            )
            if bool(row["Print"]) and row["VIN"] in by_vin:
                to_print.append(by_vin[row["VIN"]])
    elif search.strip():
        st.caption("Nothing matches that search.")
    if dead_shown:
        st.caption("Dead deals")
        for car in dead_shown:
            st.markdown(
                f'<p style="margin:0;color:#8c3a32;text-decoration:line-through;">{html.escape(car_line(car))}</p>',
                unsafe_allow_html=True,
            )

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

if to_print:
    label = f"Print {len(to_print)} buyers guide{'s' if len(to_print) != 1 else ''}"
    if st.button(label, type="primary"):
        printed_vins = {car["vin"] for car in to_print}
        db.save_flags(
            picked,
            [
                {
                    "vin": row["vin"],
                    "here": row["here"],
                    "chip": row["chip"],
                    "bg": True if row["vin"] in printed_vins else row["bg"],
                }
                for row in flag_rows
            ],
        )
        st.session_state["clear_print"] = list(printed_vins)
        st.session_state["print_job"] = guides_document(to_print, AS_OF)
        st.session_state["print_nonce"] = st.session_state.get("print_nonce", 0) + 1
        st.rerun()
    st.caption("Prints the make, model, year, VIN, purchase location, and X marks onto the blank form. Letter paper, 100% scale, no margins. Allow the pop-up. BG is checked when you hit Print.")
else:
    st.caption("Check Print on the cars you want, then print the buyers guides.")

print_job = st.session_state.pop("print_job", "")
if print_job:
    st.iframe(print_launcher(print_job), height=36)

