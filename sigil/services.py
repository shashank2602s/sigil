"""Workflow logic: versions, decisions, review gates, comments and the audit trail.

Design rule: nothing is ever applied or approved automatically. Every state change is
made by a person with the right role, and every change is written to the audit log.
"""
import json
from datetime import datetime, timezone

from .engine import apply_edits, load_brand, review

STATUS_LABEL = {
    "draft": "Draft",
    "in_review": "In review",
    "changes_requested": "Changes requested",
    "reviewed": "Reviewed, awaiting manager",
    "approved": "Approved",
}
EDITABLE = ("draft", "changes_requested")
REVIEWABLE = ("in_review", "reviewed")
MAX_BODY = 20000


class ServiceError(Exception):
    """A user-facing problem (shown as a message, not a crash)."""


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")


def _row(r):
    return dict(r) if r is not None else None


def get_user(conn, user_id):
    return _row(conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())


def get_content(conn, content_id):
    c = _row(conn.execute("SELECT * FROM content WHERE id=?", (content_id,)).fetchone())
    if not c:
        raise ServiceError("That content item does not exist.")
    return c


def latest_version(conn, content_id):
    return _row(conn.execute("SELECT * FROM versions WHERE content_id=? ORDER BY number DESC LIMIT 1",
                             (content_id,)).fetchone())


def get_version(conn, content_id, number):
    return _row(conn.execute("SELECT * FROM versions WHERE content_id=? AND number=?",
                             (content_id, number)).fetchone())


def findings_for(conn, version_id):
    rows = conn.execute(
        "SELECT * FROM findings WHERE version_id=? ORDER BY "
        "CASE severity WHEN 'blocker' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, COALESCE(start, 1000000000), id",
        (version_id,)).fetchall()
    return [dict(r) for r in rows]


def audit(conn, content_id, actor_id, action, detail=""):
    conn.execute("INSERT INTO audit(content_id,actor_id,action,detail,created_at) VALUES (?,?,?,?,?)",
                 (content_id, actor_id, action, detail, now()))


# ---------------------------------------------------------------- versions
def add_version(conn, content_id, body, user, note):
    content = get_content(conn, content_id)
    brand = load_brand(conn, content["workspace_id"])
    notes = json.loads(content["parse_notes"] or "[]")
    findings, dropped = review(body, brand, content["intent"] or "", notes)
    prev = latest_version(conn, content_id)
    number = (prev["number"] + 1) if prev else 1
    carry = {}
    if prev:
        for f in findings_for(conn, prev["id"]):
            if f["state"] in ("rejected", "overridden", "disputed", "upheld"):
                carry[(f["rule"], f["source_type"], f["source_id"], f["original"])] = f
    vid = conn.execute(
        "INSERT INTO versions(content_id,number,body,created_by,created_at,note,dropped) VALUES (?,?,?,?,?,?,?)",
        (content_id, number, body, user["id"], now(), note, dropped)).lastrowid
    for f in findings:
        old = carry.get((f["rule"], f["source_type"], f["source_id"], f.get("original")))
        state, by, reason, at = ("open", None, None, None)
        if old:
            state, by, reason, at = old["state"], old["decided_by"], old["decision_reason"], old["decided_at"]
        conn.execute(
            "INSERT INTO findings(version_id,rule,category,severity,message,why,source_type,source_id,source_label,"
            "source_quote,confidence,start,end,original,replacement,advice,needs_human,intent_conflict,state,"
            "decided_by,decision_reason,decided_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (vid, f["rule"], f["category"], f["severity"], f["message"], f["why"], f["source_type"], f["source_id"],
             f["source_label"], f["source_quote"], f["confidence"], f.get("start"), f.get("end"), f.get("original"),
             f.get("replacement"), f.get("advice"), f["needs_human"], f.get("intent_conflict"),
             state, by, reason, at))
    status = content["status"]
    if status == "changes_requested":
        status = "draft"
    conn.execute("UPDATE content SET status=?, updated_at=? WHERE id=?", (status, now(), content_id))
    audit(conn, content_id, user["id"], f"Version {number} created",
          f"{note}. {len(findings)} findings shown, {dropped} dropped by the citation validator.")
    conn.commit()
    return vid


def _validate_text(body):
    body = (body or "").strip()
    if not body:
        raise ServiceError("Please provide some text to review.")
    if len(body) > MAX_BODY:
        raise ServiceError(f"Text is too long (limit {MAX_BODY} characters).")
    return body


