"""Seeded-error evaluation. Run: python tests/eval.py  (writes tests/EVAL_RESULTS.md)"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from sigil import db, seed  # noqa: E402
from sigil.engine import load_brand, review  # noqa: E402


def run():
    conn = db.connect(":memory:")
    db.init_db(conn)
    seed.seed(conn)
    brand = load_brand(conn, 1)
    corpus = os.path.join(ROOT, "tests", "corpus")
    expected = json.load(open(os.path.join(corpus, "expected.json")))
    rows, planted, caught, clean_docs, clean_fp, extra = [], 0, 0, 0, 0, 0
    for name, exp in expected.items():
        text = open(os.path.join(corpus, name + ".txt")).read().strip()
        findings, dropped = review(text, brand, "")
        got = {f["rule"] for f in findings}
        hit = [r for r in exp if r in got]
        planted += len(exp)
        caught += len(hit)
        unexpected = sorted(got - set(exp))
        if exp:
            extra += len(unexpected)
        else:
            clean_docs += 1
            clean_fp += int(bool([f for f in findings if f["severity"] in ("blocker", "warning")]))
        rows.append((name, exp, sorted(got), unexpected))
    return rows, planted, caught, clean_docs, clean_fp, extra


if __name__ == "__main__":
    rows, planted, caught, clean_docs, clean_fp, extra = run()
    lines = ["# Seeded-error evaluation", "",
             f"- Documents: {len(rows)} ({len(rows) - clean_docs} with planted issues, {clean_docs} clean)",
             f"- Planted issues caught: **{caught}/{planted}** ({100 * caught // planted}%)",
             f"- Clean documents flagged (false positives): **{clean_fp}/{clean_docs}**",
             f"- Extra, unplanned findings on issue documents: {extra}", "",
             "| Document | Expected | Found | Unplanned |", "|---|---|---|---|"]
    for name, exp, got, un in rows:
        lines.append(f"| {name} | {', '.join(exp) or '(clean)'} | {', '.join(got) or '-'} | {', '.join(un) or '-'} |")
    lines += ["", "Small hand-written test set for regression checking. It is not a measure of accuracy on real brand content."]
    out = "\n".join(lines)
    open(os.path.join(ROOT, "tests", "EVAL_RESULTS.md"), "w").write(out + "\n")
    print(out)
