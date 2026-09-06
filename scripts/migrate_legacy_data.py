"""
One-time migration: old public.Admins / Users / Inventory (from a pg_dump
.backup file) -> the new inventory_* tables + shadow `profiles` rows in the
new Supabase project.

Usage:
    python scripts/migrate_legacy_data.py --backup /path/to/db_cluster.backup
    python scripts/migrate_legacy_data.py --backup /path/to/db_cluster.backup --apply

Without --apply this only parses the backup and prints a summary (dry run).
Pass --apply to actually create auth users / profiles / rows in Supabase.

Requires SUPABASE_URL and SUPABASE_KEY (service_role) in .env, same as the
main app -- creating auth users needs the admin API, which the anon key
cannot do.

Safe to re-run: profiles, card links, and inventory items are upserted on
their primary key. Checkouts and strikes are append-only inserts, so re-running
after a partial --apply will duplicate any checkout/strike rows that already
made it in -- check the printed summary before re-applying.
"""

import argparse
import os
import re
import sys
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from supabase import create_client


# --- Postgres COPY (text format) parsing ---

def unescape_copy_field(field: str):
    if field == "\\N":
        return None
    out = []
    i, n = 0, len(field)
    mapping = {"\\": "\\", "t": "\t", "n": "\n", "r": "\r"}
    while i < n:
        c = field[i]
        if c == "\\" and i + 1 < n:
            out.append(mapping.get(field[i + 1], field[i + 1]))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def parse_pg_array(s):
    if s is None:
        return None
    s = s.strip()
    if s == "{}":
        return []
    if not (s.startswith("{") and s.endswith("}")):
        return [s]
    body = s[1:-1]
    elements = []
    i, n = 0, len(body)
    while i < n:
        if body[i] == ",":
            i += 1
            continue
        if body[i] == '"':
            i += 1
            buf = []
            while i < n:
                c = body[i]
                if c == "\\" and i + 1 < n:
                    buf.append(body[i + 1])
                    i += 2
                    continue
                if c == '"':
                    i += 1
                    break
                buf.append(c)
                i += 1
            elements.append("".join(buf))
            while i < n and body[i] != ",":
                i += 1
        else:
            j = i
            while j < n and body[j] != ",":
                j += 1
            elements.append(body[i:j].strip())
            i = j
    return elements


def extract_copy_block(lines, table_name):
    header_prefix = f'COPY public."{table_name}"'
    start = None
    for idx, line in enumerate(lines):
        if line.startswith(header_prefix):
            start = idx + 1
            break
    if start is None:
        raise ValueError(f"COPY block for {table_name} not found in backup")
    rows = []
    for line in lines[start:]:
        if line.rstrip("\n") == "\\.":
            break
        rows.append(line.rstrip("\n"))
    return rows


def parse_table(lines, table_name, columns):
    rows = extract_copy_block(lines, table_name)
    parsed = []
    for row in rows:
        fields = [unescape_copy_field(f) for f in row.split("\t")]
        parsed.append(dict(zip(columns, fields)))
    return parsed


# --- Domain parsing helpers ---

STRIKE_RE = re.compile(r"^\[(?P<ts>[^\]]+)\]\s*(?P<reason>.*)$")
ASSET_SUFFIX_RE = re.compile(r"\(Asset:\s*(?P<asset>.+)\)\s*$")


def parse_strike_entry(entry: str):
    m = STRIKE_RE.match(entry)
    if not m:
        return {"issued_at": None, "reason": entry, "asset_name": None}
    ts_raw, reason = m.group("ts"), m.group("reason")
    issued_at = None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            issued_at = datetime.strptime(ts_raw, fmt).replace(tzinfo=timezone.utc).isoformat()
            break
        except ValueError:
            continue
    asset_match = ASSET_SUFFIX_RE.search(reason)
    asset_name = asset_match.group("asset").strip() if asset_match else None
    return {"issued_at": issued_at, "reason": reason, "asset_name": asset_name}


