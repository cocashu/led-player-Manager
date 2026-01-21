import sqlite3
from pathlib import Path
from contextlib import contextmanager
import hashlib
import json

class DBManager:
    def __init__(self, db_path="data/led.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()
        self.ensure_extra_schema()

    @contextmanager
    def get_cursor(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn.cursor()
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def init_db(self):
        """Initialize database with schema if tables don't exist"""
        if not self.db_path.exists() or self.db_path.stat().st_size == 0:
            schema_path = Path(__file__).parent / "sqlite.sql"
            if schema_path.exists():
                with open(schema_path, "r", encoding="utf-8") as f:
                    schema = f.read()
                
                with sqlite3.connect(self.db_path) as conn:
                    conn.executescript(schema)
                    print(f"Database initialized at {self.db_path}")

    def ensure_extra_schema(self):
        """Ensure additional tables/columns exist for upgraded features"""
        with sqlite3.connect(self.db_path) as conn:
            # Create play_logs table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS play_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    media_id INTEGER,
                    schedule_id INTEGER,
                    start_time DATETIME,
                    end_time DATETIME,
                    duration_seconds INTEGER,
                    FOREIGN KEY (media_id) REFERENCES media(id),
                    FOREIGN KEY (schedule_id) REFERENCES schedules(id)
                )
            """)
            # Ensure schedules has text style columns
            def has_column(table, column):
                cur = conn.execute(f"PRAGMA table_info({table})")
                return any(row[1] == column for row in cur.fetchall())
            if not has_column("schedules", "text_size"):
                conn.execute("ALTER TABLE schedules ADD COLUMN text_size INTEGER")
            if not has_column("schedules", "text_color"):
                conn.execute("ALTER TABLE schedules ADD COLUMN text_color TEXT")
            if not has_column("schedules", "bg_color"):
                conn.execute("ALTER TABLE schedules ADD COLUMN bg_color TEXT")
            if not has_column("schedules", "text_scroll_mode"):
                conn.execute("ALTER TABLE schedules ADD COLUMN text_scroll_mode TEXT DEFAULT 'static'")
            if not has_column("schedules", "is_enabled"):
                conn.execute("ALTER TABLE schedules ADD COLUMN is_enabled INTEGER DEFAULT 1")
            if not has_column("schedules", "order_index"):
                conn.execute("ALTER TABLE schedules ADD COLUMN order_index INTEGER DEFAULT 0")
            if not has_column("schedules", "is_enabled"):
                conn.execute("ALTER TABLE schedules ADD COLUMN is_enabled INTEGER DEFAULT 1")
            if not has_column("schedules", "text_scroll_mode"):
                conn.execute("ALTER TABLE schedules ADD COLUMN text_scroll_mode TEXT DEFAULT 'static'")

            if not has_column("screen_config", "schedule_window_enabled"):
                conn.execute("ALTER TABLE screen_config ADD COLUMN schedule_window_enabled INTEGER DEFAULT 0")
            if not has_column("screen_config", "schedule_window_start"):
                conn.execute("ALTER TABLE screen_config ADD COLUMN schedule_window_start TEXT")
            if not has_column("screen_config", "schedule_window_end"):
                conn.execute("ALTER TABLE screen_config ADD COLUMN schedule_window_end TEXT")
            if not has_column("screen_config", "output_mode"):
                conn.execute("ALTER TABLE screen_config ADD COLUMN output_mode TEXT")
            if not has_column("screen_config", "output_targets"):
                conn.execute("ALTER TABLE screen_config ADD COLUMN output_targets TEXT")
            if not has_column("screen_config", "extended_scale_mode"):
                conn.execute("ALTER TABLE screen_config ADD COLUMN extended_scale_mode TEXT")

            conn.execute("INSERT OR IGNORE INTO screen_config (id) VALUES (1)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS camera_config (
                    id INTEGER PRIMARY KEY,
                    enabled INTEGER DEFAULT 0,
                    name TEXT,
                    stream_url TEXT,
                    username TEXT,
                    password TEXT,
                    notes TEXT
                )
            """)
            conn.execute("INSERT OR IGNORE INTO camera_config (id) VALUES (1)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE,
                    password_hash TEXT,
                    is_admin INTEGER DEFAULT 0
                )
            """)
            cur = conn.execute("SELECT COUNT(1) FROM users WHERE username = 'admin'")
            exists = cur.fetchone()[0] if cur else 0
            if not exists:
                ph = hashlib.sha256("admin".encode("utf-8")).hexdigest()
                conn.execute("INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)", ("admin", ph, 1))

    def execute(self, sql, params=()):
        with self.get_cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.lastrowid

    def fetch_all(self, sql, params=()):
        with self.get_cursor() as cursor:
            cursor.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]

    def fetch_one(self, sql, params=()):
        with self.get_cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()
            return dict(row) if row else None

# Global instance
db = DBManager()
