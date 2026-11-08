# Architecture and main technical decisions

## Shape
One Flask application (a modular monolith) with SQLite. No external services at runtime.

```
Browser -> Flask routes (web.py) -> services.py (workflow rules, gates, audit)
                                 -> engine/ (parsing, rules, retrieval, review)
                                 -> SQLite (db.py)
```

| Module | Responsibility |
|---|---|
| `engine/parsing.py` | Text from .txt/.md/.docx/.pdf; flags DOCX images without alt text |
| `engine/rules.py` | Deterministic checks (terminology, tone, promises, comparisons, disclaimers, accessibility) and the figure check |
| `engine/retrieval.py` | Sentence splitting, number normalisation, TF-IDF index of approved facts |
| `engine/review.py` | Runs all rules, **validates citations**, applies the intent lock, routes to humans, applies accepted edits |
| `services.py` | Versions, decisions, submit and approval gates, comments, audit log |
| `web.py` + templates | Routes, role checks, annotated text, word diff |
| `seed.py` | Sample brand (fictional LumaPay), demo users, two queue items |

## Decisions and why
1. **No LLM.** The team has no budget for API keys, and content never leaving the server is a requirement for confidential brand material. The cost is lower recall on subtle language; the benefit is reproducible, explainable results.
2. **Rules first, retrieval second.** Exact checks (terms, caps, promises) are deterministic. Only figure matching uses retrieval: each sentence with a number is matched to the closest approved fact by TF-IDF cosine similarity (threshold 0.22), then numbers are normalised ("5 million" = 5000000) and compared.
3. **Evidence or silence.** Every finding carries `source_type`, `source_id` and `source_quote`. `review._resolve_source` checks the source exists and contains the quote (whitespace-normalised). Otherwise the finding is dropped and counted. There is a test that deletes a guideline and verifies the finding disappears.
4. **Human gates in the workflow layer, not the UI.** Rules are enforced in `services.py` so they hold regardless of the page:
   - Only the owner can accept, reject, dispute or edit, and only in Draft or Changes requested.
   - Submit: no blocker may be open or merely accepted-but-unapplied.
   - Reviewer approve: no blocker may stand unless **waived with a reason**, and no finding may be disputed or upheld. Reviewer approval leads to "Reviewed"; only a manager makes it "Approved".
   - Decisions on a finding carry over to the next version if the same finding reappears, so waivers are not lost when text changes.
5. **Edits are data, not text.** A suggestion stores `start`, `end`, `replacement`. Applying accepted edits is an explicit action that creates a new version; overlapping edits are skipped and reported.
6. **SQLite, one gunicorn worker.** Simple and enough for a demo. The database reseeds on a fresh deploy so judges always see sample data.

## Finding schema
`rule, category, severity (blocker|warning|note), message, why, source_type/id/label/quote, confidence, start, end, original, replacement, advice, needs_human, intent_conflict, state (open|accepted|rejected|disputed|overridden|upheld), decided_by, decision_reason`.

## Security and privacy notes
- No outbound network calls. File uploads limited to 2 MB and four types; parsed text capped at 20,000 characters.
- Jinja autoescaping on; annotated text is escaped before highlight markup is added.
- Demo roles have no passwords and there is no CSRF protection in this build. Not suitable for real confidential data; production would need SSO, CSRF tokens, per-workspace row-level access and encryption at rest.
