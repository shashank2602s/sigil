"""Deterministic brand rules plus retrieval-backed fact checks.

Every rule returns raw findings. A finding is only shown if the citation validator
(review.py) can confirm that the guideline, fact or term it cites really exists and
contains the quoted text. Evidence or silence.
"""
import re
from datetime import date

from .retrieval import FactIndex, extract_numbers, split_sentences

# Quotes that must appear verbatim in the cited guideline chunk.
Q = {
    "tone": "We never use slang or hype words, and we limit exclamation marks to one per piece.",
    "caps": "Avoid ALL CAPS for emphasis.",
    "plain": "Write sentences under 25 words.",
    "promise": "We never promise guaranteed returns, zero risk or 100% outcomes.",
    "superlative": "Superlatives such as best, fastest or number one require an approved proof point from the Approved Facts library.",
    "facts": "Never quote figures from memory; every number must match the Approved Facts library.",
    "a11y_image": "Every image needs alt text.",
    "a11y_link": "Link text must describe the destination; never use click here.",
    "comparison": "Comparisons with named competitors need legal sign-off.",
    "legal": "Any content that mentions rates, returns, cashback, savings or percentages must include the line Terms apply.",
}
KEY_FOR = {"tone": "tone", "caps": "tone", "plain": "plain", "promise": "claims", "superlative": "claims",
           "comparison": "claims", "facts": "facts", "a11y_image": "a11y", "a11y_link": "a11y", "legal": "legal"}

CAPS_OK = {"NEFT", "IMPS", "RTGS", "SWIFT", "FAQS", "HDFC", "ICICI", "AMEX", "DSS", "SMS", "OTP", "HTTP", "HTTPS", "JSON"}
PROMISE_RE = re.compile(
    r"\b(guaranteed?|guarantees?|100\s?%|risk[- ]free|zero[- ]risk|no[- ]risk|assured returns?|"
    r"never fails?|never lose|can(?:no|')t fail)", re.I)
COMPARISON_RE = re.compile(
    r"\b(?:cheaper|faster|better|safer|smarter|lower|higher|more reliable|more secure)\s+than\b|"
    r"\b(?:nobody|no one|no other)\b[^.!?]{0,40}\bthan\b", re.I)
SUPERLATIVE_RE = re.compile(
    r"\b(best|fastest|cheapest|lowest|number one|no\.\s?1|#1|leading|most trusted|most popular|"
    r"top[- ]rated|market leader|unbeatable|world[- ]class)\b", re.I)
LEGAL_TRIGGER_RE = re.compile(r"\b(interest|returns?|cashback|savings?|apr)\b|\d\s?%", re.I)
LINK_RE = re.compile(r"\b(click here|tap here|read more)\b", re.I)
MD_IMG_RE = re.compile(r"!\[\s*\]\(")


def _adapt_case(match_text, replacement):
    if not replacement:
        return replacement
    if match_text[:1].isupper() and not match_text.isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement[:1].lower() + replacement[1:] if not any(c.isupper() for c in replacement[1:]) else replacement


def _variants_regex(avoid, flags=re.I):
    words = [w.strip() for w in avoid.split(",") if w.strip()]
    if not words:
        return None
    words.sort(key=len, reverse=True)
    return re.compile(r"(?<![\w])(" + "|".join(re.escape(w) for w in words) + r")(?![\w])", flags)


def rule_terminology(text, brand, ctx):
    out = []
    for t in brand["terms"]:
        kind = t["kind"]
        if kind == "case":
            pref = t["preferred"]
            rx = re.compile(r"(?<![\w/@.])" + re.escape(pref) + r"(?!\w|\.[a-z])", re.I)
            for m in rx.finditer(text):
                if m.group(0) != pref:
                    out.append(dict(
                        rule="terminology", category="terminology", severity="warning",
                        message=f"Brand name should be written \"{pref}\", not \"{m.group(0)}\".",
                        why="The approved spelling and capitalisation of the brand name must be used everywhere.",
                        source_type="term", source_id=t["id"], source_quote=t["reason"], confidence=0.97,
                        start=m.start(), end=m.end(), replacement=pref))
            continue
        if kind not in ("preferred", "retired", "banned", "tone"):
            continue
        rx = _variants_regex(t["avoid"])
        if rx is None:
            continue
        for m in rx.finditer(text):
            repl = t["preferred"]
            if kind in ("preferred", "banned", "tone") and repl:
                repl = _adapt_case(m.group(0), repl)
            if kind == "tone":
                cat, sev, conf = "tone", "warning", 0.9
                why = "Hype and slang words dilute the confident, clear brand voice."
                src_quote = t["reason"]
            elif kind == "retired":
                cat, sev, conf = "terminology", "blocker", 0.97
                why = "This name or term has been retired; using it publishes outdated information."
                src_quote = t["reason"]
            elif kind == "banned":
                cat, sev, conf = "terminology", "warning", 0.95
                why = "This word is on the banned list for the brand."
                src_quote = t["reason"]
            else:
                cat, sev, conf = "terminology", "warning", 0.95
                why = "The approved wording keeps language consistent across channels."
                src_quote = t["reason"]
            msg = f"Replace \"{m.group(0)}\"" + (f" with \"{repl}\"." if repl else " (see source).")
            out.append(dict(rule="tone_word" if kind == "tone" else "terminology", category=cat, severity=sev,
                            message=msg, why=why, source_type="term", source_id=t["id"], source_quote=src_quote,
                            confidence=conf, start=m.start(), end=m.end(),
                            replacement=repl if repl else None,
                            advice=None if repl else "Rephrase without this word."))
    return out


