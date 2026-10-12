"""The agent's tools (PDF 2.1 "tools it can use", 2.2 "tool descriptions embedded in the system prompt").

Every tool takes keyword arguments and returns a short TEXT observation, because in ReAct the observation is text
the model reads before its next Thought. Errors are observations too ("ERROR: ..."), so the model can recover.
`describe_tools()` renders the registry as the tool section of the system prompt; `safe_execute()` runs a tool the
model asked for and never raises.
"""
import json
import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import knowledge

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"    # tests point this at a temporary folder
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")         # an @, then a dot after it, no spaces
MAX_OBSERVATION = 3400                                        # characters; keeps the scratchpad small
PASSAGE_CHARS = 1000                                          # above the longest passage (918): none is cut today
_log_lock = threading.Lock()                                  # Gradio can serve several chats at once


def _append_jsonl(name, record):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with _log_lock, open(LOGS_DIR / name, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ----------------------------------------------------------------------------------------------------
# Knowledge tools
# ----------------------------------------------------------------------------------------------------
def search_business_docs(query):
    """Search EchoNest's documents; return the best passages and the query words no document mentions."""
    query = str(query or "").strip()
    if not query:
        return "ERROR: empty query. Pass a few keywords, e.g. {\"query\": \"Legacy Edition delivery time\"}."
    found, missing = knowledge.get_index().search(query, k=3)
    if not found:
        return f"NO_MATCH: nothing in the EchoNest documents matches {query!r}."
    lines = [f"Top {len(found)} passages for {query!r}:"]
    for i, p in enumerate(found, 1):
        text = re.sub(r"\s*\n\s*", " ", p.text)
        lines.append(f"[{i}] ({p.label}) {text[:PASSAGE_CHARS]}{'…' if len(text) > PASSAGE_CHARS else ''}")
    if missing:
        lines.append("Words that appear in NO EchoNest document: " + ", ".join(missing) + ".")
    return "\n".join(lines)


PACKAGE_WORDS = {   # distinctive words that identify each package ("story"/"edition" alone are ambiguous)
    "Memory Capsule": {"capsule"}, "Event Story": {"event"}, "Life Timeline": {"life", "timeline"},
    "Legacy Edition": {"legacy"}, "Corporate Story": {"corporate", "company"},
}


def match_package(name):
    """The package a free-text name refers to, or None ('the legacy one' → Legacy Edition)."""
    catalog = knowledge.packages()
    words = set(knowledge.terms(str(name or "")))
    exact = [p for p in catalog if p.lower() == str(name or "").strip().lower()]
    if exact:
        return exact[0]
    hits = [p for p in catalog if words & {knowledge.stem(w) for w in PACKAGE_WORDS.get(p, set())}]
    return hits[0] if len(hits) == 1 else None


def get_package(name):
    """Exact facts for one package: price, what it includes, payment terms and timeline."""
    catalog = knowledge.packages()
    package = match_package(name)
    if package is None:
        return (f"ERROR: no EchoNest package matches {str(name)!r}. Packages: {', '.join(catalog)}. "
                "If the customer asked about something else, use search_business_docs.")
    facts = catalog[package]
    return (f"{package}\n"
            f"Price: {facts['price']}\n"
            f"Includes: {facts['description']}\n"
            f"Payment: {knowledge.payment_terms()}\n"
            f"Timeline: {knowledge.project_timeline()}\n"
            "(Source: about_business.pdf, sections 4, 5 and 10.)")


# ----------------------------------------------------------------------------------------------------
# Action tools (from A3)
# ----------------------------------------------------------------------------------------------------
def record_customer_interest(email, name, message=""):
    """Save a lead to logs/leads.jsonl so the EchoNest team can follow up."""
    email = str(email or "").strip().lower()
    name = str(name or "").strip()
    message = str(message or "").strip()
    if not EMAIL_RE.match(email):
        return f"ERROR: {email!r} is not a valid email address. Nothing was saved; ask the customer for it again."
    if not name:
        return "ERROR: the customer's name is missing. Nothing was saved; ask for their name."
    lead_id = "lead_" + uuid.uuid4().hex[:8]
    _append_jsonl("leads.jsonl", {"timestamp": _now(), "lead_id": lead_id, "email": email, "name": name,
                                  "message": message})
    print(f"📥 LEAD LOGGED: {name} <{email}> | {message or '(no message)'} | {lead_id}")
    return f"OK: lead {lead_id} saved for {name} <{email}>. Lina Farhat's team replies within one business day."


def record_feedback(question):
    """Log an unanswered question, a request for a service EchoNest doesn't offer, or customer feedback."""
    question = str(question or "").strip()
    if not question:
        return "ERROR: empty text. Pass the customer's exact question or feedback."
    feedback_id = "fb_" + uuid.uuid4().hex[:8]
    _append_jsonl("feedback.jsonl", {"timestamp": _now(), "feedback_id": feedback_id, "question": question})
    print(f"📝 FEEDBACK LOGGED: {question} | {feedback_id}")
    return f"OK: logged as {feedback_id}. The EchoNest team will see it."


# ----------------------------------------------------------------------------------------------------
# Registry and prompt descriptions
# ----------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Tool:
    name: str
    func: callable
    purpose: str
    when: str
    inputs: dict            # argument -> description
    required: tuple
    output: str
    example: dict = field(default_factory=dict)


TOOLS = {t.name: t for t in [
    Tool("search_business_docs", search_business_docs,
         purpose="Search EchoNest's business documents (services, prices, policies, team, materials, FAQ).",
         when="Before stating any fact about EchoNest that you have not seen in an Observation in this chat.",
         inputs={"query": "a few keywords about what the customer asked"}, required=("query",),
         output="Up to 3 passages with their source, then the query words that appear in NO document. "
                "NO_MATCH if nothing matches.",
         example={"query": "Legacy Edition delivery time"}),
    Tool("get_package", get_package,
         purpose="Exact price, contents, payment terms and timeline of one EchoNest package.",
         when="When the customer asks about a specific package: Memory Capsule, Event Story, Life Timeline, "
              "Legacy Edition or Corporate Story.",
         inputs={"name": "the package name"}, required=("name",),
         output="The package's facts, or ERROR listing the valid package names.",
         example={"name": "Event Story"}),
    Tool("record_customer_interest", record_customer_interest,
         purpose="Save a potential customer so the EchoNest team can contact them.",
         when="Only after the customer has given their name and a valid email address.",
         inputs={"email": "the customer's email address", "name": "the customer's name",
                 "message": "one line about the project they want"}, required=("email", "name"),
         output="OK with a lead id, or ERROR (e.g. invalid email) and nothing is saved.",
         example={"email": "sara@example.com", "name": "Sara", "message": "Memory Capsule for her graduation"}),
    Tool("record_feedback", record_feedback,
         purpose="Log something the team must see: a question the documents don't answer, a request for a "
                 "service EchoNest doesn't offer, or feedback (complaint or praise).",
         when="When a search shows the documents don't answer the customer's question about EchoNest, when they "
              "ask for a service EchoNest doesn't offer, or when they give feedback.",
         inputs={"question": "the customer's exact question or feedback"}, required=("question",),
         output="OK with a feedback id.",
         example={"question": "Do you sell gift cards?"}),
]}


def describe_tools(names=None):
    """The tool section of the system prompt: one block per tool, with inputs, output and an example call."""
    blocks = []
    for tool in (TOOLS[n] for n in (names or TOOLS)):
        inputs = "; ".join(f"{arg} ({'required' if arg in tool.required else 'optional'}): {desc}"
                           for arg, desc in tool.inputs.items())
        blocks.append(f"### {tool.name}\n"
                      f"- Purpose: {tool.purpose}\n"
                      f"- Use it: {tool.when}\n"
                      f"- Input (a JSON object): {inputs}\n"
                      f"- Output: {tool.output}\n"
                      f"- Example: Action: {tool.name} / Action Input: {json.dumps(tool.example, ensure_ascii=False)}")
    return "\n\n".join(blocks)


def safe_execute(name, args):
    """Run the tool the model asked for. Returns the observation text; never raises.
    `args` may be a dict or a JSON string (as parsed from the model's Action Input)."""
    tool = TOOLS.get(str(name or "").strip())
    if tool is None:
        return f"ERROR: unknown tool {name!r}. Available tools: {', '.join(TOOLS)}."
    if isinstance(args, str):
        try:
            args = json.loads(args) if args.strip() else {}
        except json.JSONDecodeError as e:
            return f"ERROR: Action Input is not valid JSON ({e.msg}). Example: {json.dumps(tool.example)}"
    if not isinstance(args, dict):
        return f"ERROR: Action Input must be a JSON object, e.g. {json.dumps(tool.example)}"
    missing = [a for a in tool.required if a not in args]
    unknown = [a for a in args if a not in tool.inputs]
    if missing or unknown:
        problems = ([f"missing {', '.join(missing)}"] if missing else []) + \
                   ([f"unknown {', '.join(unknown)}"] if unknown else [])
        return f"ERROR: wrong arguments for {tool.name} ({'; '.join(problems)}). Example: {json.dumps(tool.example)}"
    try:
        observation = str(tool.func(**args))
    except Exception as e:   # a tool bug must not crash the agent: report it as an observation
        return f"ERROR: {tool.name} failed ({type(e).__name__}: {e})."
    return observation if len(observation) <= MAX_OBSERVATION else observation[:MAX_OBSERVATION] + " …(truncated)"
