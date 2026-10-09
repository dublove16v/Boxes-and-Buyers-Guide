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
    cols: dict[str, int] = {}
    for index, cell in enumerate(row):
        key = _norm(cell)
        if not key:
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
    if "vin" not in cols:
        return None
    if "description" not in cols and "make" not in cols and "year" not in cols:
        return None
    return cols


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
    cars = []
    seen = set()
    for row in rows[header_at + 1 :]:
        vin = re.sub(r"\s+", "", _cell(row, columns.get("vin"))).upper()
        if not VIN_OK.match(vin) or vin in seen:
            continue
        year_raw = _cell(row, columns.get("year"))
        make_raw = _cell(row, columns.get("make"))
        if year_raw and make_raw:
            year = model_year(year_raw, as_of)
            make = expand_make(make_raw)
            model = _cell(row, columns.get("model"))
        else:
            described = DESC.match(_cell(row, columns.get("description")))
            if not described:
                continue
            year = model_year(described.group(1), as_of)
            make = expand_make(described.group(2))
            model = re.sub(r"\s+", " ", described.group(3)).strip()
        if year is None or not make:
            continue
        seen.add(vin)
        cars.append(
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
            }
        )
    return cars


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
