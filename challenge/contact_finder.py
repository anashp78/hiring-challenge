"""
contact_finder.py — AgentCollect hiring challenge, Stage B solution.

Reads companies.csv + enrichment_responses.json (mock providers).
Outputs contacts.csv with confidence scoring, provenance, and needs_human_review flags.

Usage:
    python challenge/contact_finder.py

Output: challenge/output/contacts.csv
"""

import json
import csv
from pathlib import Path

CONFIDENCE_THRESHOLD = 70  # per CLARIFICATIONS.md

# ── Name normalization ────────────────────────────────────────────────────────

def normalize_name(name: str) -> str:
    """Lowercase, strip titles, parentheticals, and leading/trailing whitespace."""
    if not name:
        return ""
    import re
    n = name.lower().strip()
    # Strip parenthetical role suffixes e.g. "Jeff (manager)"
    n = re.sub(r"\s*\(.*?\)", "", n).strip()
    for title in ["dr.", "dr ", "mr.", "ms.", "mrs.", "prof."]:
        n = n.replace(title, "").strip()
    return n


def names_agree(a: str, b: str) -> tuple[bool, bool]:
    """
    Returns (agree, conflict) for two name strings.
    agree=True  → corroboration bonus (+20)
    conflict=True → conflict penalty (-20) and human review flag
    Same last name but different first → (False, False): no bonus, no penalty.
    """
    a, b = normalize_name(a), normalize_name(b)
    if not a or not b:
        return False, False
    if a == b:
        return True, False
    a_parts, b_parts = a.split(), b.split()
    if not a_parts or not b_parts:
        return False, False
    same_last = a_parts[-1] == b_parts[-1]
    if same_last:
        # Same last name: check first initial for corroboration
        if a_parts[0][0] == b_parts[0][0]:
            return True, False   # S. Murphy / Sean Murphy
        else:
            return False, False  # Bob/Robert Kowalski — ambiguous, not a conflict
    # Different last names entirely → genuine conflict
    return False, True


# ── Role priority (lower = more decision-making authority for collections) ───

ROLE_PRIORITY = {
    "ap manager": 1,
    "accounts payable": 1,
    "cfo": 2,
    "finance": 2,
    "owner": 3,
    "founder": 3,
    "president": 3,
    "ceo": 3,
    "office manager": 4,
    "manager": 5,
    "registered agent": 9,  # usually not the right person
}


def role_priority(role: str) -> int:
    if not role:
        return 6
    r = role.lower()
    for key, pri in ROLE_PRIORITY.items():
        if key in r:
            return pri
    return 6


# ── Core scoring ──────────────────────────────────────────────────────────────

