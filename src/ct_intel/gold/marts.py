"""Apply Gold analytical views."""

from __future__ import annotations

from ct_intel.config import Settings
from ct_intel.sql_util import execute_script


def apply_gold(connection, settings: Settings) -> None:
    script = (settings.sql_dir / "gold.sql").read_text(encoding="utf-8")
    execute_script(connection, script)
