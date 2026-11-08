"""Flask routes and presentation helpers."""
import difflib
import os
import re
import secrets
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template, request, session, url_for)
from markupsafe import Markup, escape

from . import db, seed, services
from .engine import parsing
from .services import ServiceError

ROLE_LABEL = {"creator": "Creator", "reviewer": "Reviewer", "manager": "Manager", "admin": "Admin"}
ROLE_BLURB = {
    "creator": "Submit content, review the findings, accept or dispute suggested fixes.",
    "reviewer": "Check claims and facts, waive or uphold findings, approve or request changes.",
    "manager": "Everything a reviewer can do, plus final approval and a view of all content.",
    "admin": "Manage the brand pack: guidelines, approved facts, terminology and assets.",
}


def annotate(body, findings):
    marks = [f for f in findings if f["start"] is not None and f["end"] is not None and f["end"] > f["start"]]
    marks.sort(key=lambda f: f["start"])
    out, pos = [], 0
    for f in marks:
        if f["start"] < pos:
            continue
        out.append(escape(body[pos:f["start"]]))
        out.append(Markup(f'<mark class="m-{f["severity"]} s-{f["state"]}" title="{escape(f["message"])}">'
                          f'<a href="#f{f["id"]}">') + escape(body[f["start"]:f["end"]]) + Markup("</a></mark>"))
        pos = f["end"]
    out.append(escape(body[pos:]))
    return Markup("").join(out)


def word_diff(a, b):
    ta, tb = re.findall(r"\s+|\S+", a), re.findall(r"\s+|\S+", b)
    parts = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
        if op == "equal":
            parts.append(escape("".join(ta[i1:i2])))
            continue
        if i2 > i1:
            parts.append(Markup("<del>") + escape("".join(ta[i1:i2])) + Markup("</del>"))
        if j2 > j1:
            parts.append(Markup("<ins>") + escape("".join(tb[j1:j2])) + Markup("</ins>"))
    return Markup("").join(parts)


