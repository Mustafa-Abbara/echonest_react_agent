"""The ReAct loop as a LangGraph state machine, written by hand (PDF 2.2; PDF 1: no prebuilt executors).

    reason ──(route_after_reason)──▶ act ──▶ reason        the model asked for a tool: run it, send the Observation
       │                         ├─▶ recover ──▶ reason    the reply broke the format: send a correction
       │                         ├─▶ finalize ──▶ END      the model gave its Final Answer
       │                         └─▶ give_up ──▶ END       too many steps: apologise and log the question

- reason: one LLM call (system prompt + chat history + this turn's scratchpad), then parse_react() on the reply.
- route_after_reason: the conditional edge that DETECTS whether the model suggested an action.
- act: tools.safe_execute(), then the step and its "Observation: ..." go into the scratchpad.
The scratchpad is sent as ONE assistant turn (every step of this turn, each followed by its Observation) plus a short
"continue" user message: the classic ReAct transcript. Stage 4 live finding: with each Observation in its own user
message after the step, the default model returned empty "malformed response" replies for most lookups.
No prebuilt agent is used: not langgraph.prebuilt (create_react_agent, ToolNode, tools_condition), not LangChain's
AgentExecutor, not a model's native tool calling (bind_tools). Our own code decides every transition.
"""
import json
import operator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from . import personas, prompts, tools
from .llm import LLMSettings, get_llm
from .react_parser import Step, parse_react

MAX_STEPS = 6              # LLM calls per customer message (each is one request against the quota)
MAX_FORMAT_ERRORS = 2      # corrections per turn before giving up (1 was sometimes too few on Flash-Lite: Stage 5)
TRACES_LOG = Path(__file__).resolve().parent.parent / "logs" / "traces.jsonl"
REACT_STOP = ("Observation:",)   # the model must stop after Action Input (Stage 0: every model honours stop)
GIVE_UP_REPLY = ("I'm sorry, I couldn't finish looking that up just now. I've passed your question to the "
                 "EchoNest team, and Lina Farhat's team replies within one business day.")


class AgentState(TypedDict, total=False):
    messages: list            # system prompt + chat history + the customer's message (fixed during the turn)
    user_message: str
    settings: Any             # LLMSettings for this persona
    cot: bool
    scratchpad: Annotated[list, operator.add]   # this turn's steps, each followed by its Observation (text)
    trace: Annotated[list, operator.add]        # one record per node, for printing and logs
    step: int                 # LLM calls made this turn
    max_steps: int
    format_errors: int
    last: Any                 # the parsed Step of the latest reply
    final_answer: str
    outcome: str              # "final" | "format_fallback" | "gave_up"


def step_text(step: Step, cot=True):
    """The assistant's step as it goes back into the scratchpad: rebuilt from the parsed fields, so an invented
    Observation or a second action in the raw reply never reaches the model again."""
    lines = [f"Thought: {step.thought}"] if cot and step.thought else []
    lines += [f"Action: {step.tool}", f"Action Input: {json.dumps(step.args, ensure_ascii=False)}"]
    return "\n".join(lines)


def scratchpad_messages(entries):
    """This turn's steps so far as chat messages: one assistant turn with the whole transcript, then 'continue'."""
    if not entries:
        return []
    return [{"role": "assistant", "content": "\n\n".join(entries)},
            {"role": "user", "content": prompts.CONTINUE_MESSAGE}]


