"""EchoNest assistant: a Gradio chat over the hand-written LangGraph ReAct agent, with a persona selector.

Each reply shows the agent's steps (Thought, Action, Observation) as collapsible messages above the answer, and the
persona card shows the persona's traits and its settings: intended, and effective on the active model.
The model is chosen in .env (LLM_PROVIDER / LLM_MODEL); nothing here depends on it.

Run from the repo root:  python app.py
"""
import json

import gradio as gr

from echonest_agent import agent, personas
from echonest_agent.config import load_profile

OBSERVATION_PREVIEW = 700   # characters of each Observation shown in the trace


def trace_messages(result):
    """The turn's steps as assistant messages that start collapsed (status "done"); their metadata title keeps
    them out of the model's history (agent.gradio_to_api() skips them)."""
    messages, thought = [], None
    for t in result.trace:
        if t["node"] == "reason":
            thought = t.get("thought")
        elif t["node"] == "act":
            obs = t["observation"]
            obs = obs if len(obs) <= OBSERVATION_PREVIEW else obs[:OBSERVATION_PREVIEW] + " …"
            body = (f"**Thought:** {thought}\n\n" if thought else "") + (
                f"**Action Input:** `{json.dumps(t['args'], ensure_ascii=False)}`\n\n**Observation:**\n```\n{obs}\n```")
            messages.append(gr.ChatMessage(content=body, metadata={"title": f"🔧 {t['tool']}", "status": "done"}))
        elif t["node"] == "recover":
            messages.append(gr.ChatMessage(content=f"The reply broke the format ({t['error']}); a correction was "
                                                   "sent.", metadata={"title": "🛠 Format correction", "status": "done"}))
        elif t["node"] == "give_up":
            messages.append(gr.ChatMessage(content=t["observation"], metadata={"title": "🛑 Gave up: question logged", "status": "done"}))
    if thought and result.outcome == "final":
        messages.append(gr.ChatMessage(content=thought, metadata={"title": "🧠 Thought", "status": "done"}))
    return messages


def chat(message, history, persona_id):
    reply = agent.respond(message, history, persona_id=persona_id)
    if reply.error:
        print(f"❌ {reply.error}")
    steps = trace_messages(reply.result) if reply.result else []
    return [*steps, gr.ChatMessage(content=reply.answer)]


def persona_card(persona_id):
    """Markdown: the persona's focus and traits, and its settings, intended vs effective on the active model."""
    p = personas.PERSONAS[persona_id]
    lines = [f"**{p.name}, {p.role}.** {p.task_focus[0].upper() + p.task_focus[1:]}", ""]
    lines += [f"- **{key.replace('_', ' ').capitalize()}:** {p.traits[key]}" for key in personas.TRAITS]
    lines += ["", "| Setting | Intended | Effective here | Why |", "|---|---|---|---|"]
    rows = {name: (effective, note) for name, _, effective, note in p.card(agent.get_agent().llm)}
    for name, value in p.settings.items():
        effective, note = rows[name]
        why = p.rationale[name].split(": ", 1)[1]
        lines.append(f"| {name} | {value} | {effective}{' (' + note + ')' if note else ''} | {why} |")
    return "\n".join(lines)


PROFILE = load_profile()
CHOICES = [(f"{p.name}, {p.role}", p.id) for p in personas.PERSONAS.values()]

with gr.Blocks(title="EchoNest assistant") as demo:
    persona = gr.Dropdown(CHOICES, value=personas.DEFAULT.id, label="Persona", render=False)
    gr.ChatInterface(
        fn=chat,
        additional_inputs=[persona],
        additional_inputs_accordion=gr.Accordion("Persona", open=True, render=False),
        title="EchoNest memory assistant",
        description="Ask about EchoNest's packages, prices and policies, plan a story, or leave your details. "
                    "Open a 🔧 step to see how the agent looked it up.",
        examples=[["How long does a Legacy Edition take?", "milo"],
                  ["What's the price difference between the Event Story and the Life Timeline?", "nora"],
                  ["Can you help me plan a Memory Capsule for my daughter's graduation?", "sami"]],
        cache_examples=False,
    )
    with gr.Accordion("Persona card: traits and settings", open=False):
        card = gr.Markdown()
    gr.Markdown(f"Model: `{PROFILE.model}` via `{PROFILE.provider}` · ReAct loop written by hand in LangGraph "
                "(no prebuilt agent). Settings the model does not honour are not sent.")
    persona.change(persona_card, persona, card)
    demo.load(persona_card, persona, card)

if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft())