def parse_rental_entry(entry: str):
    parts = [p.strip() for p in entry.split("/")]
    name = parts[0] if parts else None
    checked_out_at = parts[1] if len(parts) > 1 else None
    third = parts[2] if len(parts) > 2 else None
    is_open = third == "PENDING"
    checked_in_at = None if is_open else third
    checked_out_by_name = None
    checked_in_by_name = None
    for p in parts[3:]:
        if p.startswith("In:"):
            checked_in_by_name = p[3:].strip()
        elif p.startswith("Out:"):
            checked_out_by_name = p[4:].strip()
    return {
        "renter_name": name,
        "checked_out_at": checked_out_at,
        "checked_in_at": checked_in_at,
        "is_open": is_open,
        "checked_out_by_name": checked_out_by_name,
        "checked_in_by_name": checked_in_by_name,
    }


def parse_pg_timestamp(ts: str):
    if not ts:
        return None
    try:
        return datetime.strptime(ts, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return ts  # already ISO-ish (e.g. first_logged with tz offset)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backup", required=True, help="Path to the pg_dump .backup file")
    ap.add_argument("--apply", action="store_true", help="Actually write to Supabase (default: dry run)")
    args = ap.parse_args()

    with open(args.backup, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    admins = parse_table(lines, "Admins", ["id", "name"])
    users = parse_table(lines, "Users", ["id", "name", "currently_renting", "strike_history"])
    inventory = parse_table(lines, "Inventory", [
        "id", "name", "first_logged", "last_rented_person", "is_rented", "condition", "rental_history",
    ])

    for u in users:
        u["strike_history"] = parse_pg_array(u["strike_history"]) or []
    for i in inventory:
        i["rental_history"] = parse_pg_array(i["rental_history"]) or []
        i["is_rented"] = i["is_rented"] == "t"

    print(f"Parsed: {len(admins)} admins, {len(users)} users, {len(inventory)} items")

    if not args.apply:
        print("\nDry run only -- pass --apply to write to Supabase.")
        return

    load_dotenv()
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        sys.exit("SUPABASE_URL / SUPABASE_KEY (service_role) must be set in .env")

    supabase = create_client(supabase_url, supabase_key)

    name_to_profile_id = {}
    cardid_to_profile_id = {}
    warnings = []

    def find_existing_profile_by_name(name: str):
        res = supabase.table("profiles").select("id, full_name, is_admin").ilike("full_name", name).execute()
        return res.data[0] if res.data else None

    def provision(card_id: str, name: str, is_admin: bool):
        existing = find_existing_profile_by_name(name)
        if existing:
            profile_id = existing["id"]
            if bool(existing.get("is_admin")) != is_admin:
                warnings.append(
                    f"{name}: existing profile has is_admin={existing.get('is_admin')}, "
                    f"legacy data implies {is_admin} -- left unchanged, review manually"
                )
            supabase.table("inventory_card_links").upsert(
                {"card_id": card_id, "profile_id": profile_id}, on_conflict="card_id"
            ).execute()
            name_to_profile_id[name] = profile_id
            cardid_to_profile_id[card_id] = profile_id
            print(f"  linked EXISTING profile for {name} -> {profile_id}")
            return profile_id

        email = f"kiosk-migrated-{uuid.uuid4().hex}@inventory.local"
        auth_res = supabase.auth.admin.create_user({
            "email": email,
            "password": uuid.uuid4().hex,
            "email_confirm": True,
            "user_metadata": {"full_name": name, "provisioned_via": "legacy_migration"},
        })
        profile_id = auth_res.user.id
        supabase.table("profiles").upsert(
            {"id": profile_id, "full_name": name, "is_admin": is_admin}, on_conflict="id"
        ).execute()
        supabase.table("inventory_card_links").upsert(
            {"card_id": card_id, "profile_id": profile_id}, on_conflict="card_id"
        ).execute()
        name_to_profile_id[name] = profile_id
        cardid_to_profile_id[card_id] = profile_id
        return profile_id

    print("\n-- Provisioning admins --")
    for a in admins:
        pid = provision(a["id"], a["name"], is_admin=True)
        print(f"  [admin] {a['name']} (card {a['id']}) -> {pid}")

    print("\n-- Provisioning users --")
    for u in users:
        pid = provision(u["id"], u["name"], is_admin=False)
        print(f"  [user]  {u['name']} (card {u['id']}) -> {pid}")

    print("\n-- Migrating strikes --")
    strike_rows = []
    for u in users:
        profile_id = name_to_profile_id[u["name"]]
        for entry in u["strike_history"]:
            parsed = parse_strike_entry(entry)
            strike_rows.append({
                "user_id": profile_id,
                "reason": parsed["reason"],
                "issued_at": parsed["issued_at"] or datetime.now(timezone.utc).isoformat(),
                "_asset_name": parsed["asset_name"],  # resolved to item_id after items are inserted
            })
    print(f"  Parsed {len(strike_rows)} strike entries")

    print("\n-- Migrating inventory items --")
    item_name_counts = {}
    for i in inventory:
        item_name_counts[i["name"]] = item_name_counts.get(i["name"], 0) + 1
        supabase.table("inventory_items").upsert({
            "id": i["id"],
            "name": i["name"],
            "condition": i["condition"],
            "is_rented": i["is_rented"],
            "first_logged": i["first_logged"],
            "last_rented_person": name_to_profile_id.get(i["last_rented_person"]) if i["last_rented_person"] else None,
        }, on_conflict="id").execute()
    print(f"  Upserted {len(inventory)} items")

    # Resolve strike asset names to item_id only when the name is unambiguous
    for row in strike_rows:
        asset_name = row.pop("_asset_name")
        row["item_id"] = None
        if asset_name and item_name_counts.get(asset_name) == 1:
            match = next((i for i in inventory if i["name"] == asset_name), None)
            if match:
                row["item_id"] = match["id"]

    if strike_rows:
        supabase.table("inventory_strikes").insert(strike_rows).execute()
        print(f"  Inserted {len(strike_rows)} strike rows")

    print("\n-- Migrating rental history / open checkouts --")
    checkout_rows = []
    for i in inventory:
        for entry in i["rental_history"]:
            parsed = parse_rental_entry(entry)
            renter_id = name_to_profile_id.get(parsed["renter_name"])
            if not renter_id:
                warnings.append(f"Item '{i['name']}': unknown renter '{parsed['renter_name']}' in history entry, skipped: {entry}")
                continue
            checkout_rows.append({
                "item_id": i["id"],
                "user_id": renter_id,
                "checked_out_at": parse_pg_timestamp(parsed["checked_out_at"]) or i["first_logged"],
                "checked_out_by": name_to_profile_id.get(parsed["checked_out_by_name"]),
                "checked_in_at": None if parsed["is_open"] else parse_pg_timestamp(parsed["checked_in_at"]),
                "checked_in_by": name_to_profile_id.get(parsed["checked_in_by_name"]),
                "condition_at_return": None if parsed["is_open"] else i["condition"],
            })

        # Item is currently rented but its history didn't end in an open entry
        # (e.g. no history at all, or history/DB state drifted) -- synthesize
        # an open checkout from last_rented_person so "is_rented" stays truthful.
        has_open_in_history = any(
            parse_rental_entry(e)["is_open"] and parse_rental_entry(e)["renter_name"] == i["last_rented_person"]
            for e in i["rental_history"]
        )
        if i["is_rented"] and i["last_rented_person"] and not has_open_in_history:
            renter_id = name_to_profile_id.get(i["last_rented_person"])
            if renter_id:
                checkout_rows.append({
                    "item_id": i["id"],
                    "user_id": renter_id,
                    "checked_out_at": i["first_logged"],
                    "checked_out_by": None,
                    "checked_in_at": None,
                    "checked_in_by": None,
                    "condition_at_return": None,
                })
            else:
                warnings.append(f"Item '{i['name']}': is_rented=true to unknown user '{i['last_rented_person']}', no checkout row created")

    if checkout_rows:
        supabase.table("inventory_checkouts").insert(checkout_rows).execute()
        print(f"  Inserted {len(checkout_rows)} checkout rows")

    print(f"\nDone. {len(warnings)} warning(s):")
    for w in warnings:
        print(f"  - {w}")


if __name__ == "__main__":
    main()
