import csv
import re
from io import BytesIO, StringIO

MAKES = {
    "ACUR": "Acura",
    "ALFA": "Alfa Romeo",
    "AUDI": "Audi",
    "BENT": "Bentley",
    "BMW": "BMW",
    "BUIC": "Buick",
    "CADI": "Cadillac",
    "CHEV": "Chevrolet",
    "CHRY": "Chrysler",
    "DODG": "Dodge",
    "FIAT": "Fiat",
    "FORD": "Ford",
    "GENE": "Genesis",
    "GMC": "GMC",
    "HOND": "Honda",
    "HUMM": "Hummer",
    "HYUN": "Hyundai",
    "INFI": "Infiniti",
    "ISUZ": "Isuzu",
    "JAGU": "Jaguar",
    "JEEP": "Jeep",
    "KIA": "Kia",
    "LAMB": "Lamborghini",
    "LAND": "Land Rover",
    "LEXS": "Lexus",
    "LEXU": "Lexus",
    "LINC": "Lincoln",
    "LNDR": "Land Rover",
    "LOTU": "Lotus",
    "LUCI": "Lucid",
    "MASE": "Maserati",
    "MAZD": "Mazda",
    "MERC": "Mercedes-Benz",
    "MERZ": "Mercedes-Benz",
    "MITS": "Mitsubishi",
    "MNNI": "Mini",
    "MINI": "Mini",
    "NISS": "Nissan",
    "OLDS": "Oldsmobile",
    "PLYM": "Plymouth",
    "POLE": "Polestar",
    "PONT": "Pontiac",
    "PORS": "Porsche",
    "RAM": "Ram",
    "SCIO": "Scion",
    "SUBA": "Subaru",
    "SUZU": "Suzuki",
    "TESL": "Tesla",
    "TOYO": "Toyota",
    "VOLK": "Volkswagen",
    "VOLV": "Volvo",
}
DESC = re.compile(r"^(\d{2}|\d{4})\s+([A-Za-z0-9]{2,5})\s+(.+)$")
VIN_OK = re.compile(r"^[A-HJ-NPR-Z0-9]{11,17}$")


def expand_make(code: str) -> str:
    key = code.strip().upper()
    if key in MAKES:
        return MAKES[key]
    if len(key) <= 3:
        return key
    return key[:1].upper() + key[1:].lower()


def model_year(code: str, as_of: int) -> int | None:
    if re.fullmatch(r"\d{4}", code):
        year = int(code)
        return year if 1980 <= year <= as_of + 2 else None
    if not re.fullmatch(r"\d{2}", code):
        return None
    yy = int(code)
    pivot = (as_of % 100) + 1
    return 1900 + yy if yy > pivot else 2000 + yy


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9#]+", " ", value.lower()).strip()


def _columns(row: list[str]) -> dict | None:
    cols: dict = {}
    for index, cell in enumerate(row):
        key = _norm(cell)
        if not key:
            continue
        trade = _trade_field(key)
        if trade:
            slot, field = trade
            cols.setdefault("trade_slots", {}).setdefault(slot, {})[field] = index
            continue
        if key == "vin" or key.endswith(" vin"):
            cols["vin"] = index
        elif "stock" in key:
            cols["stock"] = index
        elif "description" in key or key == "vehicle":
            cols["description"] = index
        elif key in ("year", "yr"):
            cols["year"] = index
        elif key == "make":
            cols["make"] = index
        elif key == "model":
            cols["model"] = index
        elif "mile" in key or key in ("odo",) or "odometer" in key:
            cols["miles"] = index
        elif "exterior" in key or key == "color":
            cols["color"] = index
        elif key == "trim":
            cols["trim"] = index
        elif key in ("source", "acquisition") or key in ("deal type", "stock type", "inventory source"):
            cols["source"] = index
    if "vin" not in cols and not cols.get("trade_slots"):
        return None
    if (
        "vin" in cols
        and "description" not in cols
        and "make" not in cols
        and "year" not in cols
        and not cols.get("trade_slots")
    ):
        return None
    return cols