def create_content(conn, user, title, channel, intent, body, notes):
    title = (title or "").strip()[:120] or "Untitled content"
    body = _validate_text(body)
    cid = conn.execute(
        "INSERT INTO content(workspace_id,creator_id,title,channel,intent,status,parse_notes,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (user["workspace_id"], user["id"], title, (channel or "other")[:30], (intent or "").strip()[:300],
         "draft", json.dumps(notes or []), now(), now())).lastrowid
    audit(conn, cid, user["id"], "Content created", title)
    add_version(conn, cid, body, user, "Initial submission")
    return cid


def edit_text(conn, content_id, user, body):
    content = get_content(conn, content_id)
    _require_owner_editable(content, user)
    body = _validate_text(body)
    if body == latest_version(conn, content_id)["body"].strip():
        raise ServiceError("No changes to save.")
    return add_version(conn, content_id, body, user, "Manual edit")


def _require_owner_editable(content, user):
    if user["id"] != content["creator_id"]:
        raise ServiceError("Only the creator can change this content.")
    if content["status"] not in EDITABLE:
        raise ServiceError("This content is locked while it is in review or approved.")


# ---------------------------------------------------------------- decisions
def decide(conn, finding_id, user, action, reason=""):
    f = _row(conn.execute("SELECT * FROM findings WHERE id=?", (finding_id,)).fetchone())
    if not f:
        raise ServiceError("Finding not found.")
    v = _row(conn.execute("SELECT * FROM versions WHERE id=?", (f["version_id"],)).fetchone())
    content = get_content(conn, v["content_id"])
    if latest_version(conn, content["id"])["id"] != v["id"]:
        raise ServiceError("Findings on older versions are read-only.")
    reason = (reason or "").strip()[:500]
    if action in ("accept", "reject", "dispute", "reopen"):
        _require_owner_editable(content, user)
        if action == "accept":
            if f["replacement"] is None:
                raise ServiceError("There is no automatic edit for this finding. Edit the text yourself, "
                                   "or reject or dispute it with a reason.")
            state = "accepted"
        elif action == "reject":
            if f["severity"] == "blocker" and not reason:
                raise ServiceError("Please give a reason for rejecting a blocker. A reviewer will see it.")
            state = "rejected"
        elif action == "dispute":
            if not reason:
                raise ServiceError("Please explain why you think this finding is wrong.")
            state = "disputed"
        else:
            state, reason = "open", ""
    elif action in ("override", "uphold"):
        if user["role"] not in ("reviewer", "manager"):
            raise ServiceError("Only reviewers and managers can do that.")
        if content["status"] not in REVIEWABLE:
            raise ServiceError("This content is not waiting for review.")
        if not reason:
            raise ServiceError("A reason is required and is recorded in the audit log.")
        state = "overridden" if action == "override" else "upheld"
    else:
        raise ServiceError("Unknown action.")
    conn.execute("UPDATE findings SET state=?, decided_by=?, decision_reason=?, decided_at=? WHERE id=?",
                 (state, user["id"] if state != "open" else None, reason or None,
                  now() if state != "open" else None, finding_id))
    audit(conn, content["id"], user["id"], f"Finding {action}",
          f"{f['rule']}: {f['message']}" + (f" | Reason: {reason}" if reason else ""))
    conn.commit()


def apply_accepted(conn, content_id, user):
    content = get_content(conn, content_id)
    _require_owner_editable(content, user)
    v = latest_version(conn, content_id)
    accepted = [f for f in findings_for(conn, v["id"]) if f["state"] == "accepted"]
    if not accepted:
        raise ServiceError("Accept at least one suggested edit first.")
    body, applied, skipped = apply_edits(v["body"], accepted)
    if not applied:
        raise ServiceError("None of the accepted edits could be applied.")
    add_version(conn, content_id, body, user,
                f"Applied {len(applied)} accepted edit(s)" + (f", {len(skipped)} overlapped and were skipped" if skipped else ""))
    return len(applied), len(skipped)


# ---------------------------------------------------------------- workflow
def submit(conn, content_id, user):
    content = get_content(conn, content_id)
    _require_owner_editable(content, user)
    v = latest_version(conn, content_id)
    blockers = [f for f in findings_for(conn, v["id"]) if f["severity"] == "blocker" and f["state"] in ("open", "accepted")]
    if blockers:
        raise ServiceError(f"{len(blockers)} blocker(s) still need action. Fix them, or reject or dispute each "
                           f"with a reason, before submitting.")
    conn.execute("UPDATE content SET status='in_review', updated_at=? WHERE id=?", (now(), content_id))
    audit(conn, content_id, user["id"], "Submitted for review", f"Version {v['number']}")
    conn.commit()


