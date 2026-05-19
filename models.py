import sqlite3
from config import DATABASE_PATH

DAYS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

def get_conn():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                time TEXT NOT NULL,
                days TEXT NOT NULL,
                audio_path TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                volume REAL NOT NULL DEFAULT 1.0,
                duration INTEGER NOT NULL DEFAULT 30
            )
        """)
        # Migración: agrega la columna si la BD ya existía sin ella
        cols = [r[1] for r in conn.execute("PRAGMA table_info(events)").fetchall()]
        if "duration" not in cols:
            conn.execute("ALTER TABLE events ADD COLUMN duration INTEGER NOT NULL DEFAULT 30")
        conn.commit()

def get_all_events():
    with get_conn() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM events ORDER BY time").fetchall()]

def get_event(event_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        return dict(row) if row else None

def create_event(name, time, days, audio_path, active=1, volume=1.0, duration=30):
    days_str = ",".join(days) if isinstance(days, list) else days
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO events (name, time, days, audio_path, active, volume, duration) VALUES (?,?,?,?,?,?,?)",
            (name, time, days_str, audio_path, active, volume, duration)
        )
        conn.commit()
        return cur.lastrowid

def update_event(event_id, name, time, days, audio_path, active, volume, duration):
    days_str = ",".join(days) if isinstance(days, list) else days
    with get_conn() as conn:
        conn.execute(
            "UPDATE events SET name=?, time=?, days=?, audio_path=?, active=?, volume=?, duration=? WHERE id=?",
            (name, time, days_str, audio_path, active, volume, duration, event_id)
        )
        conn.commit()

DAY_LABELS = {
    "lunes": "Lunes", "martes": "Martes", "miercoles": "Miércoles",
    "jueves": "Jueves", "viernes": "Viernes", "sabado": "Sábado", "domingo": "Domingo",
}

def name_exists(name, exclude_id=None):
    with get_conn() as conn:
        if exclude_id:
            row = conn.execute(
                "SELECT id FROM events WHERE LOWER(TRIM(name))=LOWER(TRIM(?)) AND id!=?",
                (name, exclude_id)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM events WHERE LOWER(TRIM(name))=LOWER(TRIM(?))",
                (name,)
            ).fetchone()
        return row is not None

def time_day_conflicts(time, days, exclude_id=None):
    """Devuelve lista de dicts {name, shared_days} con eventos que chocan en hora+día."""
    days_set = set(d.strip() for d in (days if isinstance(days, list) else days.split(",")))
    with get_conn() as conn:
        if exclude_id:
            rows = conn.execute(
                "SELECT name, days FROM events WHERE time=? AND id!=?",
                (time, exclude_id)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT name, days FROM events WHERE time=?",
                (time,)
            ).fetchall()
    conflicts = []
    ordered = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    for row in rows:
        existing = set(d.strip() for d in row["days"].split(","))
        shared = days_set & existing
        if shared:
            shared_ordered = [DAY_LABELS[d] for d in ordered if d in shared]
            conflicts.append({"name": row["name"], "shared_days": shared_ordered})
    return conflicts

def set_audio_path(event_id, audio_path):
    with get_conn() as conn:
        conn.execute("UPDATE events SET audio_path=? WHERE id=?", (audio_path, event_id))
        conn.commit()

def toggle_event(event_id):
    with get_conn() as conn:
        conn.execute("UPDATE events SET active = 1 - active WHERE id=?", (event_id,))
        conn.commit()

def delete_event(event_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM events WHERE id=?", (event_id,))
        conn.commit()
