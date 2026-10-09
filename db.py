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
        """
    )
    columns = {row[1] for row in conn.execute("pragma table_info(flags)")}
    if "bg" not in columns:
        conn.execute("alter table flags add column bg integer not null default 0")
        conn.execute("update flags set bg = 1 where chip = 1")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save_week(name: str, week_date: str, vehicles: list[dict]) -> str:
    week_id = f"{week_date or 'undated'}:{name}".strip()[:180]
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
              lane, lot, auction, day_label, sort_key, dead
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    car["sort_key"],
                    1 if car["dead"] else 0,
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
               day_label, sort_key, dead
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
