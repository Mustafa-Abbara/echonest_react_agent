"""Reads one model reply in the ReAct text format and decides what it asks for (PDF 2.2: "logic to detect when
the model suggests an action" and "response parsing to complete the agent's final answer").

The format (prompts.FORMAT_SPEC) is one step per reply:
    Thought: ...                        Thought: ...
    Action: <tool name>          or     Final Answer: <reply to the customer>
    Action Input: <JSON object>
The "Thought:" line is left out when chain-of-thought is switched off. The PDF's own example writes the call on one
line, Action: lookup_location("Paris"), and ends with "Answer:", so both are accepted too.

parse_react() never raises. It returns a Step whose kind is:
    "action"   run step.tool with step.args, then send back "Observation: ..."
    "final"    step.answer is the reply for the customer
    "invalid"  step.error says what is wrong, in words that can be sent back to the model as a correction
"""
import ast
import json
import re
from dataclasses import dataclass, field

KEYWORD_RE = re.compile(
    r"^[ \t>*_#-]*(?:\d+[.)]\s*)?[*_]*(thought|action[ _]?input|action|observation|final[ _]?answer|answer)[*_]*"
    r"\s*[*_]*:[*_]*[ \t]*", re.I | re.M)
CALL_RE = re.compile(r"^\s*`?([A-Za-z_][\w.-]*)`?\s*\((.*)\)\s*$", re.S)   # get_package("Legacy") on one line


@dataclass
class Step:
    kind: str                       # "action" | "final" | "invalid"
    thought: str | None = None
    tool: str | None = None
    args: dict | None = None
    answer: str | None = None
    error: str | None = None
    warnings: list = field(default_factory=list)
    raw: str = ""

    @property
    def plain_text(self):
        """The reply without format keywords, for the fallback when a model ignores the format entirely."""
        return KEYWORD_RE.sub("", self.raw).strip()


INLINE_KEYWORD_RE = re.compile(   # "...info. Action: lookup(...) Observation: ..." (the PDF example, one line)
    r"(?<=[.!?)\"'])[ \t]+(?=(?:Thought|Action Input|Action|Observation|Final Answer|Answer)\s*:)")


def _clean(text):
    """Remove code fences, normalise line endings, and start a new line at each keyword that follows the end of a
    sentence on the same line (case-sensitive, so 'take action: ...' inside an answer is left alone)."""
    text = (text or "").replace("\r\n", "\n")
    text = re.sub(r"^[ \t]*```[\w-]*[ \t]*$", "", text, flags=re.M)
    return INLINE_KEYWORD_RE.sub("\n", text).strip()


def _blocks(text):
    """[(keyword, content)] in order of appearance; keyword normalised to thought/action/action_input/
    observation/final."""
    marks = list(KEYWORD_RE.finditer(text))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        key = re.sub(r"[ _]+", "", m.group(1).lower())          # "Final Answer", "Final_Answer", "FinalAnswer"
        key = {"actioninput": "action_input", "finalanswer": "final", "answer": "final"}.get(key, key)
        out.append((key, text[m.end():end].strip()))
    return out


def normalise_tool_name(name):
    name = re.sub(r"[`'\"*]", "", name or "").strip().rstrip(".:,;")
    name = re.sub(r"^(functions|tools)\.", "", name, flags=re.I)
    return re.sub(r"[\s-]+", "_", name).lower()


def parse_arguments(text, single_arg=None):
    """Action Input → dict. Accepts JSON, a JSON object inside other text, Python-style quotes, key=value pairs,
    and a bare value when the tool has exactly one argument (single_arg). Returns (args or None, error or None)."""
    text = _clean(text).strip()
    if not text:
        return None, "Action Input is empty"
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        value = _first_object(text)
    if value is None:
        try:
            value = ast.literal_eval(text)                        # {'query': 'x'}  or  'x'
        except (ValueError, SyntaxError):
            pairs = re.findall(r"(\w+)\s*=\s*(\"[^\"]*\"|'[^']*'|[^,]+)", text)   # query="x", name='y'
            if pairs and "".join(f"{k}={v}" for k, v in pairs).replace(" ", "") == re.sub(r"[\s,]", "", text):
                value = {k: v.strip().strip("\"'") for k, v in pairs}
            elif text[0] in "{[":                                 # meant as JSON, but broken
                return None, "Action Input is not valid JSON; write a JSON object such as {\"query\": \"...\"}"
            else:
                value = text                                      # a bare value
    if isinstance(value, dict):
        return value, None
    if isinstance(value, (str, int, float)) and single_arg:
        return {single_arg: str(value).strip().strip("\"'")}, None
    return None, "Action Input must be a JSON object such as {\"query\": \"...\"}"


