"""The system prompt: persona + instructions + tool descriptions + the ReAct response format (PDF 2.2: "a system
prompt defining agent behavior and available tools", "tool descriptions embedded in the system prompt").

The response format comes in two variants for the chain-of-thought experiment (PDF 2.3): with a "Thought:" line
before every Action / Final Answer, and without it. react_parser.parse_react() reads both.
The persona and instructions blocks are written in Stage 5; this module only assembles them.
"""
from . import tools

FORMAT_WITH_COT = """## Response format
Every reply is ONE step, written in exactly one of these two forms, and nothing else.

To use a tool:
Thought: <one or two sentences: what you know so far and what you need next>
Action: <the name of one tool from the list above>
Action Input: <a JSON object with that tool's inputs>

Then stop. The system runs the tool and sends you its result in a message that starts with "Observation:".
Never write an Observation yourself.

To reply to the customer:
Thought: <one or two sentences: why you can answer now>
Final Answer: <your reply to the customer>"""

FORMAT_WITHOUT_COT = """## Response format
Every reply is ONE step, written in exactly one of these two forms, and nothing else. Do not write any "Thought:"
line or other reasoning: go straight to the Action or the Final Answer.

To use a tool:
Action: <the name of one tool from the list above>
Action Input: <a JSON object with that tool's inputs>

Then stop. The system runs the tool and sends you its result in a message that starts with "Observation:".
Never write an Observation yourself.

To reply to the customer:
Final Answer: <your reply to the customer>"""


def format_spec(cot=True):
    return FORMAT_WITH_COT if cot else FORMAT_WITHOUT_COT


def observation_message(observation):
    """How a tool result goes back to the model: a user-role message, because the text protocol has no tool role."""
    return f"Observation: {observation}"


def build_system_prompt(persona, instructions, cot=True, tool_names=None):
    """Persona, then instructions, then the tools, then the response format (each a labelled section)."""
    parts = ["# Persona", persona.strip(),
             "# Instructions", instructions.strip(),
             "# Tools\nYou can use these tools. Each one returns an Observation.", tools.describe_tools(tool_names),
             format_spec(cot)]
    return "\n\n".join(p for p in parts if p)
