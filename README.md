# Sigil: brand governance before publication

Sigil reviews content **before** it is published and checks it against a company's own approved guidelines, facts and terminology. Every finding explains *why* it was raised and **cites the exact source** it came from. Suggested fixes are shown as small before/after edits and are never applied automatically. A role-based workflow (Creator, Reviewer, Manager, Admin) with comments, version history and an audit log keeps a human in charge of every decision.

Built for the Inkloom AI brand-governance problem statement (CodeTitans India 2026, team **hero**, solo entry by Shashank Bhootapally). Everything in this repository was written during the Round 2 build window.

**Live demo:** _(add the Render link here)_  
No sign-up: pick a role on the landing page. First load on the free tier may take 30 to 60 seconds to wake up.

## Try it in two minutes
1. Enter as **Creator** > *New review* > click **Launch post (many issues)** > *Run review*.
2. Read a finding: what, why, the cited guideline or approved fact, confidence, suggested edit.
3. *Accept edit* on a terminology finding, then *Apply accepted edits* (creates version 2 and re-runs the review).
4. *Reject* (with a reason) or *Dispute* the blockers, then *Submit for review*.
5. Switch role to **Reviewer**: *Waive* or *Uphold* each blocker with a reason, then approve. A **Manager** gives final approval.
6. Open the content page: version diff, comments, audit log, and a printable review report.

## What works now (Round 2)
- Brand pack: guidelines, approved facts (with expiry), terminology (preferred, retired, banned, off-brand tone words), reusable assets list. Admin can add and remove facts, terms and guidelines; changes apply to the next review.
- Review of pasted text and uploaded `.txt`, `.md`, `.docx`, `.pdf` files.
- Checks: terminology and brand-name spelling, retired names, off-brand tone words, exclamation and all-caps limits, long sentences, prohibited promises, unsupported superlatives and comparisons, figures compared with approved facts (TF-IDF retrieval), expired facts, missing "Terms apply." disclaimer, non-descriptive link text, missing image alt text (DOCX and Markdown).
- **Evidence or silence:** a citation validator hides any finding whose cited guideline, fact or term does not exist or does not contain the quoted text. Hidden findings are counted and shown.
- **Intent lock:** the creator states the content's purpose; suggested edits that would change words related to it are flagged.
- **Human control:** nothing is auto-applied or auto-approved. Blockers must be fixed, or rejected/disputed with a reason; reviewers must waive or uphold them with a reason before approval; managers give final approval. Claims and facts always route to a human; low-confidence findings are labelled.
- Versions with word-level diff, comments, role permissions, audit log, printable report, basic insights, AI and privacy disclosure page.

## Planned for Round 3
1. **Claim Evidence Ledger:** extract every promotional claim, match it to an approved proof point, list unsupported claims.
2. **Image and visual review:** palette match, logo presence, contrast ratio, missing alt text on images.
3. **Guideline Gap Insights:** rank guideline clauses by violations, disputes and overrides to find unclear rules and stale facts.

## Honest limitations
- There is **no language model**. Analysis is rule-based plus TF-IDF similarity. It will miss subtle tone problems, paraphrased superlatives ("nobody settles faster than we do"), numbers written as words ("five million"), and wrong claims whose numbers happen to match an approved fact. Some flags will be wrong, which is why a person decides.
- Free-text guidelines that an admin imports are stored and can be cited, but automated checks are driven by the terminology list, approved facts and the core rules.
- Authentication is demo roles only (no passwords) and data lives in a local SQLite file that resets on redeploy. Do not enter real confidential content.
- English only. No visual checks yet.
- The included regression set (`tests/corpus`) was written by the developer, so its 100% result shows the rules behave as designed; it is not an independent accuracy figure.

## Run locally
```bash
pip install -r requirements.txt
python wsgi.py            # http://127.0.0.1:5000
python -m pytest tests    # 18 tests
python tests/eval.py      # regression set, writes tests/EVAL_RESULTS.md
```
Set `SIGIL_DB` to change the database path and `SECRET_KEY` for sessions.

## Deploy (Render, free)
Connect this repo in Render as a Web Service; `render.yaml` provides the settings (build: `pip install -r requirements.txt`, start: gunicorn, one worker). Health check: `/healthz`.

## Tech and disclosure
Python 3.13, Flask, SQLite, scikit-learn (TF-IDF), python-docx, pdfplumber, Jinja2, plain CSS. No external APIs or AI services are called at runtime. **Development disclosure:** this project was built with AI coding assistance (Claude by Anthropic); the author directed the scope and tested the result. See `ARCHITECTURE.md` for design decisions.
