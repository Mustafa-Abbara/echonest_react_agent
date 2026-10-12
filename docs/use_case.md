# Use case: the EchoNest ReAct agent

Assignment C4 lets us reuse the previous assignment's scenario (PDF §2.1), so the agent still works for **EchoNest**,
a fictional digital-memory studio. EchoNest turns people's photos, voice recordings and written memories into a
private, shareable story page. It sells five packages: Memory Capsule $79, Event Story $149, Life Timeline $299,
Legacy Edition $499, and Corporate Story, which has no fixed price. What's new is **how** the agent works: it now
**reasons and acts in a ReAct loop**. It has no business facts in its prompt, so it has to look them up with tools.

## Agent goal

Help a website visitor understand EchoNest's services and choose one, with every fact taken from EchoNest's own
documents. Then, depending on the conversation:
- capture the visitor as a **lead** once they want a project;
- **log** what the documents can't answer (or a service EchoNest doesn't offer), so the team sees the demand;
- **log feedback** (complaints, praise).

Three personas share this goal but have **different tasks**, as PDF §2.3 asks. They are designed in Stage 5 of the
roadmap:

| Persona | Task |
|---|---|
| Milo, the Warm Concierge | first contact, general questions, turning interest into a lead |
| Nora, the Package Specialist | exact prices, package comparisons, payment and policy details |
| Sami, the Story Planner | helping the customer plan their story (which memories, what structure) within a package's limits |

## Target audience

- **Families:** family histories, anniversaries, birthdays and reunions.
- **Individuals:** graduations, relationships, travels and personal milestones.
- **Organisations:** founder stories, company milestones and employee anniversaries.

They are website visitors with no technical background, writing in English, Arabic or French. The documents
themselves are in English.

## Tools it can use

Defined in [`echonest_agent/tools.py`](../echonest_agent/tools.py). Their descriptions are generated from the same
registry into the system prompt. Every tool returns a short text **observation**.

| Tool | What it does | Typical trigger |
|---|---|---|
| `search_business_docs(query)` | Keyword (BM25) search over the business PDF and summary: up to 3 passages with their source section, plus the query words that appear in **no** document | any factual question about EchoNest |
| `get_package(name)` | The exact price, contents, payment terms and timeline of one package, read from the PDF (nothing typed by hand) | "How much is the Legacy Edition?", "What does a Memory Capsule include?" |
| `record_customer_interest(email, name, message)` | Saves a lead to `logs/leads.jsonl` (an invalid email is refused, and nothing is saved) | the customer wants a project and has given a name and email |
| `record_feedback(question)` | Saves an unanswered question, a request for a service EchoNest doesn't offer, or feedback, to `logs/feedback.jsonl` | a search shows no answer; "Can you film our wedding?"; "The upload link is broken" |

## Constraints and limitations

**Rules the agent must follow:**
- **Grounded answers only.** Facts about EchoNest come from tool observations. The agent never invents prices,
  dates, people, discounts or policies. The Corporate Story has no fixed price, so the agent never gives a number.
- **What's missing is logged, not guessed.** The documents deliberately leave things out: gift cards, discounts,
  albums, rush orders, a "Platinum" tier. These must go to `record_feedback`. So must the four services EchoNest
  explicitly doesn't offer: film restoration, physical photo restoration, videography, recovery of deleted files.
- **No transactions.** The agent can't book, take payments or accept files; materials go through a secure upload
  link after booking. It only collects a name, an email and a one-line project description.
- **Leads need a valid email**, and the agent must never claim it saved something unless a tool call did.

**Technical limitations:**
- **Keyword search,** not semantic search. A question phrased very differently from the documents may need a second
  search with other words. The observation lists the words that matched nothing, to help the agent decide.
- **Free-tier LLMs.** Gemini 3.5 Flash-Lite allows 500 requests a day, and each ReAct step is one request. It
  ignores temperature and top-p, and rejects top-k and the penalties. That's why the settings experiments also run
  on Gemma 4 and a local model (see [stage0_findings.md](stage0_findings.md)).
- **Memory is the chat history only:** nothing is remembered between sessions. The logs are local files (lost on a
  Hugging Face Space restart).
- **The model is configuration.** Switching to another model or provider changes `.env` only (see the README). How
  well the agent follows the ReAct format depends on the model, and the experiments measure this.
