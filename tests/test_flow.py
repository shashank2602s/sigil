"""End-to-end tests: the full create > review > decide > approve workflow through the real app."""
import io
import os
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sigil.web import create_app  # noqa: E402
from sigil import seed  # noqa: E402


@pytest.fixture()
def env():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "t.db")
    app = create_app(path)
    app.config["TESTING"] = True
    return app.test_client(), path


def q(path, sql, *a):
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    rows = c.execute(sql, a).fetchall()
    c.close()
    return rows


def login(client, role):
    return client.get(f"/login/{role}", follow_redirects=True)


def create(client, sample="1"):
    t, ch, intent, body = seed.SAMPLES[sample]
    r = client.post("/new", data={"title": t, "channel": ch, "intent": intent, "text": body})
    assert r.status_code == 302
    return int(r.headers["Location"].rsplit("/", 1)[-1])


def test_public_pages(env):
    c, _ = env
    for url in ("/", "/about", "/healthz"):
        assert c.get(url).status_code == 200
    assert c.get("/dashboard", follow_redirects=False).status_code == 302  # needs a demo role


def test_seeded_review_queue(env):
    c, _ = env
    r = login(c, "reviewer")
    assert b"Waiting for your review" in r.data
    assert b"Weekend fee reminder" in r.data and b"Savings app announcement" in r.data


def test_review_shows_cited_findings(env):
    c, path = env
    login(c, "creator")
    cid = create(c)
    page = c.get(f"/content/{cid}").data.decode()
    assert "Prohibited promise" in page and "differs from the approved fact" in page
    assert "Approved fact" in page and "Terminology list" in page
    rows = q(path, "SELECT source_quote, source_type, source_id FROM findings")
    assert rows and all(r["source_quote"] and r["source_id"] for r in rows)


def test_full_workflow(env):
    c, path = env
    login(c, "creator")
    cid = create(c)

    # Submitting with open blockers is refused.
    r = c.post(f"/content/{cid}/submit", follow_redirects=True)
    assert b"blocker(s) still need action" in r.data
    assert q(path, "SELECT status FROM content WHERE id=?", cid)[0]["status"] == "draft"

    # Accept a suggested edit, apply it as a new version.
    fid = q(path, "SELECT id FROM findings WHERE rule='terminology' AND original='users'")[0]["id"]
    c.post(f"/finding/{fid}/accept", data={"reason": ""})
    r = c.post(f"/content/{cid}/apply", follow_redirects=True)
    assert b"Applied 1 edit" in r.data
    v2 = q(path, "SELECT * FROM versions WHERE content_id=? AND number=2", cid)[0]
    assert "customers" in v2["body"] and "users love" not in v2["body"]

    # Reject without a reason on a blocker is refused; dispute needs a reason.
    blockers = q(path, "SELECT f.id FROM findings f JOIN versions v ON v.id=f.version_id "
                       "WHERE v.content_id=? AND v.number=2 AND f.severity='blocker'", cid)
    assert len(blockers) == 2
    r = c.post(f"/finding/{blockers[0]['id']}/reject", data={"reason": ""}, follow_redirects=True)
    assert b"give a reason" in r.data
    c.post(f"/finding/{blockers[0]['id']}/reject", data={"reason": "Legal agreed wording"})
    c.post(f"/finding/{blockers[1]['id']}/dispute", data={"reason": "Figure is from the new dashboard"})
    r = c.post(f"/content/{cid}/submit", follow_redirects=True)
    assert b"Submitted for review" in r.data

    # Creator cannot act on a locked item or use reviewer powers.
    r = c.post(f"/finding/{blockers[0]['id']}/override", data={"reason": "x"}, follow_redirects=True)
    assert b"Only reviewers and managers" in r.data

    # Reviewer cannot approve while blockers stand; must waive or uphold each.
    login(c, "reviewer")
    r = c.post(f"/content/{cid}/decision", data={"decision": "approve"}, follow_redirects=True)
    assert b"need a decision first" in r.data
    r = c.post(f"/finding/{blockers[0]['id']}/override", data={"reason": ""}, follow_redirects=True)
    assert b"reason is required" in r.data
    c.post(f"/finding/{blockers[0]['id']}/override", data={"reason": "Wording approved by legal"})
    c.post(f"/finding/{blockers[1]['id']}/override", data={"reason": "Checked: dashboard shows 5M"})
    # Remaining warnings do not block approval.
    r = c.post(f"/content/{cid}/decision", data={"decision": "approve", "comment": "Looks fine"}, follow_redirects=True)
    assert b"Decision recorded" in r.data
    assert q(path, "SELECT status FROM content WHERE id=?", cid)[0]["status"] == "reviewed"

    # Only a manager gives final approval.
    login(c, "manager")
    c.post(f"/content/{cid}/decision", data={"decision": "approve"})
    assert q(path, "SELECT status FROM content WHERE id=?", cid)[0]["status"] == "approved"

    # Audit trail records who did what.
    actions = [r["action"] for r in q(path, "SELECT action FROM audit WHERE content_id=? ORDER BY id", cid)]
    for expected in ("Content created", "Version 2 created", "Submitted for review", "Finding override", "Approved"):
        assert expected in actions
    assert b"Printable review report" in c.get(f"/content/{cid}").data
    assert c.get(f"/content/{cid}/report").status_code == 200


