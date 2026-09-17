#!/usr/bin/env python3
"""
Catalogue drift checker.

builder.html (the live Build-a-Birthday site) is the source of truth for
theme/activity/gift/pricing options. The sales module (backend/catalogue_data.py
and backend/routers/sales_leads.py) keeps hand-maintained *copies* of a lot of
that same data, because builder.html is a static page with no API the sales
backend can read from at runtime. Nothing keeps those copies in sync
automatically today — if someone adds/changes an option in builder.html and
forgets to mirror it, the sales dropdown just quietly falls behind.

This script catches that: it extracts the live catalogue straight out of
builder.html (parsing the actual JS, not a re-typed guess at it) and diffs it
against catalogue_data.py and sales_leads.py, field by field. Run it any time
builder.html changes, or periodically, to see exactly what's drifted.

Usage:
    python3 check_catalogue_drift.py [--repo-root PATH]

Exit code 0 = no drift found. Exit code 1 = drift found (or the check
couldn't run) — handy if this ever gets wired into a pre-deploy step.

Requires: python3 (stdlib only) and node (to safely evaluate builder.html's
JS array/object literals — they use unquoted keys, so they aren't valid
JSON and can't be parsed with Python's json/ast modules directly).
"""
import argparse
import ast
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


# ─── generic extractors ─────────────────────────────────────────────────

def extract_js_literal_source(text: str, const_name: str) -> str:
    """Returns the exact RHS source text of `const <const_name> = ...;` in a
    JS file, by scanning character-by-character (tracking string/comment
    state and bracket depth) rather than a regex — these literals span
    hundreds of lines and contain nested brackets, quotes, and comments, so
    a regex can't reliably find the right closing point."""
    marker_re = re.compile(r"const\s+" + re.escape(const_name) + r"\s*=")
    m = marker_re.search(text)
    if not m:
        raise ValueError(f"couldn't find `const {const_name} =` in builder.html")
    i = m.end()
    n = len(text)
    depth = 0
    in_str = None
    in_line_comment = False
    in_block_comment = False
    start = i
    j = i
    while j < n:
        c = text[j]
        if in_line_comment:
            if c == "\n":
                in_line_comment = False
        elif in_block_comment:
            if c == "*" and j + 1 < n and text[j + 1] == "/":
                in_block_comment = False
                j += 1
        elif in_str:
            if c == "\\":
                j += 1
            elif c == in_str:
                in_str = None
        else:
            if c == "/" and j + 1 < n and text[j + 1] == "/":
                in_line_comment = True
                j += 1
            elif c == "/" and j + 1 < n and text[j + 1] == "*":
                in_block_comment = True
                j += 1
            elif c in ("'", '"', "`"):
                in_str = c
            elif c in "[{(":
                depth += 1
            elif c in "]})":
                depth -= 1
            elif c == ";" and depth <= 0:
                return text[start:j].strip()
        j += 1
    raise ValueError(f"never found a terminating `;` for `const {const_name}` in builder.html")


def extract_js_consts(builder_html: str, names: list) -> dict:
    """Pulls several `const NAME = ...;` literals out of builder.html and
    evaluates them with a real JS engine (node), since they're JS object/
    array literals with unquoted keys — not valid JSON or Python."""
    if not shutil_which("node"):
        raise RuntimeError(
            "node is not installed (or not on PATH) — required to safely "
            "evaluate builder.html's JS catalogue literals. Install Node.js "
            "and re-run."
        )
    pieces = []
    for name in names:
        src = extract_js_literal_source(builder_html, name)
        pieces.append(f"{json.dumps(name)}: ({src})")
    js_module = "module.exports = {\n" + ",\n".join(pieces) + "\n};\n"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(js_module)
        tmp_path = f.name
    try:
        out = subprocess.run(
            ["node", "-e", f"console.log(JSON.stringify(require({json.dumps(tmp_path)})))"],
            capture_output=True, text=True, timeout=30,
        )
        if out.returncode != 0:
            raise RuntimeError(f"node failed evaluating builder.html literals:\n{out.stderr}")
        return json.loads(out.stdout)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def shutil_which(cmd):
    import shutil
    return shutil.which(cmd)


def extract_py_const(source: str, name: str):
    """Pulls a top-level `NAME = <literal>` assignment out of a Python file
    via the ast module and literal_eval's just that node — never executes
    the file, so this works even without FastAPI/pydantic/databases etc.
    installed (sales_leads.py imports those, but we don't need to run it)."""
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise ValueError(f"couldn't find top-level `{name} = ...` assignment")


