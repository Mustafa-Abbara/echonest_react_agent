"""Offline tests for the A4 knowledge base and tools (Stage 2): no API key, no LLM calls.

Retrieval is checked against A3's labelled questions (tests/knowledge_checks.json): every documented fact must come
back in the top 3 passages, and every topic the documents never mention must be reported as such.
Logs are written to a temporary folder, never to logs/.
Run from the repo root: python tests/test_tools_a4.py
"""
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from echonest_agent import knowledge, tools  # noqa: E402

CHECKS = json.loads((ROOT / "tests" / "knowledge_checks.json").read_text(encoding="utf-8"))
TMP_LOGS = Path(tempfile.mkdtemp(prefix="echonest_a4_logs_"))
tools.LOGS_DIR = TMP_LOGS


def norm(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def lines(name):
    path = TMP_LOGS / name
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


# ----------------------------------------------------------------------------------------------------
# Documents and search
# ----------------------------------------------------------------------------------------------------
def test_every_document_section_becomes_a_passage():
    passages = knowledge.load_passages()
    pdf_sections = {int(p.section.split(".")[0]) for p in passages
                    if p.source == knowledge.PDF_NAME and p.section[0].isdigit()}
    assert pdf_sections == set(range(1, 18)), sorted(pdf_sections)
    faq = [p for p in passages if "Frequently Asked Questions" in p.section]
    assert len(faq) == 7 and all(p.text.startswith("Q: ") for p in faq)
    assert len([p for p in passages if p.source == knowledge.SUMMARY_NAME]) == 5


def test_documented_facts_are_retrieved_in_top_3():
    index = knowledge.get_index()
    for group in ("pdf_only", "summary_only", "not_offered"):
        for case in CHECKS[group]:
            found, _ = index.search(case["question"])
            assert any(norm(case["phrase"]) in norm(p.text) for p in found), \
                (group, case["question"], [p.section for p in found])


def test_unknown_topics_are_reported_as_unknown():
    for case in CHECKS["unknown"]:
        observation = tools.search_business_docs(case["question"])
        keyword = case["keyword"].split()[0].lower()            # "gift card" -> "gift"
        passages = "\n".join(line for line in observation.splitlines() if line.startswith("["))  # not the header
        assert keyword not in norm(passages), (case, observation)
        assert observation.startswith("NO_MATCH") or keyword in observation.split("NO EchoNest document:")[1], \
            (case, observation)


def test_stemming_and_synonyms():
    assert [knowledge.stem(w) for w in ("photos", "takes", "business", "cards", "stories")] == \
           ["photo", "take", "business", "card", "story"]
    assert "founded" in knowledge.query_terms("How did EchoNest start?")


def test_search_observation_format():
    obs = tools.search_business_docs("How long does the Legacy Edition take?")
    assert obs.startswith("Top 3 passages") and "(about_business.pdf · 10. Project Timeline)" in obs
    assert "3 to 4 weeks" in obs and len(obs) <= tools.MAX_OBSERVATION
    assert max(len(p.text) for p in knowledge.load_passages()) <= tools.PASSAGE_CHARS, "a passage would be cut"
    assert tools.search_business_docs("  ").startswith("ERROR")


# ----------------------------------------------------------------------------------------------------
# Packages: read from the PDF, never typed by hand
# ----------------------------------------------------------------------------------------------------
def test_packages_come_from_the_pdf():
    catalog = knowledge.packages()
    assert list(catalog) == ["Memory Capsule", "Event Story", "Life Timeline", "Legacy Edition", "Corporate Story"]
    assert [catalog[p]["price"] for p in list(catalog)[:4]] == ["$79", "$149", "$299", "$499"]
    corporate = catalog["Corporate Story"]["price"]
    assert "no fixed price" in corporate and "$" not in corporate and "Payment" not in corporate
    pdf = norm(knowledge.pdf_text())
    for facts in catalog.values():
        assert norm(facts["price"]) in pdf and norm(facts["description"]) in pdf


def test_get_package_matching():
    assert tools.get_package("Legacy Edition").startswith("Legacy Edition\nPrice: $499")
    for name, package in (("the legacy one", "Legacy Edition"), ("capsule", "Memory Capsule"),
                          ("LIFE TIMELINE", "Life Timeline"), ("a company history", "Corporate Story")):
        assert tools.get_package(name).startswith(package), name
    for name in ("Platinum Edition", "story", "", "wedding video"):
        assert tools.get_package(name).startswith("ERROR: no EchoNest package"), name
    corporate = tools.get_package("Corporate Story")
    assert "no fixed price" in corporate and not re.search(r"Price: \$\d", corporate)
    assert "3 to 4 weeks" in tools.get_package("Legacy Edition") and "50% deposit" in corporate


# ----------------------------------------------------------------------------------------------------
# Action tools (A3 behaviour, text observations)
# ----------------------------------------------------------------------------------------------------
def test_valid_lead_writes_one_line():
    before = len(lines("leads.jsonl"))
    obs = tools.record_customer_interest(" Sara@Example.com ", "Sara", "Memory Capsule for graduation")
    assert obs.startswith("OK: lead lead_"), obs
    rows = lines("leads.jsonl")
    assert len(rows) == before + 1 and json.loads(rows[-1])["email"] == "sara@example.com"


def test_invalid_lead_saves_nothing():
    before = len(lines("leads.jsonl"))
    for email, name in (("sara-at-example", "Sara"), ("sara@example", "Sara"), ("sara@example.com", " ")):
        assert tools.record_customer_interest(email, name).startswith("ERROR"), (email, name)
    assert len(lines("leads.jsonl")) == before


def test_unicode_lead_and_feedback():
    tools.record_customer_interest("lina@example.com", "لينا فرحات", "ألبوم عائلي")
    assert json.loads(lines("leads.jsonl")[-1])["name"] == "لينا فرحات"
    assert tools.record_feedback("Do you sell gift cards?").startswith("OK: logged as fb_")
    assert json.loads(lines("feedback.jsonl")[-1])["question"] == "Do you sell gift cards?"
    assert tools.record_feedback("").startswith("ERROR")


# ----------------------------------------------------------------------------------------------------
# safe_execute and the prompt descriptions
# ----------------------------------------------------------------------------------------------------
def test_safe_execute_never_raises():
    assert tools.safe_execute("search", {"q": "x"}).startswith("ERROR: unknown tool 'search'")
    assert tools.safe_execute("get_package", "{name: Legacy}").startswith("ERROR: Action Input is not valid JSON")
    assert tools.safe_execute("get_package", '["Legacy"]').startswith("ERROR: Action Input must be a JSON object")
    assert "missing name" in tools.safe_execute("get_package", {})
    assert "unknown text" in tools.safe_execute("record_feedback", {"text": "hi"})
    assert tools.safe_execute("get_package", '{"name": "Legacy"}').startswith("Legacy Edition")
    assert tools.safe_execute(" get_package ", {"name": "capsule"}).startswith("Memory Capsule")

    original = tools.TOOLS["get_package"]
    tools.TOOLS["get_package"] = tools.Tool(**{**original.__dict__, "func": lambda name: 1 / 0})
    try:
        assert tools.safe_execute("get_package", {"name": "x"}).startswith("ERROR: get_package failed (ZeroDivision")
    finally:
        tools.TOOLS["get_package"] = original


def test_tool_descriptions_and_examples():
    text = tools.describe_tools()
    for tool in tools.TOOLS.values():
        assert f"### {tool.name}" in text
        for arg in tool.required:
            assert f"{arg} (required)" in text and arg in tool.example, (tool.name, arg)
        observation = tools.safe_execute(tool.name, tool.example)      # every documented example really works
        assert not observation.startswith("ERROR"), (tool.name, observation)
    assert "message (optional)" in text


def test_use_case_write_up_covers_the_pdf_items():
    doc = (ROOT / "docs" / "use_case.md").read_text(encoding="utf-8")
    for heading in ("## Agent goal", "## Target audience", "## Tools it can use", "## Constraints and limitations"):
        assert heading in doc, heading
    for name in tools.TOOLS:
        assert f"`{name}(" in doc, name


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("PASS", name)
            except AssertionError as e:
                failed += 1
                print("FAIL", name, "-", e)
    print(f"\n(test logs written to {TMP_LOGS}, not to logs/)")
    raise SystemExit(failed)
