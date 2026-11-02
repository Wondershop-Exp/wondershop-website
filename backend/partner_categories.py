"""
"What do you deal in?" categories for partners (2026-11-02, per Shruti).

BASE is the built-in list, in the order the partner form shows it. Categories
added later from Slack #vendor-contacts (after Shruti confirms with "yes" in
the thread, see routers/slack_vendors.py) are stored in partner_categories
(migrations/082) and shown just before "Others" on the partner form
(vendor-onboarding.html) and in the admin Partners tab.
"""
import re
from typing import List, Optional

from database import database

BASE = ['Event Volunteer', 'Wondershop Team Member', 'Live Stations & Mascots', 'Photographer', 'Decorator',
        'Baker', 'Stationery Store', 'Personalization Store', 'Gift Shop', 'Packaging Store', 'Art & Craft Store',
        'Hardware Store', 'Decoration Store',
        'Host', 'DJ', 'Magician', 'Bubble Show Artist', 'Science Show Artist', 'Puppet Show Artist',
        'Other Entertainer', 'Transport Services', 'Others']


async def extra_categories() -> List[str]:
    try:
        rows = await database.fetch_all("SELECT name FROM partner_categories ORDER BY name")
    except Exception:   # table not created yet
        return []
    base = {b.lower() for b in BASE}
    return [r["name"] for r in rows if r["name"].lower() not in base]


async def all_categories() -> List[str]:
    """Built-in + added ones, "Others" last."""
    return BASE[:-1] + await extra_categories() + ["Others"]


def tidy_name(name: str) -> str:
    n = re.sub(r"\s+", " ", str(name or "")).strip(" .,-:;\"'*_")
    return n[:60]


async def find_category(name: str) -> Optional[str]:
    n = tidy_name(name).lower()
    return next((c for c in await all_categories() if c.lower() == n), None)


async def add_category(name: str, by: str = "") -> str:
    name = tidy_name(name)
    existing = await find_category(name)
    if existing:
        return existing
    await database.execute(
        "INSERT INTO partner_categories (name, added_by) VALUES (:n, :b) ON CONFLICT DO NOTHING",
        {"n": name, "b": (by or "")[:100]})
    return name
