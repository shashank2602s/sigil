"""Sentence splitting, number extraction and TF-IDF matching of sentences to approved facts."""
import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

SENT_RE = re.compile(r".+?(?:[.!?]+(?=\s|$)|\n|$)", re.S)
NUM_RE = re.compile(
    r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)"
    r"(?:\s*(%|percent\b|million\b|mn\b|crore\b|cr\b|lakh\b|billion\b|bn\b|thousand\b|k\b|m\b))?",
    re.I,
)
MULT = {"million": 1e6, "mn": 1e6, "m": 1e6, "crore": 1e7, "cr": 1e7, "lakh": 1e5,
        "billion": 1e9, "bn": 1e9, "thousand": 1e3, "k": 1e3}


def split_sentences(text):
    """Yield (start, end, sentence) with offsets into text."""
    out = []
    for m in SENT_RE.finditer(text):
        seg = m.group(0)
        stripped = seg.strip()
        if not stripped:
            continue
        start = m.start() + (len(seg) - len(seg.lstrip()))
        out.append((start, start + len(stripped), stripped))
    return out


def extract_numbers(text):
    """Return a list of (normalised_key, has_unit, value, start, end) for figures in text."""
    found = []
    for m in NUM_RE.finditer(text):
        raw, unit = m.group(1), (m.group(2) or "").lower()
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        if not unit and float(value).is_integer() and 1900 <= value <= 2100:
            continue  # looks like a year
        if unit in ("%", "percent"):
            key = f"{value:g}%"
        else:
            value *= MULT.get(unit, 1)
            key = f"{value:g}"
        found.append((key, bool(unit), value, m.start(), m.end()))
    return found


class FactIndex:
    """TF-IDF index over approved facts. Everything runs locally."""

    def __init__(self, facts):
        self.facts = facts
        self.vec = None
        self.matrix = None
        if facts:
            self.vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
            self.matrix = self.vec.fit_transform([f["statement"] for f in facts])

    def match(self, sentence):
        """Return (fact, score) for the closest approved fact, or (None, 0.0)."""
        if self.vec is None:
            return None, 0.0
        try:
            q = self.vec.transform([sentence])
        except Exception:
            return None, 0.0
        if q.nnz == 0:
            return None, 0.0
        sims = cosine_similarity(q, self.matrix)[0]
        i = int(sims.argmax())
        return self.facts[i], float(sims[i])
