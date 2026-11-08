"""Orchestrates rules, validates citations, applies intent-lock and confidence routing."""
import re
from datetime import date

from .rules import KEY_FOR, RULES, build_ctx  # noqa: F401

SEV_RANK = {"blocker": 0, "warning": 1, "note": 2}
STOP = {"about", "their", "there", "which", "would", "could", "should", "these", "those", "where",
        "while", "other", "being", "announce", "announcing", "launch", "post", "campaign", "content"}


def load_brand(conn, workspace_id):
    today = date.today().isoformat()
    guidelines = [dict(r) for r in conn.execute("SELECT * FROM guidelines WHERE workspace_id=?", (workspace_id,))]
    facts = [dict(r) for r in conn.execute("SELECT * FROM facts WHERE workspace_id=?", (workspace_id,))]
    for f in facts:
        f["live"] = f["status"] == "approved" and not (f["valid_until"] and f["valid_until"] < today)
    terms = [dict(r) for r in conn.execute("SELECT * FROM terms WHERE workspace_id=?", (workspace_id,))]
    return {"guidelines": guidelines, "facts": facts, "terms": terms,
            "gl_by_key": {g["key"]: g for g in guidelines if g["key"]},
            "gl_by_id": {g["id"]: g for g in guidelines},
            "fact_by_id": {f["id"]: f for f in facts},
            "term_by_id": {t["id"]: t for t in terms}}


def _norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def _resolve_source(f, brand):
    """Attach source_id/label for a raw finding; return False if the citation cannot be verified."""
    st = f["source_type"]
    if st == "guideline":
        k = f.pop("source_key", None)
        g = brand["gl_by_key"].get(KEY_FOR.get(k, k))
        if not g:
            return False
        f["source_id"], f["source_label"], doc = g["id"], f"Guideline: {g['title']}", g["text"]
    elif st == "fact":
        fact = brand["fact_by_id"].get(f["source_id"])
        if not fact:
            return False
        f["source_label"], doc = "Approved fact", fact["statement"]
    elif st == "term":
        t = brand["term_by_id"].get(f["source_id"])
        if not t:
            return False
        f["source_label"], doc = "Terminology list", t["reason"]
    else:
        return False
    return bool(f.get("source_quote")) and _norm(f["source_quote"]) in _norm(doc)


def _intent_keywords(intent):
    words = re.findall(r"[A-Za-z]{5,}", intent or "")
    return {w.lower() for w in words if w.lower() not in STOP}


def review(text, brand, intent="", notes=None, today=None):
    """Return (findings, dropped_count). Findings are plain dicts ready to store."""
    ctx = build_ctx(text, brand, notes, today)
    raw = []
    for fn in RULES:
        raw.extend(fn(text, brand, ctx))
    keywords = _intent_keywords(intent)
    findings, dropped = [], 0
    word_spans = {(f.get("start"), f.get("end")) for f in raw if f["rule"] in ("terminology", "tone_word")}
    # An all-caps hype word is reported once, by the more specific rule.
    raw = [f for f in raw if not (f["rule"] == "tone_caps" and (f["start"], f["end"]) in word_spans)]
    for f in raw:
        if not _resolve_source(f, brand):
            dropped += 1  # evidence or silence: unverifiable findings are never shown
            continue
        s, e = f.get("start"), f.get("end")
        f["original"] = text[s:e] if s is not None and e is not None and e > s else None
        f.setdefault("replacement", None)
        f.setdefault("advice", None)
        f["needs_human"] = int(f["confidence"] < 0.6 or f["category"] in ("claims", "facts"))
        f["intent_conflict"] = None
        if f["replacement"] is not None and f["original"]:
            hit = [k for k in keywords if k in f["original"].lower() and k not in f["replacement"].lower()]
            if hit:
                f["intent_conflict"] = (f"This edit would change \"{f['original']}\", which relates to your "
                                        f"stated intent (\"{hit[0]}\"). Check it still says what you mean.")
        findings.append(f)
    findings.sort(key=lambda x: (SEV_RANK[x["severity"]], x["start"] if x.get("start") is not None else 10**9))
    return findings, dropped


def apply_edits(body, findings):
    """Apply accepted edits (never automatically). Returns (new_body, applied_ids, skipped_ids)."""
    edits = [f for f in findings if f["replacement"] is not None and f["start"] is not None]
    edits.sort(key=lambda f: (f["start"], f["end"]), reverse=True)
    applied, skipped, floor = [], [], None
    for f in edits:
        if floor is not None and f["end"] > floor:
            skipped.append(f["id"])
            continue
        body = body[:f["start"]] + f["replacement"] + body[f["end"]:]
        applied.append(f["id"])
        floor = f["start"]
    return body, applied, skipped
