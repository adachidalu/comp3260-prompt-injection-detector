
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone


# Database location
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "security_audit.db"


def get_connection():
    """Create and return a connection to the SQLite database."""

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    return connection


def initialize_db():
    """
    Create all required database tables if they do not exist.
    """

    with get_connection() as conn:

        # Table 1: Security verdicts
        conn.execute("""
            CREATE TABLE IF NOT EXISTS verdicts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_id TEXT,
                verdict TEXT NOT NULL,
                evidence TEXT,
                reason TEXT,
                timestamp TEXT NOT NULL
            )
        """)

        # Table 2: Mock action requests
        conn.execute("""
            CREATE TABLE IF NOT EXISTS action_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                target TEXT,
                approved INTEGER NOT NULL,
                reason TEXT,
                timestamp TEXT NOT NULL
            )
        """)

        # Table 3: Test results
        conn.execute("""
            CREATE TABLE IF NOT EXISTS test_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_name TEXT NOT NULL,
                status TEXT NOT NULL,
                details TEXT,
                timestamp TEXT NOT NULL
            )
        """)

        conn.commit()


def log_verdict(email_id, verdict, evidence=None, reason=None):
    """Store a security verdict and its supporting evidence."""

    timestamp = datetime.now(timezone.utc).isoformat()

    if not isinstance(evidence, str):
        evidence = json.dumps(evidence) if evidence is not None else None

    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO verdicts
            (email_id, verdict, evidence, reason, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (email_id, verdict, evidence, reason, timestamp))

        return cursor.lastrowid


def log_action_request(action_type, target, approved, reason=None):
    """Store a mock action request and whether it was approved."""

    timestamp = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO action_requests
            (action_type, target, approved, reason, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (action_type, target, int(approved), reason, timestamp))

        return cursor.lastrowid


def log_test_result(test_name, status, details=None):
    """Store the result of a project test."""

    timestamp = datetime.now(timezone.utc).isoformat()

    if not isinstance(details, str):
        details = json.dumps(details) if details is not None else None

    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO test_results
            (test_name, status, details, timestamp)
            VALUES (?, ?, ?, ?)
        """, (test_name, status, details, timestamp))

        return cursor.lastrowid


def get_verdicts():
    """Retrieve all recorded security verdicts."""

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM verdicts
            ORDER BY id DESC
        """).fetchall()

        return [dict(row) for row in rows]


def get_action_requests():
    """Retrieve all recorded mock action requests."""

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM action_requests
            ORDER BY id DESC
        """).fetchall()

        return [dict(row) for row in rows]


def get_test_results():
    #Retrieve all recorded test results.

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM test_results
            ORDER BY id DESC
        """).fetchall()

        return [dict(row) for row in rows]


def get_database_summary():
    #Return the total number of records in each table.

    with get_connection() as conn:

        verdict_count = conn.execute(
            "SELECT COUNT(*) FROM verdicts"
        ).fetchone()[0]

        action_count = conn.execute(
            "SELECT COUNT(*) FROM action_requests"
        ).fetchone()[0]

        test_count = conn.execute(
            "SELECT COUNT(*) FROM test_results"
        ).fetchone()[0]

        return {
            "total_verdicts": verdict_count,
            "total_action_requests": action_count,
            "total_test_results": test_count
        }