def compute_contact(registry: dict | None, listing: dict | None, enrichment: dict | None) -> dict:
    """
    Merge three provider responses into a single scored contact record.

    Returns a dict with:
        contact_name, contact_role, contact_email_or_phone,
        confidence_score, source_urls (list), conflict (bool), notes
    """
    score = 0
    source_urls: list[str] = []
    name_candidates: list[tuple[str, str, int]] = []  # (name, role, priority)
    contact_method = ""
    notes_parts: list[str] = []

    # ── Registry ────────────────────────────────────────────────────────────
    if registry:
        source_urls.append(registry["source_url"])
        name = registry.get("name") or ""
        role = registry.get("role") or ""
        if name:
            pri = role_priority(role)
            name_candidates.append((name, role, pri))
            score += 25
            if pri <= 3:
                score += 15   # confirmed decision-maker role
            elif pri == 9:
                score -= 5    # registered agent — likely wrong person
                notes_parts.append("registry has registered agent only")

    # ── Listing ──────────────────────────────────────────────────────────────
    if listing:
        source_urls.append(listing["source_url"])
        name = listing.get("name") or ""
        phone = listing.get("phone") or ""
        if name:
            name_candidates.append((name, "", role_priority("")))
            score += 15
        if phone:
            score += 8
            if not contact_method:
                contact_method = phone

    # ── Enrichment ───────────────────────────────────────────────────────────
    if enrichment:
        source_urls.append(enrichment["source_url"])
        provider_conf: int = enrichment.get("provider_confidence", 0)
        email = enrichment.get("email") or ""
        phone = enrichment.get("phone") or ""
        if email or phone:
            # Provider confidence contributes but doesn't dominate
            score += int(provider_conf * 0.25)
            if email:
                contact_method = email  # prefer email over listing phone
            elif phone and not contact_method:
                contact_method = phone

    # ── Cross-source name agreement / conflict ────────────────────────────────
    real_names = [(n, r, p) for n, r, p in name_candidates if n]
    conflict = False

    if len(real_names) >= 2:
        agree, conf = names_agree(real_names[0][0], real_names[1][0])
        if agree:
            score += 20   # independent corroboration
        elif conf:
            score -= 20   # genuinely different people
            conflict = True
            notes_parts.append(
                f"name conflict: '{real_names[0][0]}' vs '{real_names[1][0]}'"
            )
        # same last name, different first → no bonus, no penalty, no conflict flag

    # ── Single-enrichment penalty ────────────────────────────────────────────
    if enrichment and not registry and not listing:
        score = int(score * 0.75)
        notes_parts.append("single enrichment source only")

    # ── Pick best name ────────────────────────────────────────────────────────
    contact_name = ""
    contact_role = ""
    if real_names:
        best = sorted(real_names, key=lambda x: x[2])[0]
        contact_name = best[0]
        contact_role = best[1]
        if not contact_role and contact_name.lower().startswith(("dr.", "dr ")):
            contact_role = "Owner / Practitioner"
        elif not contact_role:
            contact_role = "Owner"  # default for small SMB with no role given

    score = max(0, min(100, round(score)))
    return {
        "contact_name":           contact_name,
        "contact_role":           contact_role,
        "contact_email_or_phone": contact_method,
        "confidence_score":       score,
        "source_urls":            source_urls,
        "conflict":               conflict,
        "notes":                  "; ".join(notes_parts),
    }


# ── Pipeline ──────────────────────────────────────────────────────────────────

def process(csv_path: str, mock_path: str, output_path: str) -> None:
    mocks: dict = json.loads(Path(mock_path).read_text())
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    output_rows = []

    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            company = row["company_name"]
            mock    = mocks.get(company, {})

            result = compute_contact(
                registry=mock.get("registry"),
                listing=mock.get("listing"),
                enrichment=mock.get("enrichment"),
            )

            score         = result["confidence_score"]
            no_contact    = not result["contact_email_or_phone"]
            no_name       = not result["contact_name"]
            conflict      = result["conflict"]
            needs_review  = score < CONFIDENCE_THRESHOLD or no_contact or no_name or conflict

            output_rows.append({
                "company_name":           company,
                "mailing_address":        row["mailing_address"],
                "contact_name":           result["contact_name"]           if not needs_review else "",
                "contact_role":           result["contact_role"]           if not needs_review else "",
                "contact_email_or_phone": result["contact_email_or_phone"] if not needs_review else "",
                "confidence_score":       score,
                "source":                 " | ".join(result["source_urls"]),
                "needs_human_review":     "true" if needs_review else "false",
                "notes":                  result["notes"],
            })

    fieldnames = [
        "company_name", "mailing_address", "contact_name", "contact_role",
        "contact_email_or_phone", "confidence_score", "source",
        "needs_human_review", "notes",
    ]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    found   = sum(1 for r in output_rows if r["needs_human_review"] == "false")
    flagged = len(output_rows) - found
    print(f"Processed {len(output_rows)} companies -> {output_path}")
    print(f"  {found} contacts verified ({found / len(output_rows) * 100:.0f}%)")
    print(f"  {flagged} flagged for human review")
    print()

    # Print summary table
    print(f"{'Company':<35} {'Score':>5}  {'Review':>6}  Contact")
    print("-" * 80)
    for r in output_rows:
        flag   = "YES" if r["needs_human_review"] == "true" else "   "
        contact = r["contact_email_or_phone"] or r["notes"] or "(no data)"
        print(f"{r['company_name']:<35} {r['confidence_score']:>5}  {flag:>6}  {contact[:35]}")


if __name__ == "__main__":
    process(
        csv_path="challenge/data/companies.csv",
        mock_path="challenge/mocks/enrichment_responses.json",
        output_path="challenge/output/contacts.csv",
    )
