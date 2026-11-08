"""Sample brand pack (a fictional company, LumaPay), demo users and sample content."""
from datetime import date, timedelta

WORKSPACE = "LumaPay (sample brand)"

USERS = [
    ("Priya Nair", "creator", "Content Creator, Marketing"),
    ("Arjun Mehta", "reviewer", "Reviewer, Legal and Compliance"),
    ("Meera Iyer", "manager", "Brand Manager"),
    ("Dev Rao", "admin", "Brand Owner and Admin"),
]

GUIDELINES = [
    ("tone", "Voice and tone",
     "LumaPay sounds confident, warm and clear. We never use slang or hype words, and we limit exclamation "
     "marks to one per piece. Avoid ALL CAPS for emphasis. Speak to people as customers, not as an audience to be impressed."),
    ("plain", "Plain language",
     "Write sentences under 25 words. Prefer the active voice. Explain any financial jargon the first time it appears."),
    ("claims", "Claims and promises policy",
     "We never promise guaranteed returns, zero risk or 100% outcomes. Superlatives such as best, fastest or number one "
     "require an approved proof point from the Approved Facts library. Comparisons with named competitors need legal sign-off."),
    ("terminology", "Terminology",
     "Write LumaPay as one word with a capital L and P. Use Get started, not Sign up. Say customers, not users. "
     "The old product name PayEasy is retired; use LumaPay Instant."),
    ("facts", "Facts and figures",
     "Never quote figures from memory; every number must match the Approved Facts library. If a fact has expired, "
     "ask the brand owner to refresh it before publishing."),
    ("a11y", "Accessibility",
     "Every image needs alt text. Link text must describe the destination; never use click here. "
     "Text must keep a contrast ratio of at least 4.5:1 against its background."),
    ("legal", "Required disclaimers",
     "Any content that mentions rates, returns, cashback, savings or percentages must include the line Terms apply. "
     "Never describe a product as regulated or insured unless an approved fact says so."),
]

today = date.today()
FACTS = [
    ("LumaPay processes over 2 million transactions per month.", "Finance dashboard, Oct 2026",
     (today + timedelta(days=150)).isoformat()),
    ("Domestic transfers settle within 1 business day.", "Operations handbook v4",
     (today + timedelta(days=300)).isoformat()),
    ("The transaction fee is 1.2% for domestic cards.", "Pricing sheet 2026",
     (today + timedelta(days=200)).isoformat()),
    ("LumaPay is certified PCI DSS Level 1.", "Compliance register", (today + timedelta(days=240)).isoformat()),
    ("LumaPay is available in 14 cities across India.", "Growth team report, Q3 2026",
     (today + timedelta(days=90)).isoformat()),
    ("Customer support is available 24x7 on chat and from 9am to 9pm on phone.", "Support handbook",
     (today + timedelta(days=365)).isoformat()),
    ("LumaPay serves more than 40,000 merchants.", "Sales report, Q1 2026", "2026-06-30"),  # deliberately expired
]

TERMS = [
    ("preferred", "sign up, sign-up, signup", "Get started", "Approved call to action is \"Get started\", not \"Sign up\"."),
    ("preferred", "users", "customers", "Say \"customers\", not \"users\"."),
    ("preferred", "Luma Pay, Luma-Pay", "LumaPay", "LumaPay is always one word."),
    ("case", "LumaPay", "LumaPay", "LumaPay is written with a capital L and a capital P, with no other capitals."),
    ("retired", "PayEasy", "LumaPay Instant", "PayEasy is a retired product name; use \"LumaPay Instant\"."),
    ("banned", "cheap, cheapest payments", "affordable", "\"Cheap\" is banned; say \"affordable\" or give the actual price."),
    ("tone", "awesome", "excellent", "Hype words such as \"awesome\" are off-brand."),
    ("tone", "killer", "outstanding", "Hype words such as \"killer\" are off-brand."),
    ("tone", "crazy, insane", "remarkable", "Hype words such as \"crazy\" and \"insane\" are off-brand."),
    ("tone", "epic", "impressive", "Hype words such as \"epic\" are off-brand."),
    ("tone", "game-changer, game changer", "major improvement", "Hype words such as \"game-changer\" are off-brand."),
    ("tone", "hey guys", "Hello", "Slang greetings such as \"hey guys\" are off-brand."),
    ("tone", "gonna", "going to", "Slang such as \"gonna\" is off-brand."),
    ("tone", "wanna", "want to", "Slang such as \"wanna\" is off-brand."),
]

