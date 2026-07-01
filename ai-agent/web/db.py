"""SQLite 数据库层 — 用户认证 + 项目 + 研究会话。"""

import json
import sqlite3
import threading
from pathlib import Path

import bcrypt

_local = threading.local()


def get_db(db_path: str) -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return _local.conn


def init_db(db_path: str):
    conn = get_db(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            username   TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS projects (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL REFERENCES users(id),
            name       TEXT NOT NULL,
            saved_urls TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS research_sessions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL REFERENCES users(id),
            project_id   INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            type         TEXT DEFAULT 'research',
            query        TEXT NOT NULL,
            data_sources TEXT DEFAULT '[]',
            skill_used   TEXT,
            status       TEXT DEFAULT 'running',
            messages     TEXT DEFAULT '[]',
            report_md    TEXT DEFAULT '',
            created_at   TEXT DEFAULT (datetime('now')),
            updated_at   TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_sessions_user ON research_sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_project ON research_sessions(project_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_created ON research_sessions(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);
    """)
    conn.commit()


# ── 用户 ──────────────────────────────────────────────────────────

def create_user(db_path: str, username: str, password: str) -> dict:
    conn = get_db(db_path)
    try:
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, pw_hash))
        conn.commit()
        return {"ok": True}
    except sqlite3.IntegrityError:
        return {"ok": False, "error": "用户名已存在"}


def verify_user(db_path: str, username: str, password: str) -> dict:
    conn = get_db(db_path)
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not row:
        return {"ok": False, "error": "用户名不存在"}
    if not bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
        return {"ok": False, "error": "密码错误"}
    return {"ok": True, "user": dict(row)}


def get_user_count(db_path: str) -> int:
    return get_db(db_path).execute("SELECT COUNT(*) FROM users").fetchone()[0]


# ── 项目 ──────────────────────────────────────────────────────────

def create_project(db_path: str, user_id: int, name: str) -> int:
    conn = get_db(db_path)
    cur = conn.execute("INSERT INTO projects (user_id, name) VALUES (?, ?)", (user_id, name))
    conn.commit()
    return cur.lastrowid


def list_projects(db_path: str, user_id: int) -> list[dict]:
    conn = get_db(db_path)
    rows = conn.execute(
        """SELECT p.*, COUNT(s.id) as session_count
           FROM projects p
           LEFT JOIN research_sessions s ON s.project_id = p.id
           WHERE p.user_id = ?
           GROUP BY p.id
           ORDER BY p.created_at DESC""",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_project(db_path: str, project_id: int) -> dict | None:
    row = get_db(db_path).execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["saved_urls"] = json.loads(d.get("saved_urls", "[]") or "[]")
    return d


def rename_project(db_path: str, project_id: int, name: str):
    get_db(db_path).execute("UPDATE projects SET name = ? WHERE id = ?", (name, project_id)).connection.commit()


def add_project_url(db_path: str, project_id: int, url: str):
    p = get_project(db_path, project_id)
    if p:
        urls = p.get("saved_urls", [])
        if url not in urls:
            urls.append(url)
            get_db(db_path).execute("UPDATE projects SET saved_urls = ? WHERE id = ?",
                                   (json.dumps(urls), project_id)).connection.commit()


def remove_project_url(db_path: str, project_id: int, url: str):
    p = get_project(db_path, project_id)
    if p:
        urls = p.get("saved_urls", [])
        if url in urls:
            urls.remove(url)
            get_db(db_path).execute("UPDATE projects SET saved_urls = ? WHERE id = ?",
                                   (json.dumps(urls), project_id)).connection.commit()


# ── 项目笔记（文本数据源）─────────────────────────────────────────

def _ensure_notes_table(db_path: str):
    get_db(db_path).execute("""
        CREATE TABLE IF NOT EXISTS project_notes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            title      TEXT NOT NULL,
            content    TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """).connection.commit()


def add_project_note(db_path: str, project_id: int, title: str, content: str):
    _ensure_notes_table(db_path)
    get_db(db_path).execute(
        "INSERT INTO project_notes (project_id, title, content) VALUES (?, ?, ?)",
        (project_id, title, content),
    ).connection.commit()


def get_project_notes(db_path: str, project_id: int) -> list[dict]:
    _ensure_notes_table(db_path)
    rows = get_db(db_path).execute(
        "SELECT * FROM project_notes WHERE project_id = ? ORDER BY created_at DESC",
        (project_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_project(db_path: str, project_id: int):
    conn = get_db(db_path)
    conn.execute("DELETE FROM research_sessions WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()


# ── 研究会话 ──────────────────────────────────────────────────────

def create_session(db_path: str, user_id: int, query: str,
                   project_id: int | None = None, session_type: str = "research") -> int:
    conn = get_db(db_path)
    cur = conn.execute(
        "INSERT INTO research_sessions (user_id, project_id, type, query) VALUES (?, ?, ?, ?)",
        (user_id, project_id, session_type, query),
    )
    conn.commit()
    return cur.lastrowid


def update_session(db_path: str, session_id: int, **kwargs):
    conn = get_db(db_path)
    sets = []
    vals = []
    for k, v in kwargs.items():
        sets.append(f"{k} = ?")
        vals.append(v if not isinstance(v, (list, dict)) else json.dumps(v, ensure_ascii=False))
    sets.append("updated_at = datetime('now')")
    vals.append(session_id)
    conn.execute(f"UPDATE research_sessions SET {', '.join(sets)} WHERE id = ?", vals)
    conn.commit()


def get_session(db_path: str, session_id: int) -> dict | None:
    row = get_db(db_path).execute("SELECT * FROM research_sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["messages"] = json.loads(d["messages"] or "[]")
    d["data_sources"] = json.loads(d["data_sources"] or "[]")
    return d


def list_sessions(db_path: str, user_id: int, project_id: int | None = None, session_type: str | None = None,
                  limit: int = 100) -> list[dict]:
    conn = get_db(db_path)
    where = ["user_id = ?"]
    params = [user_id]
    if project_id is not None:
        where.append("project_id = ?" if project_id > 0 else "project_id IS NULL")
        if project_id > 0:
            params.append(project_id)
    if session_type:
        where.append("type = ?")
        params.append(session_type)
    params.append(limit)
    rows = conn.execute(
        f"SELECT id, project_id, type, query, data_sources, status, created_at FROM research_sessions "
        f"WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ?",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def delete_session(db_path: str, session_id: int):
    get_db(db_path).execute("DELETE FROM research_sessions WHERE id = ?", (session_id,)).connection.commit()


def move_session(db_path: str, session_id: int, project_id: int | None):
    get_db(db_path).execute(
        "UPDATE research_sessions SET project_id = ? WHERE id = ?", (project_id, session_id)
    ).connection.commit()
