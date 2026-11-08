"""SQLite helpers and schema."""
import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, workspace_id INTEGER NOT NULL, name TEXT NOT NULL,
    role TEXT NOT NULL, title TEXT
);
CREATE TABLE IF NOT EXISTS guidelines (
    id INTEGER PRIMARY KEY, workspace_id INTEGER NOT NULL, key TEXT, title TEXT NOT NULL, text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY, workspace_id INTEGER NOT NULL, statement TEXT NOT NULL,
    source TEXT, valid_until TEXT, status TEXT NOT NULL DEFAULT 'approved'
);
CREATE TABLE IF NOT EXISTS terms (
    id INTEGER PRIMARY KEY, workspace_id INTEGER NOT NULL, kind TEXT NOT NULL,
    avoid TEXT NOT NULL, preferred TEXT, reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY, workspace_id INTEGER NOT NULL, type TEXT NOT NULL, name TEXT NOT NULL, value TEXT
);
CREATE TABLE IF NOT EXISTS content (
    id INTEGER PRIMARY KEY, workspace_id INTEGER NOT NULL, creator_id INTEGER NOT NULL,
    title TEXT NOT NULL, channel TEXT, intent TEXT, status TEXT NOT NULL DEFAULT 'draft',
    parse_notes TEXT DEFAULT '[]', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS versions (
    id INTEGER PRIMARY KEY, content_id INTEGER NOT NULL, number INTEGER NOT NULL,
    body TEXT NOT NULL, created_by INTEGER NOT NULL, created_at TEXT NOT NULL,
    note TEXT, dropped INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY, version_id INTEGER NOT NULL, rule TEXT NOT NULL, category TEXT NOT NULL,
    severity TEXT NOT NULL, message TEXT NOT NULL, why TEXT NOT NULL,
    source_type TEXT NOT NULL, source_id INTEGER NOT NULL, source_label TEXT, source_quote TEXT NOT NULL,
    confidence REAL NOT NULL, start INTEGER, end INTEGER, original TEXT,
    replacement TEXT, advice TEXT, needs_human INTEGER NOT NULL DEFAULT 0, intent_conflict TEXT,
    state TEXT NOT NULL DEFAULT 'open', decided_by INTEGER, decision_reason TEXT, decided_at TEXT
);
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY, content_id INTEGER NOT NULL, version_id INTEGER, user_id INTEGER NOT NULL,
    body TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY, content_id INTEGER, actor_id INTEGER, action TEXT NOT NULL,
    detail TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_findings_version ON findings(version_id);
CREATE INDEX IF NOT EXISTS idx_versions_content ON versions(content_id);
"""


def connect(path):
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn):
    conn.executescript(SCHEMA)
    conn.commit()
