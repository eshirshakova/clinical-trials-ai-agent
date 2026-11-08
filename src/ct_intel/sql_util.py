"""Load and run SQL files one statement at a time."""

from __future__ import annotations

from pathlib import Path


def read_sql(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def split_sql(script: str) -> list[str]:
    statements: list[str] = []
    for chunk in script.split(";"):
        statement = chunk.strip()
        if statement:
            statements.append(statement)
    return statements


def execute_script(connection, script: str) -> None:
    for statement in split_sql(script):
        connection.execute(statement)