class ReActAgent:
    """Builds and runs the graph. `llm` is anything with complete(messages, settings) -> LLMResult."""

    def __init__(self, llm=None, verbose=True):
        self.llm = llm or get_llm()
        self.verbose = verbose
        self.tool_args = tools.tool_arguments()
        self.graph = self._build()

    # ---------- nodes --------------------------------------------------------------------------------------
    def reason(self, state):
        settings = (state.get("settings") or LLMSettings()).merged(stop=REACT_STOP)
        result = self.llm.complete(state["messages"] + scratchpad_messages(state.get("scratchpad", [])), settings)
        step = parse_react(result.text, tools=self.tool_args)
        n = state.get("step", 0) + 1
        if self.verbose:
            if step.thought:
                print(f"🧠 THOUGHT [{n}]: {step.thought}")
            for w in step.warnings:
                print(f"⚠️  PARSER: {w}")
        record = {"node": "reason", "step": n, "kind": step.kind, "thought": step.thought, "tool": step.tool,
                  "args": step.args, "error": step.error, "warnings": step.warnings, "raw": result.text,
                  "llm": {k: v for k, v in result.as_record().items() if k not in ("text", "thinking")}}
        return {"last": step, "step": n, "trace": [record]}

    def act(self, state):
        step = state["last"]
        observation = tools.safe_execute(step.tool, step.args)
        if self.verbose:
            print(f"🔧 ACTION: {step.tool}({json.dumps(step.args, ensure_ascii=False)})")
            print(f"👁  OBSERVATION: {observation if len(observation) < 400 else observation[:400] + ' …'}")
        return {"scratchpad": [step_text(step, state.get("cot", True)) + "\n" + prompts.observation_message(observation)],
                "trace": [{"node": "act", "tool": step.tool, "args": step.args, "observation": observation}]}

    def recover(self, state):
        step = state["last"]
        raw = step.raw.strip()[:1500]
        problem = step.error if raw else "your reply was empty"
        correction = (f"FORMAT ERROR: {problem}. Reply again with exactly one step, either "
                      "'Action:' + 'Action Input:' (a JSON object), or 'Final Answer:'.")
        if self.verbose:
            print(f"🛠  RECOVER: {problem}")
        # no placeholder text for an empty reply: a model copied "(empty reply)" back as its answer (Stage 8)
        return {"scratchpad": [(raw + "\n" if raw else "") + prompts.observation_message(correction)],
                "format_errors": state.get("format_errors", 0) + 1,
                "trace": [{"node": "recover", "error": step.error}]}

    def finalize(self, state):
        step = state["last"]
        if step.kind == "final":
            answer, outcome = step.answer, "final"
        else:                                    # the model kept answering in plain prose: use the prose
            answer, outcome = step.plain_text, "format_fallback"
        if self.verbose:
            print(f"✅ FINAL ({outcome}): {answer}")
        return {"final_answer": answer, "outcome": outcome, "trace": [{"node": "finalize", "outcome": outcome}]}

    def give_up(self, state):
        observation = tools.safe_execute("record_feedback",
                                         {"question": f"[agent gave up after {state.get('step')} steps] "
                                                      f"{state.get('user_message', '')}"})
        if self.verbose:
            print(f"🛑 GIVE UP after {state.get('step')} steps; {observation}")
        return {"final_answer": GIVE_UP_REPLY, "outcome": "gave_up",
                "trace": [{"node": "give_up", "observation": observation}]}

    # ---------- the conditional edge: action detection ---------------------------------------------------
    @staticmethod
    def route_after_reason(state):
        step = state["last"]
        if step.kind == "final":
            return "finalize"
        if state.get("step", 0) >= state.get("max_steps", MAX_STEPS):
            return "give_up"                     # no budget left for another tool call + answer
        if step.kind == "action":
            return "act"
        if state.get("format_errors", 0) >= 1 and step.error and "no 'Action:' or 'Final Answer:'" in step.error \
                and step.plain_text:
            return "finalize"                    # plain prose again after a correction: it is the answer
        if state.get("format_errors", 0) < MAX_FORMAT_ERRORS:
            return "recover"
        return "give_up"

    def _build(self):
        g = StateGraph(AgentState)
        for name in ("reason", "act", "recover", "finalize", "give_up"):
            g.add_node(name, getattr(self, name))
        g.add_edge(START, "reason")
        g.add_conditional_edges("reason", self.route_after_reason,
                                {"act": "act", "recover": "recover", "finalize": "finalize", "give_up": "give_up"})
        g.add_edge("act", "reason")
        g.add_edge("recover", "reason")
        g.add_edge("finalize", END)
        g.add_edge("give_up", END)
        return g.compile()

    # ---------- one customer message ---------------------------------------------------------------------
    def run(self, user_message, history=(), persona=personas.DEFAULT, instructions=None, settings=None, cot=True,
            max_steps=MAX_STEPS, log=True):
        """Answer one customer message. `history` = earlier turns as [{"role": "user"|"assistant", "content"}]
        (final answers only; this turn's tool steps are not kept). `persona` is a Persona (its settings are used
        unless `settings` is given) or a plain prompt text; `instructions` = None uses the shared block."""
        if isinstance(persona, personas.Persona):
            persona_id, block = persona.id, persona.prompt_block
            settings = settings if settings is not None else persona.llm_settings()
        else:
            persona_id, block = None, persona
        system = prompts.build_system_prompt(block, instructions, cot=cot)
        messages = [{"role": "system", "content": system}, *history, {"role": "user", "content": user_message}]
        if self.verbose:
            print(f"👤 USER: {user_message}")
        state = self.graph.invoke({"messages": messages, "user_message": user_message, "settings": settings,
                                   "cot": cot, "scratchpad": [], "trace": [], "step": 0, "max_steps": max_steps,
                                   "format_errors": 0},
                                  {"recursion_limit": 4 * max_steps + 10})
        state = getattr(state, "value", state)   # LangGraph >= 1.1 may wrap the final state
        result = TurnResult(answer=state["final_answer"], outcome=state["outcome"], steps=state["step"],
                            format_errors=state.get("format_errors", 0), trace=state["trace"], persona=persona_id)
        if log:
            result.save(user_message)
        return result


@dataclass
class TurnResult:
    answer: str
    outcome: str                  # "final" | "format_fallback" | "gave_up"
    steps: int                    # LLM calls this turn
    format_errors: int
    trace: list = field(default_factory=list)
    persona: str | None = None    # persona id, or None for a custom prompt

    @property
    def tool_calls(self):
        return [(t["tool"], t["args"]) for t in self.trace if t["node"] == "act"]

    def save(self, user_message, path=None):
        path = Path(path or TRACES_LOG)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "persona": self.persona,
                  "user": user_message,
                  "answer": self.answer, "outcome": self.outcome, "steps": self.steps,
                  "format_errors": self.format_errors, "trace": self.trace}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
