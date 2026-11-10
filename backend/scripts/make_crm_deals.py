"""Generate a realistic, messy CRM deals export for the Dataful demo.

Seeded, so the output is reproducible:
    uv run python scripts/make_crm_deals.py  ->  ../dataset/extensions/crm_deals.csv

Planted problems (what Dataful should find):
- account name variants (Acme Inc / ACME Corp. / Acme)
- stage variants (Closed Won / closed-won / Won)
- placeholder junk (asdf, test, 000-000-0000, $1)
- "Other" dominating Lead Source
- Jan-1 default Created Dates
- open deals with close dates in the past; won deals with $0
- mixed USD / EUR; amounts stored as text like "$12,500"
- a deal repeated once per contact (double counting)
- a few exact duplicate rows
- internal test accounts (@dataful-internal.com)
- stale Last Activity dates
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 42
N_DEALS = 2200
OUT = Path(__file__).resolve().parents[2] / "dataset" / "extensions" / "crm_deals.csv"

ACCOUNTS = {
    "Acme": ["Acme Inc", "ACME Corp.", "Acme", "acme inc"],
    "Globex": ["Globex Corporation", "Globex Corp", "GLOBEX"],
    "Initech": ["Initech", "Initech LLC"],
    "Umbrella": ["Umbrella Group", "Umbrella Group Ltd"],
    "Stark": ["Stark Industries"],
    "Wayne": ["Wayne Enterprises", "Wayne Enterprises, Inc."],
    "Hooli": ["Hooli"],
    "Soylent": ["Soylent Co", "Soylent Company"],
    "Vandelay": ["Vandelay Industries"],
    "Wonka": ["Wonka Industries"],
    "Tyrell": ["Tyrell Corp"],
    "Cyberdyne": ["Cyberdyne Systems"],
    "Pied Piper": ["Pied Piper", "PiedPiper"],
    "Massive Dynamic": ["Massive Dynamic"],
    "Oscorp": ["Oscorp"],
    "Nakatomi": ["Nakatomi Trading"],
    "Gringotts": ["Gringotts Bank"],
    "Dunder Mifflin": ["Dunder Mifflin", "Dunder-Mifflin"],
    "Monarch": ["Monarch Solutions"],
    "Blue Sun": ["Blue Sun Corp"],
}
DOMAINS = {k: k.lower().replace(" ", "") + ".com" for k in ACCOUNTS}
OWNERS = ["Priya Shah", "Marcus Lee", "Elena Rossi", "Tom Becker", "Aisha Khan", "Diego Alvarez"]
STAGES_OPEN = ["Prospecting", "Qualification", "Proposal", "Negotiation"]
STAGE_WON = ["Closed Won", "Closed Won", "Closed Won", "closed-won", "Won"]
STAGE_LOST = ["Closed Lost", "Closed Lost", "closed lost", "Lost"]
LEAD_SOURCES = ["Other"] * 11 + ["Web", "Referral", "Event", "Partner", "Outbound", "Webinar"]
REGIONS = ["North America", "EMEA", "APAC", "LATAM"]
FIRST = ["Ana", "Ben", "Chloe", "Dev", "Eli", "Fay", "Gus", "Hana", "Ivan", "Jade", "Kai", "Lena"]
LAST = ["Ng", "Okafor", "Park", "Quinn", "Reyes", "Silva", "Tan", "Ueda", "Vance", "Wolfe"]
TODAY = date(2026, 11, 1)


def money_text(rng: random.Random, amount: int, currency: str) -> str:
    """Render an amount the way messy exports do: sometimes plain, sometimes '$12,500'."""
    roll = rng.random()
    if roll < 0.25:
        symbol = "$" if currency == "USD" else "€"
        return f"{symbol}{amount:,}"
    if roll < 0.32:
        return f"{amount:,}"
    return str(amount)


def created_date(rng: random.Random) -> date:
    if rng.random() < 0.09:  # system default posing as data
        return date(rng.choice([2023, 2024, 2025]), 1, 1)
    return date(2023, 1, 1) + timedelta(days=rng.randint(0, 1000))


def make_deal(rng: random.Random, i: int) -> dict:
    account_key = rng.choice(list(ACCOUNTS))
    account = rng.choice(ACCOUNTS[account_key])
    region = rng.choice(REGIONS)
    currency = "EUR" if region == "EMEA" and rng.random() < 0.6 else "USD"
    created = created_date(rng)
    roll = rng.random()
    if roll < 0.35:
        stage = rng.choice(STAGE_WON)
    elif roll < 0.6:
        stage = rng.choice(STAGE_LOST)
    else:
        stage = rng.choice(STAGES_OPEN)
    close = created + timedelta(days=rng.randint(14, 240))
    amount = rng.choice([5, 8, 12, 15, 20, 25, 40, 60, 90]) * 500 + rng.randint(0, 40) * 50
    if stage in STAGE_WON and rng.random() < 0.03:
        amount = 0  # won deal at $0
    last_activity = min(TODAY, close + timedelta(days=rng.randint(-30, 30)))
    if rng.random() < 0.12:
        last_activity = date(2022, 1, 1) + timedelta(days=rng.randint(0, 300))  # stale
    first, last = rng.choice(FIRST), rng.choice(LAST)
    return {
        "Deal ID": f"D-{10000 + i}",
        "Deal Name": f"{account_key} - {rng.choice(['Renewal', 'Expansion', 'New Logo', 'Pilot', 'Upsell'])}",
        "Account": account,
        "Contact Email": f"{first.lower()}.{last.lower()}@{DOMAINS[account_key]}",
        "Owner": rng.choice(OWNERS),
        "Stage": stage,
        "Amount": money_text(rng, amount, currency),
        "Currency": currency,
        "Close Date": close.isoformat(),
        "Created Date": created.isoformat(),
        "Lead Source": rng.choice(LEAD_SOURCES),
        "Region": region,
        "Last Activity": last_activity.isoformat(),
        "Contact Phone": f"+1-{rng.randint(200, 999)}-{rng.randint(200, 999)}-{rng.randint(1000, 9999)}",
    }


def plant_junk(rng: random.Random, rows: list[dict]) -> None:
    """Placeholder junk and internal test records."""
    for row in rng.sample(rows, 25):
        row["Contact Phone"] = "000-000-0000"
    for row in rng.sample(rows, 8):
        row["Account"] = rng.choice(["asdf", "test", "Test Account"])
    for row in rng.sample(rows, 6):
        row["Amount"] = "$1"
    for row in rng.sample(rows, 14):
        row["Contact Email"] = f"qa{rng.randint(1, 9)}@dataful-internal.com"
        row["Account"] = "Dataful Internal Test"


def repeat_per_contact(rng: random.Random, rows: list[dict]) -> list[dict]:
    """Some deals are exported once per contact: same deal, same amount, different email."""
    out: list[dict] = []
    for row in rows:
        out.append(row)
        if rng.random() < 0.08:
            domain = row["Contact Email"].split("@")[1]
            for _ in range(rng.randint(1, 3)):
                extra = dict(row)
                extra["Contact Email"] = f"{rng.choice(FIRST).lower()}.{rng.choice(LAST).lower()}@{domain}"
                extra["Contact Phone"] = f"+1-{rng.randint(200, 999)}-{rng.randint(200, 999)}-{rng.randint(1000, 9999)}"
                out.append(extra)
    return out


def main() -> None:
    rng = random.Random(SEED)
    rows = [make_deal(rng, i) for i in range(N_DEALS)]
    plant_junk(rng, rows)
    rows = repeat_per_contact(rng, rows)
    for row in rng.sample(rows, 12):  # exact duplicate exports
        rows.insert(rng.randint(0, len(rows)), dict(row))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows -> {OUT}")


if __name__ == "__main__":
    main()
