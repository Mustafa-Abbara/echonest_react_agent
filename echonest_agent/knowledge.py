"""EchoNest's business documents as searchable passages (the agent's only source of business facts).

The documents are NOT pasted into the system prompt (as they were in A3): the agent has to look facts up with the
search_business_docs / get_package tools, so the ReAct loop really reasons and acts (PDF 2.2).

Passages: one per numbered section of me/about_business.pdf (the FAQ split into one passage per question), one per
paragraph of me/business_summary.txt. Search is BM25 keyword ranking with light stemming: no extra dependency, and
every result can be traced to a document section.
"""
import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ME_DIR = ROOT / "me"
PDF_NAME, SUMMARY_NAME = "about_business.pdf", "business_summary.txt"

STOPWORDS = set("""a an the and or but if then than so of to in on at by for from with without into about as is are
was were be been being am do does did done have has had having i me my we our us you your he she it its they them their
this that these those there here what which who whom whose when where why how can could would should will shall may
might must not no yes any some all each every more most other such only own same too very just also please tell know
want like get got give let much s t""".split())


@dataclass(frozen=True)
class Passage:
    source: str        # file name
    section: str       # e.g. "10. Project Timeline" or "paragraph 3"
    text: str

    @property
    def label(self):
        return f"{self.source} · {self.section}"


def clean_text(text):
    """Normalise line endings and spaces; at most one blank line (same rules as A3)."""
    text = text.replace("\r\n", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def pdf_text(me_dir=ME_DIR):
    from pypdf import PdfReader
    reader = PdfReader(Path(me_dir) / PDF_NAME)
    return clean_text("\n\n".join((page.extract_text() or "") for page in reader.pages))


SECTION_RE = re.compile(r"^(\d{1,2})\. ([A-Z][^\n]{2,60})$", re.M)


def pdf_passages(text):
    """One passage per numbered section; the FAQ section becomes one passage per question."""
    heads = list(SECTION_RE.finditer(text))
    passages = [Passage(PDF_NAME, "title", clean_text(text[:heads[0].start()]))] if heads else []
    for i, head in enumerate(heads):
        body = clean_text(text[head.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)])
        title = f"{head.group(1)}. {head.group(2).strip()}"
        if "Frequently Asked Questions" in title:
            for j, qa in enumerate(re.split(r"\n(?=Q: )", body), 1):
                passages.append(Passage(PDF_NAME, f"{title}, Q{j}", qa.strip()))
        else:
            passages.append(Passage(PDF_NAME, title, body))
    return passages


def summary_passages(text):
    return [Passage(SUMMARY_NAME, f"paragraph {i}", p.strip())
            for i, p in enumerate(clean_text(text).split("\n\n"), 1) if p.strip()]


@lru_cache(maxsize=4)
def load_passages(me_dir=ME_DIR):
    me_dir = Path(me_dir)
    for name in (PDF_NAME, SUMMARY_NAME):
        if not (me_dir / name).exists():
            raise FileNotFoundError(f"{me_dir / name} not found. Run from the repo root.")
    return tuple(pdf_passages(pdf_text(me_dir)) +
                 summary_passages((me_dir / SUMMARY_NAME).read_text(encoding="utf-8")))


# ----------------------------------------------------------------------------------------------------
# Search
# ----------------------------------------------------------------------------------------------------
def stem(word):
    """Tiny stemmer: plural/verb -s (photos→photo, takes→take, cards→card); keeps -ss (business)."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def terms(text):
    return [stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS and len(w) > 1]


# Query words the documents express differently (irregular forms and the docs' own wording). Kept small on purpose:
# each entry fixed a labelled question that keyword search alone missed (tests/test_tools_a4.py).
SYNONYMS = {"lead": ["led"], "start": ["founded"], "began": ["founded"], "begin": ["founded"],
            "cost": ["price"], "pay": ["payment", "deposit"]}


def query_terms(query):
    q = terms(query)
    return list(dict.fromkeys(q + [s for t in q for s in SYNONYMS.get(t, [])]))


class Index:
    """BM25 over the passages (k1=1.5, b=0.75). Each passage is indexed with its section title."""

    def __init__(self, passages):
        self.passages = list(passages)
        self.docs = [Counter(terms(f"{p.section} {p.text}")) for p in self.passages]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.lengths) / len(self.lengths)
        df = Counter(t for d in self.docs for t in d)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query_terms, k1=1.5, b=0.75):
        out = []
        for doc, length in zip(self.docs, self.lengths):
            s = 0.0
            for t in query_terms:
                if t in doc:
                    tf = doc[t]
                    s += self.idf[t] * tf * (k1 + 1) / (tf + k1 * (1 - b + b * length / self.avg))
            out.append(s)
        return out

    def search(self, query, k=3):
        """Returns (passages ranked best first, query words found in no document)."""
        q = query_terms(query)
        missing = [t for t in dict.fromkeys(terms(query)) if t not in self.idf and
                   not any(s in self.idf for s in SYNONYMS.get(t, []))]
        scores = self.scores(q)
        ranked = sorted((i for i, s in enumerate(scores) if s > 0), key=lambda i: -scores[i])
        return [self.passages[i] for i in ranked[:k]], missing


@lru_cache(maxsize=4)
def get_index(me_dir=ME_DIR):
    return Index(load_passages(me_dir))


# ----------------------------------------------------------------------------------------------------
# Packages (structured view of the same documents: nothing here is typed by hand)
# ----------------------------------------------------------------------------------------------------
def section(title_start, me_dir=ME_DIR):
    """The text of the PDF section whose title starts with `title_start` (e.g. '5. Pricing')."""
    for p in load_passages(me_dir):
        if p.source == PDF_NAME and p.section.startswith(title_start):
            return p.text
    raise KeyError(title_start)


def bullets(text):
    """'- Name: details' bullets (wrapped lines joined) → {name: details}. A bullet ends at the next bullet or at a
    non-bullet 'Label: ...' line such as 'Payment: ...'."""
    items = re.findall(r"^-\s+([^:\n]+):\s*(.+?)(?=\n-\s|\n[A-Z][\w ]{0,30}:|\Z)", text, re.M | re.S)
    return {name.strip(): re.sub(r"\s*\n\s*", " ", details).strip() for name, details in items}


@lru_cache(maxsize=4)
def packages(me_dir=ME_DIR):
    """{package name: {"price", "description"}} read from the PDF's Pricing and Services sections."""
    prices = bullets(section("5. Pricing", me_dir))
    services = bullets(section("4. Services", me_dir))
    return {name: {"price": price, "description": services.get(name, "")} for name, price in prices.items()}


def payment_terms(me_dir=ME_DIR):
    m = re.search(r"^Payment:\s*(.+)$", section("5. Pricing", me_dir), re.M | re.S)
    return re.sub(r"\s*\n\s*", " ", m.group(1)).strip() if m else ""


def project_timeline(me_dir=ME_DIR):
    return re.sub(r"\s*\n\s*", " ", section("10. Project Timeline", me_dir)).strip()