# ─── regex extractors for things that live as HTML markup, not JS consts ──

def extract_tier_card_prices(builder_html: str) -> dict:
    """{(category, tier): price} from onclick="selTier(this,'host','Premium',10000)" """
    out = {}
    for cat, tier, price in re.findall(
        r"selTier\(this,'(\w+)','(\w+)',(\d+)\)", builder_html
    ):
        out[(cat, tier)] = int(price)
    return out


def extract_venue_types(builder_html: str) -> list:
    """[(value, label), ...] from the Venue Type button grid."""
    pattern = re.compile(
        r"selV\(this,'([^']+)'\)\"><span class=\"v-ic\">[^<]*</span>([^<]+)</button>"
    )
    return [(value, label.strip()) for value, label in pattern.findall(builder_html)]


def extract_return_gift_type_chips(builder_html: str) -> list:
    """Filter-by-type chip labels, excluding the 'All' chip."""
    pattern = re.compile(r"fGifts\('type','(\w+)',this\)\">([^<]+)</button>")
    return [label.strip() for slug, label in pattern.findall(builder_html) if slug != "all"]


def extract_music_addon_prices(builder_html: str) -> dict:
    out = {}
    for name, price in re.findall(r"n:'(Music Lights|Smoke Machine)',p:(\d+)", builder_html):
        out[name] = int(price)
    return out


# ─── comparison helpers ─────────────────────────────────────────────────

class Report:
    def __init__(self):
        self.sections = []  # (title, [issue, ...] or None-if-skipped)

    def add(self, title, issues, skipped_reason=None):
        self.sections.append((title, issues, skipped_reason))

    def has_drift(self):
        return any(issues for _, issues, skipped in self.sections if issues)

    def print(self):
        W = 78
        print("=" * W)
        print("CATALOGUE DRIFT CHECK — builder.html vs sales module")
        print("=" * W)
        clean, drifted, skipped = 0, 0, 0
        for title, issues, skipped_reason in self.sections:
            if skipped_reason:
                skipped += 1
                print(f"\n⏭  {title} — SKIPPED ({skipped_reason})")
                continue
            if not issues:
                clean += 1
                print(f"\n✅ {title} — in sync")
                continue
            drifted += 1
            print(f"\n⚠️  {title} — {len(issues)} issue(s)")
            for issue in issues:
                print(f"    - {issue}")
        print("\n" + "=" * W)
        print(f"{clean} clean, {drifted} drifted, {skipped} skipped")
        print("=" * W)
        return drifted


def diff_sets(builder_items: set, sales_items: set, label_builder="builder.html", label_sales="sales module"):
    issues = []
    only_builder = builder_items - sales_items
    only_sales = sales_items - builder_items
    for item in sorted(only_builder, key=str):
        issues.append(f"in {label_builder} but not {label_sales}: {item!r}")
    for item in sorted(only_sales, key=str):
        issues.append(f"in {label_sales} but not {label_builder}: {item!r}")
    return issues


def diff_price_maps(builder_map: dict, sales_map: dict, label_builder="builder.html", label_sales="sales module"):
    issues = []
    all_keys = set(builder_map) | set(sales_map)
    for key in sorted(all_keys, key=str):
        bv, sv = builder_map.get(key), sales_map.get(key)
        if key not in builder_map:
            issues.append(f"{key!r}: in {label_sales} (₹{sv}) but not {label_builder}")
        elif key not in sales_map:
            issues.append(f"{key!r}: in {label_builder} (₹{bv}) but not {label_sales}")
        elif bv != sv:
            issues.append(f"{key!r}: {label_builder}=₹{bv} vs {label_sales}=₹{sv}")
    return issues


