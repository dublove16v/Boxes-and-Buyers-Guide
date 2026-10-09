import re

VIN_OK = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")


def _clean(value) -> str:
    text = str(value or "")
    text = text.replace("\t", " ").replace("\r", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def stock_kind(stock: str) -> str:
    """DealerTrack stock numbers: T or TL is a trade, P or PL is a purchase."""
    token = re.sub(r"[^A-Za-z0-9]", "", _clean(stock)).upper()
    if token.endswith("TL") or token.endswith("T"):
        return "Trade"
    if token.endswith("PL") or token.endswith("P"):
        return "Purchase"
    return ""


def dealer_stock(car: dict) -> str:
    return _clean(car.get("stock") or "")


def intake_label(car: dict) -> str:
    kind = stock_kind(dealer_stock(car))
    if kind:
        return kind
    marked = _clean(car.get("intake"))
    if marked in ("Trade", "Purchase"):
        return marked
    source = _clean(car.get("source"))
    if re.search(r"trade", source, re.I):
        return "Trade"
    if re.search(r"purchas|auction|buy", source, re.I):
        return "Purchase"
    return ""


def _export_stock(car: dict, vin: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]", "", dealer_stock(car)).upper()
    if not token:
        token = vin[-6:]
    if len(token) > 10:
        token = token[-10:]
    return token


def key_advantage_cars(dms_cars: list[dict], boxes_cars: list[dict] | None = None) -> list[dict]:
    """Most recent DealerTrack report plus the most recent boxes list.

    The same VIN is written once. DealerTrack supplies the stock number.
    P or PL is a purchase, T or TL is a trade. A boxes car with no stock
    number is a purchase. Dead deals that are not on the DealerTrack report
    are left out.
    """
    by_vin: dict[str, dict] = {}
    order: list[str] = []

    def remember(car: dict, from_boxes: bool) -> None:
        vin = _clean(car.get("vin")).upper()
        if not vin:
            return
        if from_boxes and car.get("dead") and vin not in by_vin:
            return
        if vin in by_vin:
            row = by_vin[vin]
            for field in ("year", "make", "model", "trim", "color", "odometer"):
                if not row.get(field) and car.get(field):
                    row[field] = car[field]
            if from_boxes:
                for field in ("lane", "lot", "auction"):
                    if car.get(field):
                        row[field] = car[field]
            elif dealer_stock(car):
                row["stock"] = dealer_stock(car)
                row["intake"] = stock_kind(row["stock"]) or row.get("intake") or ""
            return
        row = dict(car)
        row["vin"] = vin
        row["stock"] = dealer_stock(car)
        kind = stock_kind(row["stock"])
        if not kind and "trade" in _clean(car.get("source")).lower():
            kind = "Trade"
        if not kind and from_boxes:
            kind = "Purchase"
        row["intake"] = kind
        if not row.get("auction"):
            row["auction"] = "" if from_boxes else "DealerTrack"
        by_vin[vin] = row
        order.append(vin)

    for car in dms_cars:
        remember(car, False)
    for car in boxes_cars or []:
        remember(car, True)
    return [by_vin[vin] for vin in order]


def key_advantage_txt(cars: list[dict]) -> tuple[str, int]:
    """Tab-delimited vehicle import. No header. Windows line endings.

    VIN, stock (last 6), year, make, model, exterior color, status A, note 1, note 2.
    """
    lines = []
    for car in cars:
        vin = _clean(car.get("vin")).upper()
        if not VIN_OK.match(vin):
            continue
        stock = _export_stock(car, vin)
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