def _trade_field(key: str) -> tuple[str, str] | None:
    match = re.match(
        r"trade(?:\s*in)?\s*(\d*)\s*(vin|year|yr|make|model|trim|color|stock|odometer|mileage|miles|odo)\b",
        key,
    )
    if not match:
        return None
    slot = match.group(1) or "1"
    field = match.group(2)
    if field == "yr":
        field = "year"
    elif field in ("mileage", "miles", "odo"):
        field = "odometer"
    return slot, field


def _cell(row: list[str], index: int | None) -> str:
    if index is None or index < 0 or index >= len(row):
        return ""
    return row[index].strip()


def _miles(raw: str) -> str:
    try:
        number = float(str(raw).replace(",", ""))
    except ValueError:
        return ""
    if number <= 0:
        return ""
    return f"{round(number):,}"


def vehicles_from_table(rows: list[list[str]], as_of: int) -> list[dict]:
    columns = None
    header_at = -1
    for index, row in enumerate(rows[:40]):
        found = _columns(row)
        if found:
            columns = found
            header_at = index
            break
    if not columns:
        return []
    by_vin: dict[str, dict] = {}

    def keep(car: dict) -> None:
        vin = car["vin"]
        old = by_vin.get(vin)
        if old is None or ("trade" in car.get("source", "").lower() and "trade" not in old.get("source", "").lower()):
            by_vin[vin] = car

    for row in rows[header_at + 1 :]:
        if "vin" in columns:
            vin = re.sub(r"\s+", "", _cell(row, columns.get("vin"))).upper()
            if VIN_OK.match(vin):
                year_raw = _cell(row, columns.get("year"))
                make_raw = _cell(row, columns.get("make"))
                if year_raw and make_raw:
                    year = model_year(year_raw, as_of)
                    make = expand_make(make_raw)
                    model = _cell(row, columns.get("model"))
                else:
                    described = DESC.match(_cell(row, columns.get("description")))
                    year = model_year(described.group(1), as_of) if described else None
                    make = expand_make(described.group(2)) if described else ""
                    model = re.sub(r"\s+", " ", described.group(3)).strip() if described else ""
                if year is not None and make:
                    keep(
                        {
                            "vin": vin,
                            "year": year,
                            "make": make,
                            "model": model,
                            "trim": _cell(row, columns.get("trim")),
                            "color": _cell(row, columns.get("color")),
                            "odometer": _miles(_cell(row, columns.get("miles"))),
                            "lane": "",
                            "lot": _cell(row, columns.get("stock")),
                            "auction": "",
                            "day_label": "In stock",
                            "sort_key": "0000-00-01",
                            "dead": False,
                            "source": _cell(row, columns.get("source")),
                        }
                    )
        for fields in (columns.get("trade_slots") or {}).values():
            vin = re.sub(r"\s+", "", _cell(row, fields.get("vin"))).upper()
            if not VIN_OK.match(vin):
                continue
            year = model_year(_cell(row, fields.get("year")), as_of)
            make = expand_make(_cell(row, fields.get("make")))
            if year is None or not make:
                continue
            keep(
                {
                    "vin": vin,
                    "year": year,
                    "make": make,
                    "model": _cell(row, fields.get("model")),
                    "trim": _cell(row, fields.get("trim")),
                    "color": _cell(row, fields.get("color")),
                    "odometer": _miles(_cell(row, fields.get("odometer"))),
                    "lane": "",
                    "lot": _cell(row, fields.get("stock")),
                    "auction": "",
                    "day_label": "Trade",
                    "sort_key": "0000-00-01",
                    "dead": False,
                    "source": "Trade",
                }
            )
    return list(by_vin.values())


def _table_from_excel(data: bytes) -> list[list[str]]:
    import pandas as pd

    frame = pd.read_excel(BytesIO(data), header=None, dtype=str)
    frame = frame.fillna("")
    return [[str(value).strip() for value in row] for row in frame.itertuples(index=False)]


def parse_dms_file(data: bytes, filename: str, as_of: int) -> list[dict]:
    lower = filename.lower()
    if lower.endswith(".csv") or lower.endswith(".txt"):
        text = data.decode("utf-8-sig", errors="replace")
        rows = [[cell.strip() for cell in row] for row in csv.reader(StringIO(text))]
    else:
        rows = _table_from_excel(data)
    return vehicles_from_table(rows, as_of)
