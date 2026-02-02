#!/usr/bin/env python3
"""Initialize SQLite database for the trivia app.

This script is responsible for:
- Ensuring the SQLite database exists and is reachable.
- Creating/maintaining the schema (including trivia tables).
- Seeding a starter set of trivia questions (idempotent).
- Maintaining db_visualizer/sqlite.env using the authoritative DB path.

Authoritative DB path source:
- database/db_connection.txt (line: "# File path: ...")

Notes:
- We avoid hardcoding absolute paths in code; instead we read them from
  db_connection.txt which is treated as the authoritative reference for this repo.
"""

import os
import re
import sqlite3
from typing import Optional, Sequence, Tuple


DB_NAME_FALLBACK = "myapp.db"


# PUBLIC_INTERFACE
def get_db_path_from_connection_file(connection_file: str = "db_connection.txt") -> str:
    """Return the authoritative SQLite DB file path from db_connection.txt.

    Args:
        connection_file: Path to db_connection.txt (relative to this script's CWD).

    Returns:
        Absolute path to SQLite database file.

    Raises:
        RuntimeError: If the file cannot be read or does not contain a File path line.
    """
    try:
        content = open(connection_file, "r", encoding="utf-8").read()
    except Exception as exc:
        raise RuntimeError(
            f"Could not read {connection_file}. It must exist and contain '# File path: ...'."
        ) from exc

    match = re.search(r"^# File path:\s*(.+)$", content, re.MULTILINE)
    if not match:
        raise RuntimeError(
            f"{connection_file} does not contain an authoritative '# File path: ...' line."
        )

    db_path = match.group(1).strip()

    # Normalize to absolute path so callers behave consistently.
    return os.path.abspath(db_path)


def _connect(db_path: str) -> sqlite3.Connection:
    """Create a SQLite connection with sensible defaults."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # Ensure foreign keys work.
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _create_base_schema(conn: sqlite3.Connection) -> None:
    """Create the base schema tables used by the template container."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Keep a simple users table (may be used by other parts of template / future work).
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.execute(
        "INSERT OR REPLACE INTO app_info (key, value) VALUES (?, ?)",
        ("project_name", "interactive-trivia-challenge"),
    )
    conn.execute(
        "INSERT OR REPLACE INTO app_info (key, value) VALUES (?, ?)",
        ("version", "0.2.0"),
    )
    conn.execute(
        "INSERT OR REPLACE INTO app_info (key, value) VALUES (?, ?)",
        ("description", "SQLite DB for interactive trivia questions and sessions."),
    )