def _first_object(text):
    """The first balanced {...} in the text that parses as JSON (or as a Python dict), else None."""
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            if depth == 0:
                chunk = text[start:i + 1]
                for loader in (json.loads, ast.literal_eval):
                    try:
                        value = loader(chunk)
                        if isinstance(value, dict):
                            return value
                    except (ValueError, SyntaxError):
                        pass
                break
        start = text.find("{", start + 1)
    return None


def parse_react(text, tools=None):
    """Parse one reply. `tools` maps known tool names to their argument names in order (first = the one a bare
    value fills), e.g. {"get_package": ["name"]}; unknown tool names are then reported as invalid."""
    raw = text or ""
    text = _clean(raw)
    warnings = []

    # 1. The model must stop after Action Input. Anything from a self-written "Observation:" on is invented.
    blocks = _blocks(text)
    for i, (key, _) in enumerate(blocks):
        if key == "observation":
            warnings.append("the reply contained its own 'Observation:'; everything from there was ignored")
            blocks = blocks[:i]
            break

    thought = next((c for k, c in blocks if k == "thought"), None)
    actions = [(i, c) for i, (k, c) in enumerate(blocks) if k == "action"]
    finals = [c for k, c in blocks if k == "final"]

    if not blocks:
        return Step("invalid", error="the reply has no 'Action:' or 'Final Answer:' line", raw=raw,
                    warnings=warnings)

    # 2. An action wins over a final answer: its observation is needed before the reply is final.
    if actions:
        index, action_text = actions[0]
        if len(actions) > 1:
            warnings.append("the reply asked for several actions; only the first one is run")
        if finals:
            warnings.append("the reply contained both an Action and a Final Answer; the Action runs first")
        first_line, _, rest = action_text.partition("\n")
        input_text = next((c for k, c in blocks[index + 1:index + 2] if k == "action_input"), None)
        same_line = re.split(r"\s*action[ _]input\s*:\s*", first_line, maxsplit=1, flags=re.I)
        if len(same_line) == 2:                                   # Action: tool Action Input: {...} on one line
            first_line, input_text = same_line[0], same_line[1] + ("\n" + rest if rest else "")
        call = CALL_RE.match(first_line)
        if call:                                                  # Action: get_package("Legacy Edition")
            tool, input_text = call.group(1), call.group(2)
        else:
            tool = first_line
            if input_text is None and rest.strip():               # Action Input written without its keyword
                input_text = rest
        tool = normalise_tool_name(tool)
        if not tool:
            return Step("invalid", thought=thought, error="'Action:' has no tool name", raw=raw, warnings=warnings)
        if tools is not None and tool not in tools:
            return Step("invalid", thought=thought, tool=tool, raw=raw, warnings=warnings,
                        error=f"unknown tool {tool!r}; use one of: {', '.join(tools)}")
        if input_text is None:
            return Step("invalid", thought=thought, tool=tool, raw=raw, warnings=warnings,
                        error=f"'Action: {tool}' must be followed by an 'Action Input:' line with a JSON object")
        arg_names = (tools or {}).get(tool) or []
        args, error = parse_arguments(input_text, single_arg=arg_names[0] if len(arg_names) == 1 else None)
        if error:
            return Step("invalid", thought=thought, tool=tool, raw=raw, warnings=warnings, error=error)
        return Step("action", thought=thought, tool=tool, args=args, raw=raw, warnings=warnings)

    # 3. A final answer: everything after the keyword, all lines kept.
    if finals:
        answer = finals[0].strip()
        if not answer:
            return Step("invalid", thought=thought, error="'Final Answer:' is empty", raw=raw, warnings=warnings)
        return Step("final", thought=thought, answer=answer, raw=raw, warnings=warnings)

    if any(k == "action_input" for k, _ in blocks):
        return Step("invalid", thought=thought, raw=raw, warnings=warnings,
                    error="'Action Input:' without an 'Action:' line naming the tool")
    return Step("invalid", thought=thought, raw=raw, warnings=warnings,
                error="the reply has a Thought but no 'Action:' or 'Final Answer:'")