def rule_tone_punctuation(text, brand, ctx):
    out = []
    bangs = [m.start() for m in re.finditer(r"!", text)]
    for pos in bangs[1:]:
        out.append(dict(rule="tone_exclaim", category="tone", severity="warning",
                        message="Extra exclamation mark. Use at most one per piece.",
                        why="Heavy exclamation use reads as hype rather than confident, warm copy.",
                        source_type="guideline", source_key="tone", source_quote=Q["tone"], confidence=0.93,
                        start=pos, end=pos + 1, replacement="."))
    ok_lower = {t["preferred"].lower() for t in brand["terms"] if t["kind"] == "case" and t["preferred"]}
    for m in re.finditer(r"\b[A-Z]{4,}\b", text):
        w = m.group(0)
        if w in CAPS_OK or w.lower() in ok_lower:
            continue
        prev = text[:m.start()].rstrip()
        at_start = (not prev) or prev[-1] in ".!?\n"
        out.append(dict(rule="tone_caps", category="tone", severity="warning",
                        message=f"Avoid all-caps emphasis (\"{w}\").",
                        why="All-caps text reads as shouting and is harder for screen-reader and low-vision users.",
                        source_type="guideline", source_key="caps", source_quote=Q["caps"], confidence=0.9,
                        start=m.start(), end=m.end(), replacement=w.capitalize() if at_start else w.lower()))
    return out


def rule_readability(text, brand, ctx):
    out = []
    for start, end, sent in ctx["sentences"]:
        n = len(sent.split())
        if n > 25:
            out.append(dict(rule="readability", category="readability",
                            severity="warning" if n > 35 else "note",
                            message=f"Long sentence ({n} words). Aim for under 25.",
                            why="Shorter sentences are easier to scan and to translate.",
                            source_type="guideline", source_key="plain", source_quote=Q["plain"],
                            confidence=0.9, start=start, end=end,
                            advice="Split this into two sentences."))
    return out


def rule_promises(text, brand, ctx):
    out = []
    for m in PROMISE_RE.finditer(text):
        out.append(dict(rule="promise", category="claims", severity="blocker",
                        message=f"Prohibited promise: \"{m.group(0)}\".",
                        why="Promising guaranteed or risk-free outcomes creates regulatory and reputational risk.",
                        source_type="guideline", source_key="promise", source_quote=Q["promise"],
                        confidence=0.95, start=m.start(), end=m.end(),
                        advice="Describe what the product does, not what the customer will certainly get."))
    return out


def rule_superlatives(text, brand, ctx):
    out = []
    fact_text = " ".join(f["statement"].lower() for f in brand["facts"] if f["live"])
    for m in SUPERLATIVE_RE.finditer(text):
        if m.group(0).lower() in fact_text:
            continue
        out.append(dict(rule="superlative", category="claims", severity="warning",
                        message=f"Unsupported superlative claim: \"{m.group(0)}\".",
                        why="No approved fact supports this comparison, so it cannot be published as stated.",
                        source_type="guideline", source_key="superlative", source_quote=Q["superlative"],
                        confidence=0.85, start=m.start(), end=m.end(),
                        advice="Remove the comparison, or ask a reviewer to add an approved proof point."))
    return out


def rule_comparisons(text, brand, ctx):
    out = []
    for m in COMPARISON_RE.finditer(text):
        out.append(dict(rule="comparison", category="claims", severity="warning",
                        message=f"Comparative claim: \"{m.group(0)}\".",
                        why="Comparisons with competitors or alternatives need legal sign-off and a proof point.",
                        source_type="guideline", source_key="comparison", source_quote=Q["comparison"],
                        confidence=0.8, start=m.start(), end=m.end(),
                        advice="State what LumaPay offers without comparing, or get legal sign-off first."))
    return out