# ─── main ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo-root", default=None, help="repo root (default: inferred from this script's location)")
    parser.add_argument("--builder-html", default=None, help="path to builder.html (default: <repo-root>/builder.html)")
    parser.add_argument("--catalogue-data", default=None, help="path to backend/catalogue_data.py")
    parser.add_argument("--sales-leads", default=None, help="path to backend/routers/sales_leads.py")
    args = parser.parse_args()

    if args.repo_root:
        repo_root = Path(args.repo_root)
    else:
        # <repo-root>/backend/scripts/check_catalogue_drift.py -> repo root
        repo_root = Path(__file__).resolve().parents[2]

    builder_path = Path(args.builder_html) if args.builder_html else repo_root / "builder.html"
    catdata_path = Path(args.catalogue_data) if args.catalogue_data else repo_root / "backend" / "catalogue_data.py"
    salesleads_path = Path(args.sales_leads) if args.sales_leads else repo_root / "backend" / "routers" / "sales_leads.py"

    for p in (builder_path, catdata_path, salesleads_path):
        if not p.exists():
            print(f"ERROR: {p} not found. Pass --repo-root, or --builder-html/--catalogue-data/--sales-leads directly.", file=sys.stderr)
            sys.exit(1)

    builder_html = builder_path.read_text(encoding="utf-8")
    catdata_src = catdata_path.read_text(encoding="utf-8")
    salesleads_src = salesleads_path.read_text(encoding="utf-8")

    report = Report()

    # ── JS-literal-derived checks (need node) ──
    js_names = ["THEMES", "DECOR_TIER_META", "ACTS", "GIFTS", "PINATAS",
                "PACKAGING_UNIT_PRICE", "PACKAGING_LABELS", "TAG_NOTE_UNIT_PRICE", "TAG_NOTE_MIN_QTY"]
    js_err = None
    js = {}
    try:
        js = extract_js_consts(builder_html, js_names)
    except Exception as e:
        js_err = str(e)

    if js_err:
        for title in ["Decor tiers (price)", "Decor themes", "Activities", "Return gifts",
                       "Pinata tier pricing", "Packaging pricing/labels", "Return-gift-tag pricing"]:
            report.add(title, None, skipped_reason=js_err)
    else:
        # Decor tier prices
        b_decor = {t["tier"]: t["price"] for t in js["DECOR_TIER_META"]}
        s_decor_meta = extract_py_const(catdata_src, "DECOR_TIER_META")
        s_decor = {tier: meta["price"] for tier, meta in s_decor_meta.items()}
        report.add("Decor tiers (price)", diff_price_maps(b_decor, s_decor, "builder.html", "catalogue_data.py"))

        # Themes (id -> name)
        b_themes = {(t["id"], t["n"]) for t in js["THEMES"]}
        s_themes_list = extract_py_const(catdata_src, "THEMES")
        s_themes = {(t["id"], t["n"]) for t in s_themes_list}
        report.add("Decor themes", diff_sets(b_themes, s_themes, "builder.html", "catalogue_data.py"))

        # Activities: (id, name, price, flat)
        b_acts = {(a["id"], a["n"], a["r1"], a["flat"]) for a in js["ACTS"]}
        s_acts_list = extract_py_const(catdata_src, "ACTIVITIES")
        s_acts = {(aid, name, price, flat) for aid, name, price, flat in s_acts_list}
        report.add("Activities", diff_sets(b_acts, s_acts, "builder.html", "catalogue_data.py"))

        # Return gifts: (id, name, price)
        b_gifts = {(g["id"], g["n"], g["unit"]) for g in js["GIFTS"]}
        s_gifts_list = extract_py_const(catdata_src, "GIFTS")
        s_gifts = {(gid, name, price) for gid, name, _img, price in s_gifts_list}
        report.add("Return gifts", diff_sets(b_gifts, s_gifts, "builder.html", "catalogue_data.py"))

        # Pinata pricing: keyed by display name (catalogue_data.py has no per-id pinata pricing)
        b_pinata_price = {p["n"]: p["p"] for p in js["PINATAS"]}
        s_pinata_price = extract_py_const(catdata_src, "PINATA_TIER_PRICES")
        s_pinata_price = {k: v for k, v in s_pinata_price.items() if k != "Custom"}
        report.add("Pinata tier pricing", diff_price_maps(b_pinata_price, s_pinata_price, "builder.html", "catalogue_data.py"))

        # Packaging: unit prices + labels — these live directly in sales_leads.py, not catalogue_data.py
        s_pkg_price = extract_py_const(salesleads_src, "PACKAGING_UNIT_PRICE")
        report.add("Packaging pricing", diff_price_maps(js["PACKAGING_UNIT_PRICE"], s_pkg_price, "builder.html", "sales_leads.py"))
        s_pkg_labels = extract_py_const(catdata_src, "PACKAGING_LABELS")
        pkg_label_issues = []
        for k in set(js["PACKAGING_LABELS"]) | set(s_pkg_labels):
            bl, sl = js["PACKAGING_LABELS"].get(k), s_pkg_labels.get(k)
            if bl != sl:
                pkg_label_issues.append(f"{k!r}: builder.html={bl!r} vs catalogue_data.py={sl!r}")
        report.add("Packaging labels", pkg_label_issues)

        # Return-gift-tag pricing (builder.html TAG_NOTE_UNIT_PRICE/MIN_QTY vs sales_leads.py)
        s_tag_price = extract_py_const(salesleads_src, "TAG_NOTE_UNIT_PRICE")
        s_tag_minqty = extract_py_const(salesleads_src, "TAG_NOTE_MIN_QTY")
        tag_issues = []
        if js["TAG_NOTE_UNIT_PRICE"] != s_tag_price:
            tag_issues.append(f"unit price: builder.html=₹{js['TAG_NOTE_UNIT_PRICE']} vs sales_leads.py=₹{s_tag_price}")
        if js["TAG_NOTE_MIN_QTY"] != s_tag_minqty:
            tag_issues.append(f"min qty: builder.html={js['TAG_NOTE_MIN_QTY']} vs sales_leads.py={s_tag_minqty}")
        report.add("Return-gift-tag pricing", tag_issues)

    # ── regex-derived checks (no node needed) ──
    b_tier_prices = extract_tier_card_prices(builder_html)

    s_host = extract_py_const(catdata_src, "HOST_TIER_PRICES")
    b_host = {tier: price for (cat, tier), price in b_tier_prices.items() if cat == "host"}
    report.add("Host tier pricing", diff_price_maps(b_host, s_host, "builder.html", "catalogue_data.py"))

    s_dj = extract_py_const(catdata_src, "DJ_TIER_PRICES")
    b_dj = {tier: price for (cat, tier), price in b_tier_prices.items() if cat == "dj"}
    report.add("Music (DJ) tier pricing", diff_price_maps(b_dj, s_dj, "builder.html", "catalogue_data.py"))

    s_photo = extract_py_const(catdata_src, "PHOTO_TIER_PRICES")
    b_photo = {tier: price for (cat, tier), price in b_tier_prices.items() if cat == "photo"}
    report.add("Photographer tier pricing", diff_price_maps(b_photo, s_photo, "builder.html", "catalogue_data.py"))

    b_venues = set(extract_venue_types(builder_html))
    s_venues_list = extract_py_const(salesleads_src, "VENUE_TYPES")
    s_venues = {(v["value"], v["label"]) for v in s_venues_list}
    report.add("Venue types", diff_sets(b_venues, s_venues, "builder.html", "sales_leads.py"))

    b_gift_types = set(extract_return_gift_type_chips(builder_html))
    s_gift_types = set(extract_py_const(salesleads_src, "RETURN_GIFT_TYPES"))
    report.add("Return-gift filter types", diff_sets(b_gift_types, s_gift_types, "builder.html", "sales_leads.py"))

    b_addons = extract_music_addon_prices(builder_html)
    s_addons_list = extract_py_const(salesleads_src, "MUSIC_ADDONS")
    s_addons = {a["name"]: a["price"] for a in s_addons_list}
    report.add("Music add-on pricing", diff_price_maps(b_addons, s_addons, "builder.html", "sales_leads.py"))

    # ── internal self-consistency checks (sales_leads.py's own display-label
    # maps vs the tier sets they're supposed to label — these aren't checked
    # against builder.html directly since the labels are sales-UI-only
    # renames, but they should never reference a tier that doesn't exist) ──
    s_music_labels = extract_py_const(salesleads_src, "MUSIC_LABELS")
    label_issues = [f"MUSIC_LABELS has a tier {k!r} not in DJ_TIER_PRICES {sorted(s_dj)}"
                     for k in s_music_labels if k not in s_dj]
    s_photo_labels = extract_py_const(salesleads_src, "PHOTO_LABELS")
    label_issues += [f"PHOTO_LABELS has a tier {k!r} not in PHOTO_TIER_PRICES {sorted(s_photo)}"
                      for k in s_photo_labels if k not in s_photo]
    label_issues += [f"PHOTO_TIER_PRICES has a tier {k!r} with no PHOTO_LABELS entry"
                      for k in s_photo if k not in s_photo_labels]
    report.add("Sales-UI label maps (internal consistency)", label_issues)

    # ── informational: sales-only pricing with no live-site equivalent ──
    report.add(
        "Pinata bags (₹/bag) — sales-only add-on",
        [], skipped_reason="no equivalent option on the live site; nothing to diff against"
    )

    drifted = report.print()
    sys.exit(1 if (drifted or js_err) else 0)


if __name__ == "__main__":
    main()