def _create_trivia_schema(conn: sqlite3.Connection) -> None:
    """Create the trivia schema: questions, choices, correct answer, and optional metadata."""
    # Questions are uniquely identified by an explicit stable "code" for idempotent seeding.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trivia_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            question_text TEXT NOT NULL,

            -- Optional metadata
            category TEXT,
            difficulty TEXT,
            explanation TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trivia_choices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL,
            choice_text TEXT NOT NULL,
            choice_order INTEGER NOT NULL,
            is_correct INTEGER NOT NULL DEFAULT 0,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (question_id) REFERENCES trivia_questions(id) ON DELETE CASCADE,
            UNIQUE (question_id, choice_order)
        )
        """
    )

    # Helpful indexes for typical query patterns.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trivia_choices_question_id ON trivia_choices(question_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trivia_questions_category ON trivia_questions(category)"
    )


def _question_exists(conn: sqlite3.Connection, code: str) -> bool:
    cur = conn.execute("SELECT 1 FROM trivia_questions WHERE code = ? LIMIT 1", (code,))
    return cur.fetchone() is not None


def _insert_question_with_choices(
    conn: sqlite3.Connection,
    *,
    code: str,
    question_text: str,
    choices: Sequence[str],
    correct_index: int,
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    explanation: Optional[str] = None,
) -> None:
    """Insert a question and its choices (idempotent based on code)."""
    if _question_exists(conn, code):
        return

    conn.execute(
        """
        INSERT INTO trivia_questions (code, question_text, category, difficulty, explanation)
        VALUES (?, ?, ?, ?, ?)
        """,
        (code, question_text, category, difficulty, explanation),
    )

    qid = conn.execute("SELECT id FROM trivia_questions WHERE code = ?", (code,)).fetchone()["id"]

    for idx, choice_text in enumerate(choices):
        is_correct = 1 if idx == correct_index else 0
        conn.execute(
            """
            INSERT INTO trivia_choices (question_id, choice_text, choice_order, is_correct)
            VALUES (?, ?, ?, ?)
            """,
            (qid, choice_text, idx, is_correct),
        )


def _seed_starter_questions(conn: sqlite3.Connection) -> None:
    """Seed a small starter set of trivia questions.

    Designed to be safe to run multiple times:
    - Uses trivia_questions.code uniqueness to avoid duplicates.
    """
    starter_questions: Sequence[Tuple] = [
        (
            "GEN_001",
            "What is the capital city of France?",
            ["Berlin", "Madrid", "Paris", "Rome"],
            2,
            "Geography",
            "Easy",
            "Paris is the capital and most populous city of France.",
        ),
        (
            "SCI_001",
            "Which planet is known as the Red Planet?",
            ["Venus", "Mars", "Jupiter", "Mercury"],
            1,
            "Science",
            "Easy",
            "Mars appears red due to iron oxide (rust) on its surface.",
        ),
        (
            "CS_001",
            "In programming, what does 'HTML' stand for?",
            [
                "HyperText Markup Language",
                "High Transfer Machine Language",
                "Hyperlink and Text Management Language",
                "Home Tool Markup Language",
            ],
            0,
            "Technology",
            "Easy",
            "HTML stands for HyperText Markup Language.",
        ),
        (
            "HIS_001",
            "Who was the first President of the United States?",
            ["Thomas Jefferson", "John Adams", "George Washington", "James Madison"],
            2,
            "History",
            "Easy",
            "George Washington served as the first U.S. President from 1789 to 1797.",
        ),
        (
            "MATH_001",
            "What is 9 × 7?",
            ["56", "63", "72", "49"],
            1,
            "Math",
            "Easy",
            "9 times 7 equals 63.",
        ),
        (
            "POP_001",
            "Which movie features the quote: 'May the Force be with you'?",
            ["Star Wars", "The Matrix", "Harry Potter", "The Lord of the Rings"],
            0,
            "Pop Culture",
            "Easy",
            "The quote is famously associated with the Star Wars franchise.",
        ),
    ]

    for (
        code,
        question_text,
        choices,
        correct_index,
        category,
        difficulty,
        explanation,
    ) in starter_questions:
        _insert_question_with_choices(
            conn,
            code=code,
            question_text=question_text,
            choices=choices,
            correct_index=correct_index,
            category=category,
            difficulty=difficulty,
            explanation=explanation,
        )


def _write_visualizer_env(db_path: str) -> None:
    """Write db_visualizer/sqlite.env so the included DB viewer points at the correct DB."""
    os.makedirs("db_visualizer", exist_ok=True)
    with open("db_visualizer/sqlite.env", "w", encoding="utf-8") as f:
        f.write(f'export SQLITE_DB="{db_path}"\n')


def main() -> None:
    """Main initialization routine."""
    print("Starting SQLite setup (trivia schema + seed)...")

    # Use authoritative DB path from db_connection.txt if present and valid.
    # If db_connection.txt is missing (fresh clone), fall back to local myapp.db
    # and then (re)write db_connection.txt at the end.
    used_fallback = False
    try:
        db_path = get_db_path_from_connection_file("db_connection.txt")
    except Exception as exc:
        print(f"Warning: {exc}")
        print(f"Falling back to local DB file: {DB_NAME_FALLBACK}")
        db_path = os.path.abspath(DB_NAME_FALLBACK)
        used_fallback = True

    db_exists = os.path.exists(db_path)
    if db_exists:
        print(f"SQLite database already exists at {db_path}")
    else:
        print(f"Creating new SQLite database at {db_path}...")

    # Ensure directory exists for absolute path.
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

    conn = _connect(db_path)
    try:
        # Basic connectivity check.
        conn.execute("SELECT 1;")

        # Schema creation
        _create_base_schema(conn)
        _create_trivia_schema(conn)

        # Seed starter data
        _seed_starter_questions(conn)

        conn.commit()

        # Stats
        table_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()["cnt"]

        q_count = conn.execute("SELECT COUNT(*) AS cnt FROM trivia_questions").fetchone()["cnt"]
        c_count = conn.execute("SELECT COUNT(*) AS cnt FROM trivia_choices").fetchone()["cnt"]

        print("Database is accessible and working.")
        print("Database statistics:")
        print(f"  Tables: {table_count}")
        print(f"  Trivia questions: {q_count}")
        print(f"  Trivia choices: {c_count}")

    finally:
        conn.close()

    # Update db_visualizer env to point to authoritative db file.
    _write_visualizer_env(db_path)

    # Only (re)write db_connection.txt if we had to fall back OR the stored path is stale.
    # This keeps db_connection.txt as the single, authoritative reference.
    connection_string = f"sqlite:///{db_path}"
    try:
        if used_fallback:
            with open("db_connection.txt", "w", encoding="utf-8") as f:
                f.write("# SQLite connection methods:\n")
                f.write(f"# Python: sqlite3.connect('{db_path}')\n")
                f.write(f"# Connection string: {connection_string}\n")
                f.write(f"# File path: {db_path}\n")
            print("Connection information saved to db_connection.txt (authoritative path updated).")
    except Exception as exc:
        print(f"Warning: Could not save connection info: {exc}")

    print("\nSQLite setup complete!")
    print(f"Database file: {db_path}")
    print("To use the Node.js DB viewer, run: source db_visualizer/sqlite.env")
    print("\nScript completed successfully.")


if __name__ == "__main__":
    main()