def test_request_changes_and_new_version(env):
    c, path = env
    login(c, "reviewer")
    cid = q(path, "SELECT id FROM content WHERE title='Weekend fee reminder'")[0]["id"]
    r = c.post(f"/content/{cid}/decision", data={"decision": "changes", "comment": ""}, follow_redirects=True)
    assert b"what needs to change" in r.data
    c.post(f"/content/{cid}/decision", data={"decision": "changes", "comment": "Please mention the fee limit."})
    assert q(path, "SELECT status FROM content WHERE id=?", cid)[0]["status"] == "changes_requested"
    login(c, "creator")
    c.post(f"/content/{cid}/edit", data={"text": "Enjoy a clear 1.2% fee on domestic cards. Get started today. Terms apply."})
    assert q(path, "SELECT status FROM content WHERE id=?", cid)[0]["status"] == "draft"


def test_disputed_seed_item_needs_reviewer_decision(env):
    c, path = env
    login(c, "reviewer")
    cid = q(path, "SELECT id FROM content WHERE title='Savings app announcement'")[0]["id"]
    r = c.post(f"/content/{cid}/decision", data={"decision": "approve"}, follow_redirects=True)
    assert b"need a decision first" in r.data
    fid = q(path, "SELECT f.id FROM findings f JOIN versions v ON v.id=f.version_id WHERE v.content_id=? "
                  "AND f.rule='promise'", cid)[0]["id"]
    c.post(f"/finding/{fid}/uphold", data={"reason": "Wording is still a promise"})
    assert q(path, "SELECT state FROM findings WHERE id=?", fid)[0]["state"] == "upheld"
    r = c.post(f"/content/{cid}/decision", data={"decision": "approve"}, follow_redirects=True)
    assert b"need a decision first" in r.data


def test_permissions(env):
    c, path = env
    login(c, "creator")
    assert c.post("/brand/fact", data={"statement": "x"}).status_code == 403
    other = q(path, "SELECT id FROM content LIMIT 1")[0]["id"]
    create(c)  # creator can see own content
    login(c, "admin")
    assert c.post("/brand/fact", data={"statement": "LumaPay has 3 offices.", "source": "HR"}).status_code == 302
    assert q(path, "SELECT COUNT(*) n FROM facts WHERE statement LIKE '%3 offices%'")[0]["n"] == 1
    assert c.get("/brand").status_code == 200 and c.get("/insights").status_code == 200
    assert other


def test_admin_rule_changes_apply_to_next_review(env):
    c, path = env
    login(c, "admin")
    c.post("/brand/term", data={"kind": "banned", "avoid": "synergy", "preferred": "teamwork",
                                "reason": "Corporate buzzwords are banned."})
    login(c, "creator")
    cid = create(c, "3")
    assert b"synergy" not in c.get(f"/content/{cid}").data
    r = c.post("/new", data={"title": "t", "text": "Our synergy is great."})
    page = c.get(r.headers["Location"]).data
    assert b"synergy" in page and b"Corporate buzzwords are banned." in page


def test_upload_docx_flags_missing_alt_text(env):
    from docx import Document
    from PIL import Image
    c, path = env
    login(c, "creator")
    png = io.BytesIO()
    Image.new("RGB", (20, 20), "teal").save(png, "PNG")
    png.seek(0)
    doc = Document()
    doc.add_paragraph("LumaPay helps shops get started today.")
    doc.add_picture(png)
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    r = c.post("/new", data={"title": "", "channel": "website", "intent": "", "text": "",
                             "file": (buf, "brochure.docx")}, content_type="multipart/form-data")
    assert r.status_code == 302
    page = c.get(r.headers["Location"]).data
    assert b"has no alt text" in page


def test_bad_inputs(env):
    c, _ = env
    login(c, "creator")
    assert c.post("/new", data={"text": ""}).status_code == 400
    r = c.post("/new", data={"text": "", "file": (io.BytesIO(b"x"), "evil.exe")}, content_type="multipart/form-data")
    assert r.status_code == 400 and b"Unsupported file type" in r.data
    assert c.get("/content/9999").status_code == 404
