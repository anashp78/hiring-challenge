# PLAN.md — Contact Finder

## Architecture

Input: CSV of `(company_name, mailing_address)`. Output: one row per input with `contact_name`, `contact_role`, `contact_email_or_phone`, `confidence_score`, `source`, `needs_human_review`.

Three-layer pipeline:

1. **Enrichment fanout** — hit all three providers independently. Registry for legal owner identity, listing for public-facing name and phone, enrichment for a contact method with a confidence score attached. No single source is trusted on its own — any of them can be stale, wrong, or gamed.

2. **Signal assembly** — for each company, merge what came back: extract name candidates, contact methods, and provenance URLs. Apply confidence scoring (see Quality section). Pick the best name by decision-maker priority: AP/accounts payable > owner/founder > CFO > office manager > registered agent > no name.

3. **Output gating** — if `confidence_score < 70` or no verifiable contact method exists, emit `contact_email_or_phone = ""` and `needs_human_review = true`. Never fabricate. A clean "cannot verify" is a correct result.

## Sources & Strategy

**Registry** (state business registries): most authoritative for legal identity and owner/officer name. Fails for sole proprietors who file as DBA, very small businesses that never formally registered, and anything recently formed. Role matters: "Owner" or "President" is the signal; "Registered Agent" is often a law firm and not the right contact.

**Listing** (web/maps): good for phone numbers and sometimes a manager name. Less reliable for identity — names are often generic ("Jeff, manager") or absent. Useful for cross-referencing registry names. Fails for businesses with no web presence.

**Enrichment** (email/phone enrichment provider): returns a contact email or phone with a self-reported confidence score. Most likely to have a contact method, least reliable on its own. Provider confidence is an input to my scoring, not the final score — a single enrichment hit with no corroboration is treated with skepticism regardless of what the provider claims.

**Why multiple sources:** one source is gamed, aggregated, or stale. Agreement across two independent sources with different data lineages is the actual signal. Disagreement is a flag, not a tiebreaker.

**How they fail together:** registry is missing → listing and enrichment only; listing is stale → enrichment and registry only; enrichment returns a plausible-format email that doesn't exist → only way to catch it is corroboration. No single failure mode takes down the whole pipeline.

## Quality

**Confidence scoring logic:**

Start at 0. Add:
- Registry found with name: +25. If role is Owner/President/Founder: +15 more. If Registered Agent: -5 (wrong person).
- Listing found with name: +15. Listing phone present: +8.
- Enrichment found with contact method: provider_confidence × 0.25 (up to ~25 pts — provider confidence is a signal, not the answer).
- Two or more sources agree on the same name (fuzzy match for nicknames/initials): +20.
- Two or more sources disagree on name: -20 (flag for human review regardless).
- Single enrichment source only: ×0.75 penalty (one-source contacts are less trustworthy).

Cap at 100, floor at 0.

**Dedupe:** within a single company row, pick one contact. Priority: named owner/founder from registry first, then listing name, then enrichment-only. No cross-company dedupe needed (each company is independent).

**Provenance:** every field is traceable. `source` column carries all `source_url` values pipe-separated. Nothing is emitted without at least one `source_url`. If I can't attribute a value, I don't emit it.

**"Cannot verify" states:** `contact_name = ""`, `contact_role = ""`, `contact_email_or_phone = ""`, `needs_human_review = true`. Returned when: confidence < 70, no name found from any source, or sources conflict on name without resolution. A high `needs_human_review` rate on genuinely ambiguous rows is the correct result.

**False-positive risk:** the main risk is enrichment returning a plausible-format email for the wrong person. Mitigation: if enrichment name doesn't match registry or listing name, confidence is penalized. For FDCPA compliance, a wrong contact is worse than no contact.

## Privacy / Compliance

**Will do:** B2B contact information only. Business email addresses and business phone numbers. Provenance recorded for every value. Opt-out/suppression list support designed in from the start (suppression check before any outreach, not after). Only use publicly available data.

**Will not do:** personal home addresses or personal phone numbers. Social media inference to identify private individuals. Any enrichment that infers protected characteristics. Dark-pattern scraping (CAPTCHAs, rate-limit bypass). Aggregating data on individuals without a legitimate B2B collections purpose.

**FDCPA relevance:** even in B2B, if we're contacting a sole proprietor, collections contact rules apply. The system should flag sole-proprietor indicators and route for human review before outreach.

## Clarifying Questions

**1. Is a Registered Agent an acceptable decision-maker when no owner data is available?**

- Why it matters: Registered Agents are frequently law firms or filing services — not business operators. Sending a collections notice to a registered agent may be legally valid for service of process but operationally useless for driving payment. It also wastes a contact attempt.
- Default assumption if unanswered: No. Registered Agent alone → `needs_human_review = true`. I flag it but don't use it as a contact.
- What changes if answered yes: I add Registered Agent as a lowest-priority fallback tier, confidence capped at 55 (below threshold by default, but available for human reviewers to act on if they choose to lower the threshold for a specific batch).

**2. What is the operational cost of a false positive vs. a false negative?**

- Why it matters: this determines where to set the confidence threshold and how aggressive to be on partial-match rows. If a wrong contact sent a collections notice creates legal liability or client-brand damage, the threshold should be strict (70+, maybe 80+). If a missed contact just delays recovery, the threshold can flex down for human review.
- Default assumption if unanswered: false positives are more costly. I default to 70 threshold and optimize for precision. I would rather flag 40% of rows for human review than send 10% to the wrong person.
- What changes if answered: lower threshold + explicit `low_confidence` tier between 50-70 that generates a softer outreach (postal mail only, no phone/email) vs. flagging the row entirely.

**3. When two independent sources return different names for the same company, which wins — or does conflict always mean human review?**

- Why it matters: the Coastal Breeze Pool Service pattern (registry: Tina Alvarez / Manager; listing: Marcus Webb) is not rare in SMB — ownership changes, silent partners, and management layers all create this. I need a tiebreaker rule or a hard "conflict = human review" policy to apply consistently.
- Default assumption if unanswered: conflict = `needs_human_review = true`, regardless of individual confidence scores. I surface both names in a `notes` field so the human reviewer has the raw signal.
- What changes if answered: if there's a source priority hierarchy (registry always wins over listing when roles conflict), I can implement it and reduce the human review rate for these cases.