def create_app(db_path=None):
    base = os.path.dirname(os.path.abspath(__file__))
    app = Flask(__name__, template_folder=os.path.join(base, "templates"),
                static_folder=os.path.join(base, "static"))
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(16)
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["DB_PATH"] = db_path or os.environ.get("SIGIL_DB", os.path.join(base, "..", "data", "sigil.db"))

    conn = db.connect(app.config["DB_PATH"])
    db.init_db(conn)
    seed.seed(conn)
    conn.close()

    def get_db():
        if "db" not in g:
            g.db = db.connect(app.config["DB_PATH"])
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        d = g.pop("db", None)
        if d is not None:
            d.close()

    @app.before_request
    def load_user():
        g.user = None
        uid = session.get("uid")
        if uid:
            g.user = services.get_user(get_db(), uid)

    @app.context_processor
    def inject():
        return {"ROLE_LABEL": ROLE_LABEL, "STATUS_LABEL": services.STATUS_LABEL, "me": g.get("user")}

    @app.template_filter("pct")
    def pct(v):
        return f"{round(v * 100)}%"

    def login_required(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not g.user:
                flash("Choose a demo role to continue.", "info")
                return redirect(url_for("index"))
            return fn(*a, **kw)
        return wrapper

    def role_required(*roles):
        def deco(fn):
            @wraps(fn)
            def wrapper(*a, **kw):
                if g.user["role"] not in roles:
                    abort(403)
                return fn(*a, **kw)
            return wrapper
        return deco

    def load_content(cid):
        try:
            c = services.get_content(get_db(), cid)
        except ServiceError:
            abort(404)
        if c["workspace_id"] != g.user["workspace_id"]:
            abort(404)
        if g.user["role"] == "creator" and c["creator_id"] != g.user["id"]:
            abort(403)
        return c

    # ------------------------------------------------------------ pages
    @app.route("/")
    def index():
        if g.user:
            return redirect(url_for("dashboard"))
        return render_template("index.html", roles=ROLE_LABEL, blurbs=ROLE_BLURB)

    @app.route("/login/<role>")
    def login(role):
        if role not in ROLE_LABEL:
            abort(404)
        row = get_db().execute("SELECT id FROM users WHERE role=? ORDER BY id LIMIT 1", (role,)).fetchone()
        session.clear()
        session["uid"] = row["id"]
        return redirect(url_for("dashboard"))

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("index"))

    @app.route("/about")
    def about():
        return render_template("about.html")

    @app.route("/healthz")
    def healthz():
        return "ok"

    @app.route("/dashboard")
    @login_required
    def dashboard():
        items = services.list_content(get_db(), g.user)
        role = g.user["role"]
        queue = []
        if role in ("reviewer", "manager"):
            wanted = ("in_review",) if role == "reviewer" else ("in_review", "reviewed")
            queue = [i for i in items if i["status"] in wanted]
        rest = [i for i in items if i not in queue]
        return render_template("dashboard.html", queue=queue, items=rest, total=len(items))

    @app.route("/new", methods=["GET", "POST"])
    @login_required
    def new():
        d = get_db()
        if request.method == "POST":
            title, channel = request.form.get("title", ""), request.form.get("channel", "other")
            intent, text = request.form.get("intent", ""), request.form.get("text", "")
            notes = []
            f = request.files.get("file")
            try:
                if f and f.filename:
                    text, notes = parsing.parse_upload(f.filename, f.read())
                    title = title or f.filename
                cid = services.create_content(d, g.user, title, channel, intent, text, notes)
                flash("Review complete. Every finding below cites the guideline or approved source it came from.", "ok")
                return redirect(url_for("content", cid=cid))
            except (ServiceError, ValueError) as e:
                flash(str(e), "error")
                return render_template("new.html", form=request.form, samples=seed.SAMPLES), 400
        form = {}
        s = request.args.get("sample")
        if s in seed.SAMPLES:
            t, ch, intent, body = seed.SAMPLES[s]
            form = {"title": t, "channel": ch, "intent": intent, "text": body}
        return render_template("new.html", form=form, samples=seed.SAMPLES)

    @app.route("/content/<int:cid>")
    @login_required
    def content(cid):
        d = get_db()
        c = load_content(cid)
        versions = [dict(r) for r in d.execute("SELECT * FROM versions WHERE content_id=? ORDER BY number", (cid,))]
        latest = versions[-1]
        want = request.args.get("v", type=int)
        v = next((x for x in versions if x["number"] == want), latest)
        findings = services.findings_for(d, v["id"])
        users = {u["id"]: u["name"] for u in d.execute("SELECT id,name FROM users")}
        for f in findings:
            f["decider"] = users.get(f["decided_by"])
        is_latest = v["id"] == latest["id"]
        owner = g.user["id"] == c["creator_id"]
        can_edit = owner and is_latest and c["status"] in services.EDITABLE
        can_review = (g.user["role"] in ("reviewer", "manager") and is_latest and c["status"] in services.REVIEWABLE)
        diff = None
        if v["number"] > 1:
            prev = next(x for x in versions if x["number"] == v["number"] - 1)
            diff = word_diff(prev["body"], v["body"])
        comments = [dict(r) for r in d.execute(
            "SELECT cm.*, u.name, u.role FROM comments cm JOIN users u ON u.id=cm.user_id "
            "WHERE content_id=? ORDER BY cm.id", (cid,))]
        log = [dict(r) for r in d.execute(
            "SELECT a.*, u.name FROM audit a LEFT JOIN users u ON u.id=a.actor_id WHERE content_id=? ORDER BY a.id DESC",
            (cid,))]
        for ver in versions:
            ver["author"] = users.get(ver["created_by"])
        counts = {"blocker": 0, "warning": 0, "note": 0, "human": 0, "accepted": 0}
        for f in findings:
            counts[f["severity"]] += 1
            counts["human"] += f["needs_human"]
            counts["accepted"] += f["state"] == "accepted"
        blockers_left = services.approval_blockers(d, cid) if is_latest else []
        return render_template(
            "content.html", c=c, v=v, versions=versions, findings=findings, counts=counts, is_latest=is_latest,
            body_html=annotate(v["body"], findings), diff=diff, comments=comments, log=log, can_edit=can_edit,
            can_review=can_review, owner=owner, creator_name=users.get(c["creator_id"]),
            blockers_left=blockers_left, status_label=services.STATUS_LABEL[c["status"]])

    @app.route("/content/<int:cid>/report")
    @login_required
    def report(cid):
        d = get_db()
        c = load_content(cid)
        v = services.latest_version(d, cid)
        users = {u["id"]: u["name"] for u in d.execute("SELECT id,name FROM users")}
        findings = services.findings_for(d, v["id"])
        for f in findings:
            f["decider"] = users.get(f["decided_by"])
        log = [dict(r) for r in d.execute(
            "SELECT a.*, u.name FROM audit a LEFT JOIN users u ON u.id=a.actor_id WHERE content_id=? ORDER BY a.id",
            (cid,))]
        return render_template("report.html", c=c, v=v, findings=findings, log=log,
                               creator_name=users.get(c["creator_id"]), status_label=services.STATUS_LABEL[c["status"]])

    # ------------------------------------------------------------ actions
    def act(fn, cid, ok_msg=None, anchor=""):
        try:
            result = fn()
            if ok_msg:
                flash(ok_msg(result) if callable(ok_msg) else ok_msg, "ok")
        except ServiceError as e:
            get_db().rollback()
            flash(str(e), "error")
        return redirect(url_for("content", cid=cid) + anchor)

    @app.post("/finding/<int:fid>/<action>")
    @login_required
    def finding_action(fid, action):
        d = get_db()
        row = d.execute("SELECT v.content_id FROM findings f JOIN versions v ON v.id=f.version_id WHERE f.id=?",
                        (fid,)).fetchone()
        if not row:
            abort(404)
        load_content(row["content_id"])
        return act(lambda: services.decide(d, fid, g.user, action, request.form.get("reason", "")),
                   row["content_id"], anchor=f"#f{fid}")

    @app.post("/content/<int:cid>/apply")
    @login_required
    def apply_edits(cid):
        load_content(cid)
        return act(lambda: services.apply_accepted(get_db(), cid, g.user), cid,
                   lambda r: f"Applied {r[0]} edit(s) as a new version and re-ran the review.")

    @app.post("/content/<int:cid>/edit")
    @login_required
    def edit(cid):
        load_content(cid)
        return act(lambda: services.edit_text(get_db(), cid, g.user, request.form.get("text", "")), cid,
                   "Saved as a new version and re-ran the review.")

    @app.post("/content/<int:cid>/submit")
    @login_required
    def submit(cid):
        load_content(cid)
        return act(lambda: services.submit(get_db(), cid, g.user), cid, "Submitted for review.")

    @app.post("/content/<int:cid>/decision")
    @login_required
    def decision(cid):
        load_content(cid)
        dec = request.form.get("decision", "")
        return act(lambda: services.review_decision(get_db(), cid, g.user, dec, request.form.get("comment", "")), cid,
                   "Decision recorded.")

    @app.post("/content/<int:cid>/comment")
    @login_required
    def comment(cid):
        load_content(cid)
        return act(lambda: services.add_comment(get_db(), cid, g.user, request.form.get("body", "")), cid,
                   "Comment added.")

    # ------------------------------------------------------------ brand pack
    @app.route("/brand")
    @login_required
    def brand():
        d = get_db()
        ws = g.user["workspace_id"]
        today = services.now()[:10]
        facts = [dict(r) for r in d.execute("SELECT * FROM facts WHERE workspace_id=? ORDER BY id", (ws,))]
        for f in facts:
            f["expired"] = bool(f["valid_until"]) and f["valid_until"] < today
        return render_template(
            "brand.html",
            guidelines=[dict(r) for r in d.execute("SELECT * FROM guidelines WHERE workspace_id=? ORDER BY id", (ws,))],
            facts=facts,
            terms=[dict(r) for r in d.execute("SELECT * FROM terms WHERE workspace_id=? ORDER BY kind, id", (ws,))],
            assets=[dict(r) for r in d.execute("SELECT * FROM assets WHERE workspace_id=? ORDER BY type, id", (ws,))],
            is_admin=g.user["role"] == "admin")

    @app.post("/brand/fact")
    @login_required
    @role_required("admin")
    def add_fact():
        st = request.form.get("statement", "").strip()
        if not st:
            flash("A fact needs a statement.", "error")
        else:
            get_db().execute("INSERT INTO facts(workspace_id,statement,source,valid_until) VALUES (?,?,?,?)",
                             (g.user["workspace_id"], st[:300], request.form.get("source", "")[:120],
                              request.form.get("valid_until") or None))
            get_db().commit()
            flash("Approved fact added.", "ok")
        return redirect(url_for("brand") + "#facts")

    @app.post("/brand/term")
    @login_required
    @role_required("admin")
    def add_term():
        kind, avoid = request.form.get("kind", ""), request.form.get("avoid", "").strip()
        pref, reason = request.form.get("preferred", "").strip(), request.form.get("reason", "").strip()
        if kind not in ("preferred", "retired", "banned", "tone") or not avoid or not reason:
            flash("Choose a type and fill in the words to avoid and the reason.", "error")
        else:
            get_db().execute("INSERT INTO terms(workspace_id,kind,avoid,preferred,reason) VALUES (?,?,?,?,?)",
                             (g.user["workspace_id"], kind, avoid[:200], pref[:100] or None, reason[:200]))
            get_db().commit()
            flash("Terminology rule added. It applies to the next review.", "ok")
        return redirect(url_for("brand") + "#terms")

    @app.post("/brand/guideline")
    @login_required
    @role_required("admin")
    def add_guideline():
        title, text = request.form.get("title", "").strip(), request.form.get("text", "").strip()
        f = request.files.get("file")
        try:
            if f and f.filename:
                text, _ = parsing.parse_upload(f.filename, f.read())
                title = title or f.filename
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("brand") + "#guidelines")
        if not title or not text:
            flash("Give the guideline a title and some text, or upload a file.", "error")
        else:
            get_db().execute("INSERT INTO guidelines(workspace_id,key,title,text) VALUES (?,?,?,?)",
                             (g.user["workspace_id"], None, title[:120], text[:20000]))
            get_db().commit()
            flash("Guideline imported. It is stored and can be cited; automated checks use the terminology list, "
                  "approved facts and core rules.", "ok")
        return redirect(url_for("brand") + "#guidelines")

    @app.post("/brand/<kind>/<int:rid>/delete")
    @login_required
    @role_required("admin")
    def delete_item(kind, rid):
        table = {"fact": "facts", "term": "terms", "guideline": "guidelines"}.get(kind)
        if not table:
            abort(404)
        if kind == "guideline":
            row = get_db().execute("SELECT key FROM guidelines WHERE id=?", (rid,)).fetchone()
            if row and row["key"]:
                flash("Core guidelines are used by the rule engine and cannot be deleted in this build.", "error")
                return redirect(url_for("brand") + "#guidelines")
        get_db().execute(f"DELETE FROM {table} WHERE id=? AND workspace_id=?", (rid, g.user["workspace_id"]))
        get_db().commit()
        flash("Removed.", "ok")
        return redirect(url_for("brand"))

    @app.post("/brand/fact/<int:rid>/toggle")
    @login_required
    @role_required("admin")
    def toggle_fact(rid):
        get_db().execute("UPDATE facts SET status=CASE status WHEN 'approved' THEN 'retired' ELSE 'approved' END "
                         "WHERE id=? AND workspace_id=?", (rid, g.user["workspace_id"]))
        get_db().commit()
        return redirect(url_for("brand") + "#facts")

    @app.route("/insights")
    @login_required
    def insights():
        return render_template("insights.html", data=services.insights(get_db(), g.user))

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("error.html", code=403, msg="You do not have access to that page with this role."), 403

    @app.errorhandler(404)
    def missing(_e):
        return render_template("error.html", code=404, msg="That page does not exist."), 404

    @app.errorhandler(413)
    def too_big(_e):
        return render_template("error.html", code=413, msg="That file is too large (limit 2 MB)."), 413

    return app