def approval_blockers(conn, content_id):
    v = latest_version(conn, content_id)
    out = []
    for f in findings_for(conn, v["id"]):
        if f["state"] in ("disputed", "upheld"):
            out.append(f)
        elif f["severity"] == "blocker" and f["state"] != "overridden":
            out.append(f)
    return out


def review_decision(conn, content_id, user, decision, comment=""):
    content = get_content(conn, content_id)
    if user["role"] not in ("reviewer", "manager"):
        raise ServiceError("Only reviewers and managers can review.")
    if content["status"] not in REVIEWABLE:
        raise ServiceError("This content is not waiting for review.")
    comment = (comment or "").strip()[:1000]
    if decision == "changes":
        if not comment:
            raise ServiceError("Please say what needs to change.")
        status, label = "changes_requested", "Changes requested"
    elif decision == "approve":
        if user["role"] == "reviewer" and content["status"] == "reviewed":
            raise ServiceError("Already reviewed. Waiting for a manager's final approval.")
        blockers = approval_blockers(conn, content_id)
        if blockers:
            raise ServiceError(f"{len(blockers)} finding(s) need a decision first. Override (waive) or uphold each one "
                               f"with a reason, or request changes.")
        status, label = ("approved", "Approved") if user["role"] == "manager" else ("reviewed", "Reviewed")
    else:
        raise ServiceError("Unknown decision.")
    conn.execute("UPDATE content SET status=?, updated_at=? WHERE id=?", (status, now(), content_id))
    if comment:
        add_comment(conn, content_id, user, comment, commit=False)
    audit(conn, content_id, user["id"], label, comment)
    conn.commit()


def add_comment(conn, content_id, user, body, commit=True):
    body = (body or "").strip()[:1000]
    if not body:
        raise ServiceError("Comment cannot be empty.")
    content = get_content(conn, content_id)
    if content["workspace_id"] != user["workspace_id"]:
        raise ServiceError("Not allowed.")
    v = latest_version(conn, content_id)
    conn.execute("INSERT INTO comments(content_id,version_id,user_id,body,created_at) VALUES (?,?,?,?,?)",
                 (content_id, v["id"], user["id"], body, now()))
    if commit:
        audit(conn, content_id, user["id"], "Comment added", body[:120])
        conn.commit()


# ---------------------------------------------------------------- queries
def list_content(conn, user):
    if user["role"] == "creator":
        rows = conn.execute("SELECT * FROM content WHERE creator_id=? ORDER BY updated_at DESC, id DESC",
                            (user["id"],)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM content WHERE workspace_id=? ORDER BY updated_at DESC, id DESC",
                            (user["workspace_id"],)).fetchall()
    items = []
    for r in rows:
        c = dict(r)
        v = latest_version(conn, c["id"])
        fs = findings_for(conn, v["id"])
        c["version"] = v["number"]
        c["blockers"] = sum(1 for f in fs if f["severity"] == "blocker" and f["state"] not in ("overridden",))
        c["open_findings"] = sum(1 for f in fs if f["state"] == "open")
        c["disputed"] = sum(1 for f in fs if f["state"] in ("disputed", "upheld"))
        c["creator"] = get_user(conn, c["creator_id"])["name"]
        c["status_label"] = STATUS_LABEL[c["status"]]
        items.append(c)
    return items


def insights(conn, user):
    ws = user["workspace_id"]
    q = conn.execute
    by_cat = [dict(r) for r in q(
        "SELECT f.category, COUNT(*) n FROM findings f JOIN versions v ON v.id=f.version_id "
        "JOIN content c ON c.id=v.content_id WHERE c.workspace_id=? GROUP BY f.category ORDER BY n DESC", (ws,))]
    by_rule = [dict(r) for r in q(
        "SELECT f.rule, f.category, COUNT(*) n FROM findings f JOIN versions v ON v.id=f.version_id "
        "JOIN content c ON c.id=v.content_id WHERE c.workspace_id=? GROUP BY f.rule ORDER BY n DESC LIMIT 8", (ws,))]
    by_status = [dict(r) for r in q("SELECT status, COUNT(*) n FROM content WHERE workspace_id=? GROUP BY status", (ws,))]
    totals = dict(q("SELECT (SELECT COUNT(*) FROM content WHERE workspace_id=?) items,"
                    "(SELECT COUNT(*) FROM versions v JOIN content c ON c.id=v.content_id WHERE c.workspace_id=?) versions,"
                    "(SELECT COALESCE(SUM(dropped),0) FROM versions v JOIN content c ON c.id=v.content_id "
                    " WHERE c.workspace_id=?) dropped", (ws, ws, ws)).fetchone())
    return {"by_cat": by_cat, "by_rule": by_rule, "by_status": by_status, "totals": totals}