ASSETS = [
    ("palette", "Brand teal", "#0E7C86"), ("palette", "Ink navy", "#14213D"), ("palette", "Signal amber", "#FCA311"),
    ("palette", "Paper white", "#F8F9FA"), ("logo", "LumaPay primary logo", "logo-primary.svg"),
    ("logo", "LumaPay icon", "logo-icon.svg"), ("font", "Heading font", "Poppins"), ("font", "Body font", "Inter"),
]

SAMPLES = {
    "1": ("Launch post (many issues)", "social",
          "Announce LumaPay Instant with an upbeat tone",
          "Hey guys!! LumaPay Instant is here and it's AWESOME!! Sign up today and get 5% cashback on every payment, "
          "GUARANTEED. Our users love us because we are the fastest payments app in India and we process over 5 million "
          "transactions every month. Click here to join the 40,000 merchants who already trust Lumapay."),
    "2": ("Fees explainer (facts)", "website",
          "Explain our fees and settlement times clearly",
          "LumaPay charges a transaction fee of 2.5% on domestic cards. Domestic transfers settle within 2 business days. "
          "Our support team is available on chat at any time. LumaPay is certified PCI DSS Level 1. Terms apply."),
    "3": ("Clean example", "email",
          "Welcome new shops to LumaPay",
          "LumaPay helps small shops accept payments in minutes. Customers can pay by card or UPI, and domestic transfers "
          "settle within 1 business day. Get started on our website today."),
    "4": ("Retired name and long sentence", "blog",
          "Tell existing customers about the rename from PayEasy",
          "PayEasy is now LumaPay Instant, and because we know that moving to a new name can feel confusing for busy shop "
          "owners who have used the old name for years and who rely on our service every single day of the week, we have "
          "kept every feature exactly the same. ![](banner.png) Read more on our website."),
}


def seed(conn):
    """Idempotent: only runs on an empty database."""
    from . import services

    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        return
    ws = conn.execute("INSERT INTO workspaces(name) VALUES (?)", (WORKSPACE,)).lastrowid
    ids = {}
    for name, role, title in USERS:
        ids[role] = conn.execute("INSERT INTO users(workspace_id,name,role,title) VALUES (?,?,?,?)",
                                 (ws, name, role, title)).lastrowid
    for key, title, text in GUIDELINES:
        conn.execute("INSERT INTO guidelines(workspace_id,key,title,text) VALUES (?,?,?,?)", (ws, key, title, text))
    for statement, source, valid in FACTS:
        conn.execute("INSERT INTO facts(workspace_id,statement,source,valid_until) VALUES (?,?,?,?)",
                     (ws, statement, source, valid))
    for kind, avoid, preferred, reason in TERMS:
        conn.execute("INSERT INTO terms(workspace_id,kind,avoid,preferred,reason) VALUES (?,?,?,?,?)",
                     (ws, kind, avoid, preferred, reason))
    for typ, name, value in ASSETS:
        conn.execute("INSERT INTO assets(workspace_id,type,name,value) VALUES (?,?,?,?)", (ws, typ, name, value))
    conn.commit()

    creator = services.get_user(conn, ids["creator"])
    reviewer = services.get_user(conn, ids["reviewer"])

    # Queue item 1: a clean-ish post, fixed by the creator and submitted for review.
    cid = services.create_content(conn, creator, "Weekend fee reminder", "email",
                                  "Remind customers of our domestic card fee in a friendly way",
                                  "This weekend, enjoy an awesome 1.2% fee on domestic cards. Get started on our website. "
                                  "Terms apply.", [])
    v = services.latest_version(conn, cid)
    for f in services.findings_for(conn, v["id"]):
        services.decide(conn, f["id"], creator, "accept", "")
    services.apply_accepted(conn, cid, creator)
    services.submit(conn, cid, creator)

    # Queue item 2: creator disputes a blocker; a reviewer must decide.
    cid2 = services.create_content(conn, creator, "Savings app announcement", "social",
                                   "Announce that settlements are dependable",
                                   "Join today: your settlements are guaranteed. Terms apply.", [])
    v2 = services.latest_version(conn, cid2)
    for f in services.findings_for(conn, v2["id"]):
        if f["rule"] == "promise":
            services.decide(conn, f["id"], creator, "dispute",
                            "Product team says this describes settlement timing, not investment returns.")
    services.submit(conn, cid2, creator)
    _ = reviewer
    conn.commit()
