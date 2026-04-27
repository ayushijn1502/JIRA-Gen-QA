# End-to-end flow (class-wise)

Plain-language guide to **where things initialize** and **how data moves** through AutoTest-Agent (JiraGen-QA).

---

## Big picture

You run **`main.py`** → it loads **settings**, builds **services** (JIRA, search-over-code, AI, GitHub, pytest, prompts), puts them in a **`NodeContainer`**, builds a **LangGraph** assembly line with four steps, drops the **ticket** on the shared **state**, and the graph runs **Analyze → Generate → Verify → (maybe) Deploy** until tests pass or retries run out.

---

## 1. Entry point: `main.py` + Typer

- **What it is:** The command-line front door. Typer’s `app` is created at import time; when you run `python main.py run PROJ-123`, Typer calls the `run` command function.
- **Initialization:** Nothing heavy runs at import except creating `app` and `Console`. The real work starts when `run()` executes.
- **Data:** User types a **ticket id** and optional **config path** → those become function arguments.

---

## 2. Configuration: `load_settings` → `AppSettings`

- **Where:** `autotest_agent/config.py` — `load_settings("config.yaml")` returns an **`AppSettings`** object (Pydantic), with nested pieces like **`JiraSettings`**, **`GeminiSettings`**, **`RAGSettings`**, **`GitHubSettings`**, **`PocSettings`**.
- **Layman:** The rulebook and address book: JIRA URL, API keys, which repo to use, how big code chunks are for search, etc.
- **Data flow:** YAML (and optional env vars like `AUTOTEST_GEMINI__API_KEY`) → validated **settings** object → every service is constructed using these values.

---

## 3. The wiring room: `_build_services()` in `main.py`

This function is the **only place** that connects concrete implementations. It creates:

| Class | Role in plain English |
|--------|------------------------|
| **`JiraWrapper`** | Talks to JIRA; fetches one ticket by id. |
| **`RAGEngine`** | Reads your target codebase, chunks it, embeds it; later answers “what code looks related to this ticket?” |
| **`GeminiLLMService`** | Calls Google Gemini; turns prompts into structured objects (plans, code). |
| **`GitHubService`** or **`SkippedGitHubService`** | Either creates branch/PR or pretends GitHub is off. |
| **`PytestRunner`** | Runs pytest on the generated file. |
| **`PromptBuilder`** | Loads persona/instruction text from `docs/*.md`. |

**Data flow:** `AppSettings` → constructor arguments for each service → **tuple** of ready-to-use objects returned to `run()`.

---

## 4. Optional check: `preflight_gemini`

- **Layman:** “Does the API key and model name actually work?” before spending time on RAG/JIRA.
- **Data:** Uses settings only; no ticket yet.

---

## 5. RAG indexing: `RAGEngine.index_codebase`

- **When:** Right after services exist, before the graph runs.
- **Layman:** “Read the framework folder and build an internal index so similarity search is fast.”
- **Data:** **Folder path** from settings goes in; the engine holds vectors/chunks for similarity search during the run.

---

## 6. First domain object: `JiraTicket`

- **Where:** `jira.fetch_ticket(ticket_id)` returns a **`JiraTicket`** (`autotest_agent/domain/models.py`).
- **Layman:** A clean copy of the ticket: id, title, description, acceptance criteria — what the AI will actually read.

---

## 7. Glue object: `NodeContainer`

- **Where:** `autotest_agent/agents/nodes.py`.
- **Initialization:** `main.py` passes in `llm`, `rag`, `git`, `test_runner`, `prompt_builder`, paths, flags.
- **Layman:** A **toolbelt** holding every external system. LangGraph nodes must look like `def node(state): ...`, so dependencies cannot be passed as extra parameters; instead each step is a **method on this class** (`self.llm`, `self.rag`, …).

---

## 8. Workflow definition: `build_graph` → LangGraph `StateGraph`

- **Where:** `autotest_agent/agents/graph.py`.
- **Initialization:** `StateGraph(GraphState)` registers nodes: **`analyze`**, **`generate`**, **`verify`**, **`deploy`**, plus **`fail_exit`**. Edges: analyze → generate → verify, then a **decision** after verify (pass → deploy, fail with retries left → generate again, else fail_exit).
- **Layman:** A fixed flowchart compiled into something you can `.invoke(...)`.

---

## 9. Shared state: `GraphState` (TypedDict)

- **Where:** `autotest_agent/domain/models.py`.
- **Layman:** One shared dictionary shape every step reads and updates: ticket, plan, generated test, verification result, retry count, errors, phase name.
- **Data flow:** `main.py` builds **`initial_state`** with at least `ticket`, `retry_count`, `max_retries`, `error_history`, `phase`. Each node returns a **small dict** of updates; LangGraph **merges** them into the full state.

---

## 10. The four nodes (methods on `NodeContainer`)

### Analyze (`container.analyze`)

- **Reads:** `state["ticket"]`.
- **Does:** Builds a text query from title + description → **`rag.query`** → relevant code chunks → **`PromptBuilder`** builds system text → **`llm.generate(..., TestPlan)`** produces a **`TestPlan`** (where to put tests, scenario list, stored context).
- **Writes:** `plan`, `phase`.

### Generate (`container.generate`)

- **Reads:** `plan`, `retry_count`, `error_history` (on retries).
- **Does:** Another prompt; LLM returns **`GeneratedTest`** (path, full pytest `code`, explanation). Retries use a “fix” style prompt and past errors.
- **Writes:** `generated_test`, `phase`.

### Verify (`container.verify`)

- **Reads:** `generated_test`.
- **Does:** Writes file to disk → **`test_runner.run_tests`** → **`VerificationResult`**.
- **Writes:** `verification`, bumps `retry_count` and appends to `error_history` if failed, `phase`.

### Deploy (`container.deploy`)

- **Reads:** `generated_test`, `ticket`, `plan` (for PR body).
- **Does:** Shows code in the terminal, asks **y/N** approval. If GitHub skipped: marks done locally. Else **`git.create_branch`**, **`commit_and_push`**, **`create_pr`**.
- **Writes:** `phase` = `deployed`, `completed_local`, or `cancelled`.

If verify keeps failing until retries are exhausted, **`_fail_exit`** in `graph.py` sets **`phase`** to **`failed`** (not a method on the container).

---

## 11. After `graph.invoke` in `main.py`

- **Reads:** `final_state["phase"]` and optional LLM token usage.
- **Layman:** Prints a friendly success / cancelled / failed message.

---

## Flow diagram

```mermaid
flowchart LR
  subgraph init["Startup in main.py"]
    CFG[load_settings]
    SVC[_build_services]
    CFG --> SVC
  end
  subgraph prep["Before graph"]
    RAG[RAGEngine.index_codebase]
    JIRA[JiraWrapper.fetch_ticket]
    SVC --> RAG
    SVC --> JIRA
  end
  subgraph graph["LangGraph"]
    A[analyze]
    G[generate]
    V[verify]
    D[deploy]
    A --> G --> V
    V -->|pass| D
    V -->|retry| G
    V -->|no retries| F[fail_exit]
  end
  JIRA --> ST[initial_state with ticket]
  NC[NodeContainer] --> graph
  ST --> A
```

---

## One paragraph for non-developers

**Config** loads secrets and paths. **Connectors** are created for JIRA, code search, AI, GitHub, and running tests. The **ticket** is downloaded once and placed on a **shared worksheet**. **Analyze** asks “what should we test?” and produces a plan. **Generate** writes the test file. **Verify** runs it; if it breaks, errors are saved and the system tries again. **Deploy** shows a human the code; if they agree, the tool optionally opens a pull request.
