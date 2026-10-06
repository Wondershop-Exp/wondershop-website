"""
Small, idempotent schema top-ups applied on every startup (2026-10-06).

Production missed migration 024 (packing-list event date/time/venue), which
made "Save & get staff link" fail with a 500. The migrations listed here only
ADD missing columns / tables (IF NOT EXISTS), so running them again is
harmless; anything that fails is logged and skipped - startup never stops.
"""
import logging
import os
import re

from database import database

logger = logging.getLogger(__name__)

SAFE_MIGRATIONS = [
    "023_packaging_submit.sql",
    "024_packaging_event_details.sql",
    "040_to_be_confirmed.sql",
    "041_decor_reference_images.sql",
]


def _statements(sql: str):
    sql = re.sub(r"--[^\n]*", "", sql)
    return [s.strip() for s in sql.split(";") if s.strip()]


async def ensure_schema() -> None:
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")
    for name in SAFE_MIGRATIONS:
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as fh:
                stmts = _statements(fh.read())
        except OSError:
            logger.warning(f"ensure_schema: {name} not found - skipped")
            continue
        for st in stmts:
            try:
                await database.execute(st)
            except Exception as exc:
                logger.warning(f"ensure_schema: {name}: {exc}")
    logger.info("ensure_schema: done")