def rule_figures(text, brand, ctx):
    """Compare figures in each sentence with the closest approved fact (TF-IDF retrieval)."""
    out = []
    index = ctx["fact_index"]
    today = ctx["today"]
    for start, end, sent in ctx["sentences"]:
        nums = extract_numbers(sent)
        if not nums:
            continue
        fact, score = index.match(sent)
        keys = {n[0] for n in nums}

        def span(n):
            return start + n[3], start + n[4]

        if fact is not None and score >= 0.22:
            fnums = {n[0] for n in extract_numbers(fact["statement"])}
            expired = bool(fact.get("valid_until")) and fact["valid_until"] < today
            wrong = [n for n in nums if n[0] not in fnums]
            if fnums and wrong:
                s0, e0 = span(wrong[0])
                shown = ", ".join(sent[n[3]:n[4]] for n in wrong)
                out.append(dict(rule="figure_mismatch", category="facts", severity="blocker",
                                message=f"Figure ({shown}) differs from the approved fact.",
                                why=f"The closest approved fact says: \"{fact['statement']}\"",
                                source_type="fact", source_id=fact["id"], source_quote=fact["statement"],
                                confidence=round(min(0.95, 0.5 + score), 2), start=s0, end=e0,
                                advice="Use the approved figure, or have a reviewer update the Approved Facts library first."))
            elif expired and fnums and keys <= fnums:
                s0, e0 = span(nums[0])
                out.append(dict(rule="figure_stale", category="facts", severity="warning",
                                message="This figure matches an approved fact that has expired.",
                                why=f"The fact was valid until {fact['valid_until']}. Confirm it is still true.",
                                source_type="fact", source_id=fact["id"], source_quote=fact["statement"],
                                confidence=round(min(0.9, 0.5 + score), 2), start=s0, end=e0,
                                advice="Ask the brand owner to refresh this fact before publishing."))
        else:
            significant = [n for n in nums if n[1] or n[2] >= 1000]
            if significant:
                s0, e0 = span(significant[0])
                out.append(dict(rule="figure_unsourced", category="facts", severity="warning",
                                message=f"Figure \"{sent[significant[0][3]:significant[0][4]]}\" has no matching approved fact.",
                                why="Numbers in published content must trace back to the Approved Facts library.",
                                source_type="guideline", source_key="facts", source_quote=Q["facts"],
                                confidence=0.55, start=s0, end=e0,
                                advice="Remove the figure, or add an approved fact that supports it."))
    return out


def rule_legal(text, brand, ctx):
    if LEGAL_TRIGGER_RE.search(text) and "terms apply" not in text.lower():
        end = len(text.rstrip())
        return [dict(rule="disclaimer", category="compliance", severity="warning",
                     message="Mentions rates, returns, cashback, savings or percentages but has no \"Terms apply.\" line.",
                     why="A standard disclaimer is required whenever financial benefits are mentioned.",
                     source_type="guideline", source_key="legal", source_quote=Q["legal"], confidence=0.9,
                     start=end, end=end, replacement="\n\nTerms apply.")]
    return []


def rule_accessibility(text, brand, ctx):
    out = []
    for m in LINK_RE.finditer(text):
        out.append(dict(rule="a11y_link", category="accessibility", severity="warning",
                        message=f"Non-descriptive link text: \"{m.group(0)}\".",
                        why="Screen-reader users often scan a list of links; \"click here\" tells them nothing.",
                        source_type="guideline", source_key="a11y_link", source_quote=Q["a11y_link"],
                        confidence=0.9, start=m.start(), end=m.end(),
                        advice="Name the destination, for example \"View pricing\"."))
    for m in MD_IMG_RE.finditer(text):
        out.append(dict(rule="a11y_image", category="accessibility", severity="warning",
                        message="Image has empty alt text.",
                        why="Without alt text, people using screen readers miss the image's meaning.",
                        source_type="guideline", source_key="a11y_image", source_quote=Q["a11y_image"],
                        confidence=0.95, start=m.start(), end=m.end(),
                        advice="Describe the image inside the square brackets."))
    for n in ctx["notes"]:
        if n.get("type") == "image_no_alt":
            out.append(dict(rule="a11y_image", category="accessibility", severity="warning",
                            message=f"Image {n.get('index', '?')} in the uploaded document has no alt text.",
                            why="Without alt text, people using screen readers miss the image's meaning.",
                            source_type="guideline", source_key="a11y_image", source_quote=Q["a11y_image"],
                            confidence=0.95, start=None, end=None,
                            advice="Add alt text to the image in the original document, then re-upload."))
    return out


RULES = [rule_terminology, rule_tone_punctuation, rule_readability, rule_promises, rule_superlatives, rule_comparisons,
         rule_figures, rule_legal, rule_accessibility]


def build_ctx(text, brand, notes, today=None):
    return {
        "sentences": split_sentences(text),
        "fact_index": FactIndex([f for f in brand["facts"] if f["status"] == "approved"]),
        "today": today or date.today().isoformat(),
        "notes": notes or [],
    }
