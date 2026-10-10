import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _db_path() -> Path:
    """Community Cloud can mount the repo read-only. Fall back to a writable dir."""
    candidates = [ROOT / "data", Path("/tmp/boxes-desk")]
    for folder in candidates:
        try:
            folder.mkdir(parents=True, exist_ok=True)
            probe = folder / ".write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return folder / "desk.db"
        except OSError:
            continue
    fallback = Path(os.environ.get("TMPDIR", "/tmp")) / "boxes-desk.db"
    return fallback


DB_PATH = _db_path()


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    conn.executescript(
        """
        create table if not exists weeks (
          id text primary key,
          name text not null,
          week_date text not null default '',
          updated_at text not null
        );
        create table if not exists vehicles (
          week_id text not null,
          position integer not null,
          vin text not null,
          year integer,
          make text not null default '',
          model text not null default '',
          trim text not null default '',
          color text not null default '',
          odometer text not null default '',
          lane text not null default '',
          lot text not null default '',
          auction text not null default '',
          day_label text not null default '',
          sort_key text not null default '',
          dead integer not null default 0,
          stock text not null default '',
          primary key (week_id, position)
        );
        create table if not exists flags (
          week_id text not null,
          vin text not null,
          here integer not null default 0,
          chip integer not null default 0,
          bg integer not null default 0,
          primary key (week_id, vin)
        );
        create table if not exists shop (
          id integer primary key check (id = 1),
          labor text not null default '',
          parts text not null default '',
          systems text not null default '',
          duration text not null default ''
        );
        create table if not exists dms (
          id integer primary key check (id = 1),
          name text not null default '',
          payload text not null default '[]'
        );
        create table if not exists boxes_link (
          id integer primary key check (id = 1),
          url text not null default '',
          name text not null default '',
          digest text not null default '',
          pulled_at text not null default '',
          error text not null default ''
        );
        """
    )
    columns = {row[1] for row in conn.execute("pragma table_info(flags)")}
    if "bg" not in columns:
        conn.execute("alter table flags add column bg integer not null default 0")
        conn.execute("update flags set bg = 1 where chip = 1")
    vehicle_columns = {row[1] for row in conn.execute("pragma table_info(vehicles)")}
    if "stock" not in vehicle_columns:
        conn.execute("alter table vehicles add column stock text not null default ''")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save_week(name: str, week_date: str, vehicles: list[dict], week_id: str | None = None) -> str:
    week_id = (week_id or f"{week_date or 'undated'}:{name}").strip()[:180]
    conn = connect()
    with conn:
        conn.execute(
            """
            insert into weeks (id, name, week_date, updated_at)
            values (?, ?, ?, ?)
            on conflict(id) do update set
              name = excluded.name,
              week_date = excluded.week_date,
              updated_at = excluded.updated_at
            """,
            (week_id, name, week_date, _now()),
        )
        conn.execute("delete from vehicles where week_id = ?", (week_id,))
        conn.executemany(
            """
            insert into vehicles (
              week_id, position, vin, year, make, model, trim, color, odometer,
              lane, lot, auction, day_label, sort_key, dead, stock
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    week_id,
                    index,
                    car["vin"],
                    car["year"],
                    car["make"],
                    car["model"],
                    car["trim"],
                    car["color"],
                    car["odometer"],
                    car["lane"],
                    car["lot"],
                    car["auction"],
                    car["day_label"],
                    car.get("sort_key") or "",
                    1 if car.get("dead") else 0,
                    car.get("stock") or "",
                )
                for index, car in enumerate(vehicles)
            ],
        )
    return week_id


def list_weeks() -> list[dict]:
    conn = connect()
    rows = conn.execute(
        "select id, name, week_date from weeks order by week_date desc, updated_at desc"
    ).fetchall()
    return [dict(row) for row in rows]


def week_vehicles(week_id: str) -> list[dict]:
    conn = connect()
    rows = conn.execute(
        """
        select vin, year, make, model, trim, color, odometer, lane, lot, auction,
               day_label, sort_key, dead, stock
        from vehicles
        where week_id = ?
        order by sort_key, position
        """,
        (week_id,),
    ).fetchall()
    cars = []
    for row in rows:
        car = dict(row)
        car["dead"] = bool(car["dead"])
        cars.append(car)
    return cars


def flags_for(week_id: str) -> dict[str, dict]:
    conn = connect()
    rows = conn.execute(
        "select vin, here, chip, bg from flags where week_id = ?",
        (week_id,),
    ).fetchall()
    return {
        row["vin"]: {"here": bool(row["here"]), "chip": bool(row["chip"]), "bg": bool(row["bg"])}
        for row in rows
    }


def save_flags(week_id: str, rows: list[dict]) -> None:
    conn = connect()
    with conn:
        for row in rows:
            vin = str(row["vin"]).upper()
            here = 1 if row.get("here") else 0
            chip = 1 if row.get("chip") else 0
            bg = 1 if row.get("bg") else 0
            if not here and not chip and not bg:
                conn.execute("delete from flags where week_id = ? and vin = ?", (week_id, vin))
            else:
                conn.execute(
                    """
                    insert into flags (week_id, vin, here, chip, bg)
                    values (?, ?, ?, ?, ?)
                    on conflict(week_id, vin) do update set
                      here = excluded.here,
                      chip = excluded.chip,
                      bg = excluded.bg
                    """,
                    (week_id, vin, here, chip, bg),
                )
        _touch_state(conn)


def load_shop() -> dict:
    conn = connect()
    row = conn.execute("select labor, parts, systems, duration from shop where id = 1").fetchone()
    if not row:
        return {"labor": "", "parts": "", "systems": "", "duration": ""}
    return dict(row)


def save_shop(labor: str, parts: str, systems: str, duration: str) -> None:
    conn = connect()
    with conn:
        conn.execute(
            """
            insert into shop (id, labor, parts, systems, duration)
            values (1, ?, ?, ?, ?)
            on conflict(id) do update set
              labor = excluded.labor,
              parts = excluded.parts,
              systems = excluded.systems,
              duration = excluded.duration
            """,
            (labor, parts, systems, duration),
        )


def save_dms(name: str, vehicles: list[dict]) -> None:
    conn = connect()
    with conn:
        conn.execute(
            """
            insert into dms (id, name, payload) values (1, ?, ?)
            on conflict(id) do update set name = excluded.name, payload = excluded.payload
            """,
            (name, json.dumps(vehicles)),
        )
        _touch_state(conn)


def load_dms() -> tuple[str, list[dict]]:
    conn = connect()
    row = conn.execute("select name, payload from dms where id = 1").fetchone()
    if not row:
        return "", []
    try:
        cars = json.loads(row["payload"])
    except json.JSONDecodeError:
        cars = []
    return row["name"] or "", cars if isinstance(cars, list) else []


def load_boxes_link() -> dict:
    conn = connect()
    row = conn.execute("select url, name, digest, pulled_at, error from boxes_link where id = 1").fetchone()
    if not row:
        return {"url": "", "name": "", "digest": "", "pulled_at": "", "error": ""}
    return dict(row)


def save_boxes_link(url: str, name: str = "", digest: str = "", error: str = "") -> None:
    conn = connect()
    with conn:
        conn.execute(
            """
            insert into boxes_link (id, url, name, digest, pulled_at, error)
            values (1, ?, ?, ?, ?, ?)
            on conflict(id) do update set
              url = excluded.url,
              name = excluded.name,
              digest = excluded.digest,
              pulled_at = excluded.pulled_at,
              error = excluded.error
            """,
            (url, name, digest, _now(), error),
        )
        _touch_state(conn)


INTAKE_ID = "intake:trades-purchases"
INTAKE_NAME = "TRADES & PURCHASES"


def sync_intake(dms_cars: list[dict]) -> int:
    """Add DealerTrack trades (T/TL) and purchases (P/PL) to a running sheet.

    Cars already on the sheet stay there. A later report does not remove them
    and does not put them on a boxes week.
    """
    from key_advantage import dealer_stock, stock_kind

    incoming = []
    for car in dms_cars:
        stock = dealer_stock(car)
        kind = stock_kind(stock)
        if kind not in ("Trade", "Purchase") or not car.get("vin"):
            continue
        incoming.append((car, stock, kind))
    if not incoming:
        return 0
    existing = week_vehicles(INTAKE_ID)
    by_vin = {str(car["vin"]).upper(): dict(car) for car in existing}
    added = 0
    changed = False
    for car, stock, kind in incoming:
        vin = str(car["vin"]).upper()
        if vin in by_vin:
            row = by_vin[vin]
            updates = {
                "stock": stock,
                "day_label": f"{kind} · {stock}",
            }
            for field in ("year", "make", "model", "trim", "color", "odometer"):
                if car.get(field):
                    updates[field] = car.get(field)
            if any(str(row.get(field) or "") != str(value or "") for field, value in updates.items()):
                row.update(updates)
                changed = True
            continue
        by_vin[vin] = {
            "vin": vin,
            "year": car.get("year"),
            "make": car.get("make") or "",
            "model": car.get("model") or "",
            "trim": car.get("trim") or "",
            "color": car.get("color") or "",
            "odometer": car.get("odometer") or "",
            "lane": "",
            "lot": "",
            "auction": "",
            "day_label": f"{kind} · {stock}",
            "sort_key": "0000-00-02" if kind == "Trade" else "0000-00-03",
            "dead": False,
            "stock": stock,
        }
        added += 1
    ordered = []
    seen = set()
    for vin, car in by_vin.items():
        if vin not in {str(row["vin"]).upper() for row in existing}:
            ordered.append(car)
            seen.add(vin)
    for car in existing:
        vin = str(car["vin"]).upper()
        if vin not in seen:
            ordered.append(by_vin[vin])
    if not added and not changed:
        return 0
    save_week(INTAKE_NAME, "9999-12-31", ordered, week_id=INTAKE_ID)
    _touch_state(connect())
    return added


def _ensure_meta(conn: sqlite3.Connection) -> None:
    conn.execute("create table if not exists meta (key text primary key, value text)")


def _touch_state(conn: sqlite3.Connection) -> None:
    _ensure_meta(conn)
    stamp = str(int(datetime.now(timezone.utc).timestamp() * 1000))
    conn.execute(
        """
        insert into meta (key, value) values ('user-stamp', ?)
        on conflict(key) do update set value = excluded.value
        """,
        (stamp,),
    )


def touch_state() -> None:
    conn = connect()
    with conn:
        _touch_state(conn)


def state_stamp() -> int:
    conn = connect()
    _ensure_meta(conn)
    row = conn.execute("select value from meta where key = 'user-stamp'").fetchone()
    try:
        return int(row["value"]) if row else 0
    except (TypeError, ValueError):
        return 0


def _set_stamp(stamp: int) -> None:
    conn = connect()
    with conn:
        _ensure_meta(conn)
        conn.execute(
            """
            insert into meta (key, value) values ('user-stamp', ?)
            on conflict(key) do update set value = excluded.value
            """,
            (str(int(stamp)),),
        )


def export_user_state() -> dict:
    """Checks, uploads, trades, and the boxes link. Seed weeks stay in the repo."""
    conn = connect()
    seed_names = {path.stem for path in (ROOT / "seed" / "csv").glob("*.csv")}
    flags = [
        {
            "week_id": row["week_id"],
            "vin": row["vin"],
            "here": bool(row["here"]),
            "chip": bool(row["chip"]),
            "bg": bool(row["bg"]),
        }
        for row in conn.execute("select week_id, vin, here, chip, bg from flags")
    ]
    weeks = []
    for week in conn.execute("select id, name, week_date from weeks"):
        if week["name"] in seed_names:
            continue
        weeks.append(
            {
                "id": week["id"],
                "name": week["name"],
                "week_date": week["week_date"],
                "vehicles": week_vehicles(week["id"]),
            }
        )
    dms_name, dms_cars = load_dms()
    return {
        "stamp": state_stamp(),
        "flags": flags,
        "weeks": weeks,
        "dms": {"name": dms_name, "cars": dms_cars},
        "link": load_boxes_link(),
    }


def import_user_state(state: dict) -> None:
    stamp = int(state.get("stamp") or 0)
    if stamp <= state_stamp():
        return
    for week in state.get("weeks") or []:
        vehicles = week.get("vehicles") or []
        if not week.get("id") or not vehicles:
            continue
        save_week(
            str(week.get("name") or "Boxes"),
            str(week.get("week_date") or ""),
            vehicles,
            week_id=str(week["id"]),
        )
    by_week: dict[str, list[dict]] = {}
    for row in state.get("flags") or []:
        week_id = str(row.get("week_id") or "")
        if week_id:
            by_week.setdefault(week_id, []).append(row)
    for week_id, rows in by_week.items():
        save_flags(week_id, rows)
    dms = state.get("dms") or {}
    cars = dms.get("cars") or []
    if cars:
        save_dms(str(dms.get("name") or "DealerTrack"), cars)
    link = state.get("link") or {}
    if link.get("url"):
        save_boxes_link(
            str(link.get("url") or ""),
            str(link.get("name") or ""),
            str(link.get("digest") or ""),
            str(link.get("error") or ""),
        )
    _set_stamp(stamp)


def apply_dead_catalog() -> int:
    """Mark cars that were struck through on the original boxes workbook."""
    path = ROOT / "seed" / "dead.json"
    if not path.exists():
        return 0
    catalog = json.loads(path.read_text())
    conn = connect()
    weeks = {row["name"]: row["id"] for row in conn.execute("select id, name from weeks")}
    changed = 0
    with conn:
        for name, vins in catalog.items():
            week_id = weeks.get(name)
            if not week_id:
                continue
            wanted = {str(vin).upper() for vin in vins}
            rows = conn.execute(
                "select vin, dead from vehicles where week_id = ?",
                (week_id,),
            ).fetchall()
            turn_on = [row["vin"] for row in rows if row["vin"].upper() in wanted and not row["dead"]]
            turn_off = [row["vin"] for row in rows if row["vin"].upper() not in wanted and row["dead"]]
            for vin in turn_on:
                conn.execute(
                    "update vehicles set dead = 1 where week_id = ? and vin = ?",
                    (week_id, vin),
                )
            for vin in turn_off:
                conn.execute(
                    "update vehicles set dead = 0 where week_id = ? and vin = ?",
                    (week_id, vin),
                )
            changed += len(turn_on) + len(turn_off)
    return changed


def apply_highlight_flags() -> int:
    """Check Here, Chip, and BG for highlighted cars on weeks before 10-7-26."""
    path = ROOT / "seed" / "highlights.json"
    if not path.exists():
        return 0
    catalog = json.loads(path.read_text())
    conn = connect()
    conn.execute("create table if not exists meta (key text primary key, value text)")
    if conn.execute("select 1 from meta where key = 'highlights-before-2026-10-07'").fetchone():
        return 0
    weeks = {
        row["name"]: row["id"]
        for row in conn.execute("select id, name, week_date from weeks")
        if (row["week_date"] or "") < "2026-10-07"
    }
    changed = 0
    with conn:
        for name, vins in catalog.items():
            week_id = weeks.get(name)
            if not week_id:
                continue
            present = {
                row["vin"].upper()
                for row in conn.execute("select vin from vehicles where week_id = ?", (week_id,))
            }
            for vin in vins:
                vin = str(vin).upper()
                if vin not in present:
                    continue
                conn.execute(
                    """
                    insert into flags (week_id, vin, here, chip, bg)
                    values (?, ?, 1, 1, 1)
                    on conflict(week_id, vin) do update set
                      here = 1,
                      chip = 1,
                      bg = 1
                    """,
                    (week_id, vin),
                )
                changed += 1
        conn.execute(
            "insert into meta (key, value) values ('highlights-before-2026-10-07', '1')"
        )
    return changed


def import_seed_csvs() -> int:
    """Load the shipped BOXES folder into the database. Skips weeks already saved."""
    folder = ROOT / "seed" / "csv"
    if not folder.exists():
        return 0
    from parse_boxes import parse_boxes_file, week_date_from_name

    existing = {row["name"] for row in list_weeks()}
    added = 0
    for path in sorted(folder.glob("*.csv")):
        name = path.stem
        if name in existing:
            continue
        cars = parse_boxes_file(path.read_bytes(), path.name)
        if not cars:
            continue
        save_week(name, week_date_from_name(name), cars)
        added += 1
    return added
