import re

VIN_OK = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")


def _clean(value) -> str:
    text = str(value or "")
    text = text.replace("\t", " ").replace("\r", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def intake_label(car: dict) -> str:
    source = _clean(car.get("source") or car.get("intake") or "")
    if re.search(r"trade", source, re.I):
        return "Trade"
    if re.search(r"purchas|auction|buy", source, re.I):
        return "Purchase"
    if source:
        return source
    return "Purchase" if car.get("auction") else "Trade"


def key_advantage_cars(week_cars: list[dict], dms_cars: list[dict]) -> list[dict]:
    """Auction purchases from the boxes week, plus trades from the DealerTrack report.

    When the report has trade-in columns or a trade source, only those trades are
    added. Otherwise every DealerTrack car that is not already a purchase is added
    as a trade. Dead deals are left out. The same VIN is written once.
    """
    chosen = []
    seen = set()
    for car in week_cars:
        if car.get("dead"):
            continue
        vin = _clean(car.get("vin")).upper()
        if vin in seen:
            continue
        seen.add(vin)
        row = dict(car)
        row["vin"] = vin
        row["intake"] = "Purchase"
        chosen.append(row)
    explicit = [car for car in dms_cars if "trade" in _clean(car.get("source")).lower()]
    extras = explicit if explicit else list(dms_cars)
    for car in extras:
        vin = _clean(car.get("vin")).upper()
        if not vin or vin in seen:
            continue
        seen.add(vin)
        row = dict(car)
        row["vin"] = vin
        row["intake"] = "Trade" if intake_label(car) != "Purchase" else "Purchase"
        if not row.get("auction"):
            row["auction"] = "DealerTrack"
        chosen.append(row)
    return chosen


def key_advantage_txt(cars: list[dict]) -> tuple[str, int]:
    """Tab-delimited vehicle import. No header. Windows line endings.

    VIN, stock (last 6), year, make, model, exterior color, status A, note 1, note 2.
    """
    lines = []
    for car in cars:
        vin = _clean(car.get("vin")).upper()
        if not VIN_OK.match(vin):
            continue
        stock = vin[-6:]
        miles = _clean(car.get("odometer"))
        note1 = " · ".join(
            part
            for part in (
                _clean(car.get("trim")),
                f"{miles} mi" if miles else "",
                f"Lane {_clean(car.get('lane'))}" if _clean(car.get("lane")) else "",
                f"Lot {_clean(car.get('lot'))}" if _clean(car.get("lot")) else "",
            )
            if part
        )
        note2 = " · ".join(
            part
            for part in (
                intake_label(car),
                _clean(car.get("auction")),
            )
            if part
        )
        fields = [
            vin,
            stock,
            _clean(car.get("year")),
            _clean(car.get("make")),
            _clean(car.get("model")),
            _clean(car.get("color")),
            "A",
            note1,
            note2,
        ]
        lines.append("\t".join(fields))
    body = "\r\n".join(lines)
    if body:
        body += "\r\n"
    return body, len(lines)
