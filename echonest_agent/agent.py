"""The orchestrator: one customer message in, one reply out (Stage 6; PDF 1: "a working assistant").

respond() turns the chat history into plain messages (final answers only: the trace shown in the UI is never sent
back to the model), runs the ReAct graph with the chosen persona, and returns the reply together with the turn's
trace. LLM errors become a friendly sentence instead of a traceback.
"""
from dataclasses import dataclass

from . import graph, personas
from .llm import LLMError, QuotaExhausted

MAX_HISTORY_MESSAGES = 20   # the last 10 exchanges
EMPTY_MESSAGE_REPLY = "I'm here whenever you're ready. What story would you like to tell?"
FRIENDLY_ERRORS = {
    "quota": "I've reached my message limit for today, so I can't reply right now. Please try again later.",
    "busy": "Our system is a little busy at the moment. Could you try again in a minute?",
    "other": "Sorry, something went wrong on my side. Could you try that again?",
}

_agent = None


def get_agent():
    """One ReActAgent per process (it holds the LLM client and its request pacing)."""
    global _agent
    if _agent is None:
        _agent = graph.ReActAgent(verbose=False)
    return _agent


def _text_of(content):
    """Text from any Gradio content shape: str, a list of blocks/strings, or a file/component dict."""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        content = [content]
    if not isinstance(content, (list, tuple)):
        return ""  # e.g. a gradio Component
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text") or "")
    return "\n".join(p for p in parts if p)


def gradio_to_api(history):
    """Gradio chat history -> [{"role": "user"|"assistant", "content": str}, ...], final answers only.
    Trace messages (an assistant message with a metadata title, shown collapsed in the UI) are skipped."""
    messages = []
    for item in history or []:
        if isinstance(item, (list, tuple)) and len(item) == 2:  # Gradio 4 [user, bot] pairs
            pairs = [("user", item[0]), ("assistant", item[1])]
        elif isinstance(item, dict):
            if (item.get("metadata") or {}).get("title"):
                continue
            pairs = [(item.get("role"), item.get("content"))]
        else:
            continue
        for role, content in pairs:
            text = _text_of(content).strip()
            if role in ("user", "assistant") and text:
                messages.append({"role": role, "content": text})
    return messages


@dataclass
class Reply:
    answer: str
    persona: str
    result: graph.TurnResult | None = None   # None when no turn ran (empty message or an LLM error)
    error: str | None = None


def respond(message, history=(), persona_id=personas.DEFAULT.id, cot=True, agent=None):
    """Answer one customer message as `persona_id`. `history` may be Gradio's history or plain messages."""
    persona = personas.PERSONAS.get(persona_id, personas.DEFAULT)
    if isinstance(message, dict):            # multimodal textbox: {"text": ..., "files": [...]}
        message = message.get("text", "")
    message = str(message or "").strip()
    if not message:
        return Reply(EMPTY_MESSAGE_REPLY, persona.id)
    past = gradio_to_api(history)[-MAX_HISTORY_MESSAGES:]
    try:
        result = (agent or get_agent()).run(message, history=past, persona=persona, cot=cot)
    except QuotaExhausted as e:
        return Reply(FRIENDLY_ERRORS["quota"], persona.id, error=str(e))
    except LLMError as e:
        busy = "temporarily unavailable" in str(e) or "Rate limit" in str(e)
        return Reply(FRIENDLY_ERRORS["busy" if busy else "other"], persona.id, error=str(e))
    except Exception as e:                   # never show a traceback to a customer
        return Reply(FRIENDLY_ERRORS["other"], persona.id, error=f"{type(e).__name__}: {e}")
    return Reply(result.answer, persona.id, result=result)
