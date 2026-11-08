"""Engine-level tests: regression set, citation validator, intent lock, safe edit application."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sigil import db, seed  # noqa: E402
from sigil.engine import apply_edits, load_brand, review  # noqa: E402
import eval as ev  # noqa: E402


def brand():
    conn = db.connect(":memory:")
    db.init_db(conn)
    seed.seed(conn)
    return conn, load_brand(conn, 1)


def test_regression_set_meets_floor():
    rows, planted, caught, clean_docs, clean_fp, extra = ev.run()
    assert caught == planted
    assert clean_fp == 0


def test_every_finding_cites_a_real_source():
    _, b = brand()
    for _, (_, _, intent, body) in seed.SAMPLES.items():
        findings, dropped = review(body, b, intent)
        assert dropped == 0
        for f in findings:
            assert f["source_quote"]
            if f["source_type"] == "guideline":
                assert f["source_quote"] in " ".join(b["gl_by_id"][f["source_id"]]["text"].split())
            elif f["source_type"] == "fact":
                assert f["source_quote"] == b["fact_by_id"][f["source_id"]]["statement"]
            else:
                assert f["source_quote"] == b["term_by_id"][f["source_id"]]["reason"]


def test_validator_hides_findings_whose_source_is_missing():
    """Evidence or silence: if the cited guideline is gone, the finding must not be shown."""
    conn, _ = brand()
    conn.execute("DELETE FROM guidelines WHERE key='claims'")
    b = load_brand(conn, 1)
    findings, dropped = review("Your returns are guaranteed. Terms apply.", b, "")
    assert dropped >= 1
    assert not [f for f in findings if f["rule"] == "promise"]


def test_validator_hides_findings_when_quote_not_in_source():
    conn, _ = brand()
    conn.execute("UPDATE guidelines SET text='Claims are reviewed by legal.' WHERE key='claims'")
    findings, dropped = review("Your returns are guaranteed. Terms apply.", load_brand(conn, 1), "")
    assert dropped >= 1 and not findings


def test_intent_lock_warns_when_edit_touches_intent_words():
    _, b = brand()
    findings, _ = review("PayEasy is now LumaPay Instant.", b, "Tell customers about the rename from PayEasy")
    f = [x for x in findings if x["rule"] == "terminology"][0]
    assert f["intent_conflict"] and "payeasy" in f["intent_conflict"].lower()
    findings, _ = review("PayEasy is now LumaPay Instant.", b, "Welcome new shops")
    assert not [x for x in findings if x["rule"] == "terminology"][0]["intent_conflict"]


def test_claims_and_facts_always_route_to_a_human():
    _, b = brand()
    findings, _ = review("We are the fastest. Our fee is 9%.", b, "")
    for f in findings:
        if f["category"] in ("claims", "facts"):
            assert f["needs_human"] == 1


def test_apply_edits_skips_overlaps_and_keeps_text_safe():
    body = "abcdef"
    fs = [{"id": 1, "start": 0, "end": 4, "replacement": "X"}, {"id": 2, "start": 2, "end": 6, "replacement": "Y"}]
    new, applied, skipped = apply_edits(body, fs)
    assert len(applied) == 1 and len(skipped) == 1
    assert new in ("Xef", "abY")


def test_stale_fact_flagged_and_current_fact_not():
    _, b = brand()
    f1, _ = review("LumaPay serves more than 40,000 merchants.", b, "")
    assert [x["rule"] for x in f1] == ["figure_stale"]
    f2, _ = review("Domestic transfers settle within 1 business day.", b, "")
    assert f2 == []
