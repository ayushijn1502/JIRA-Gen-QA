# AutoTest-Agent — Manager Roadmap & How It Works

This document explains **what the tool does**, **how it starts**, **how it reads JIRA**, **how it creates test automation**, and **how the pieces fit together**. You can share this file as-is with stakeholders.

---

## Executive summary (one sentence)

**AutoTest-Agent** reads a **JIRA ticket**, uses **AI plus your existing pytest codebase (RAG)** to **draft pytest tests**, **runs pytest to validate them**, optionally **opens a GitHub pull request**, and includes a **human approval step** before any GitHub action (when enabled).

---

## What problem it solves

- **Manual gap:** Turning a JIRA story into consistent, repo-aligned tests takes time.
- **This POC:** Automates **requirements → test plan → code → machine verification → optional PR**, grounded in **your** patterns (`target_framework/`) and **your** rules (`docs/*.md`).

---

## Step 1 — Where the tool initializes

| Step | What happens |
|------|----------------|
| **You run the CLI** | Example: `python main.py run KAN-1`. Entry point: `main.py` at the project root. |
| **Configuration loads** | `config.yaml` is read and validated (Pydantic) via `autotest_agent/config.py`: JIRA URL/credentials, **Gemini-only** settings (API key, model id, optional `max_output_tokens`, **`max_total_tokens_per_run`** soft budget, **`run_preflight`**), **`poc`** (default: two scenarios, smaller RAG windows when enabled), paths, **`max_retries`** (each retry re-invokes **Generate**), GitHub on/off. |
| **Gemini preflight (optional)** | Before indexing or JIRA fetch, **`main.py`** can call `autotest_agent/infrastructure/gemini_preflight.py`: a lightweight **metadata** request to Google to confirm the key and model id. Google does **not** expose “remaining free quota” in this API; the app also **sums reported token usage** after each successful LLM call and can refuse further calls if the next request would exceed the configured per-run budget (`GeminiLLMService` in `llm_service.py`). Set `gemini.run_preflight: false` only if you must skip the check (same host as chat). |
| **Services are created** | The same startup path wires concrete implementations: **JIRA client**, **RAG (FAISS + embeddings)**, **Gemini LLM** (sole provider), **GitHub** (or a no-op when disabled), **pytest runner**, **prompt builder**. **Ollama / local LLM** is not used. |
| **Persona and rules load** | `autotest_agent/agents/prompts.py` reads **`docs/agents.md`**, **`docs/skills.md`**, and **`docs/knowledge_base.md`**. Those files define **agent roles**, **documented “skills”**, and **coding standards** injected into the LLM system prompts. |
| **RAG indexes the framework** | Before the main workflow runs, Python files under **`target_framework/`** are chunked, embedded, and stored in a **FAISS** index so later steps can retrieve relevant examples. |

**Stakeholder takeaway:** One command loads **config**, **team-written rules from markdown**, and **searchable context from your sample test repo**.

---

## Step 2 — How it reads the JIRA ticket

| Step | What happens |
|------|----------------|
| **Issue key from the CLI** | Example: `KAN-1` (the key from your JIRA board URL). |
| **JIRA REST access** | `autotest_agent/infrastructure/jira_wrapper.py` uses **python-jira** with the server URL, email, and API token from configuration. |
| **Normalized ticket object** | The wrapper maps JIRA fields into an internal model: **ticket id**, **title**, **description**, and **acceptance criteria** (criteria are parsed from plain-text description patterns where possible). |

**Stakeholder takeaway:** The pipeline consumes a **real ticket** as structured **requirements input**, not a hand-typed summary.

---

## Step 3 — How “automation” is created (LangGraph workflow)

Orchestration is a **state machine** built with **LangGraph** (`autotest_agent/agents/graph.py`). Each step updates shared state (`autotest_agent/domain/models.py`). Node implementations live in `autotest_agent/agents/nodes.py`.

### High-level flow

```text
Analyze → Generate → Verify → (if tests fail and retries remain) → Generate again …
       → (if tests pass) → Deploy (optional GitHub, with human approval)
```

| Stage | Business meaning | Technical meaning (short) |
|--------|------------------|---------------------------|
| **Analyze** | Decide **what** to test and **where** it should live, using ticket text **plus** similar code from the repo. | RAG query + Gemini produces a structured **test plan** (scenarios, target path, context). By default **`poc.max_test_scenarios` is 2** (positive + negative); prompts and a hard cap keep the plan small to limit tokens. |
| **Generate** | **Write** the pytest file content. | Gemini returns structured JSON (file path, code, explanation). On retry, previous **pytest errors** are included in the prompt. **`max_retries`** should stay low for free-tier usage. |
| **Verify** | **Prove** the code runs. | Generated file is written to disk; **`pytest`** is run via subprocess; pass/fail and logs are recorded. |
| **Deploy** | **Human gate**, then optional delivery. | Terminal shows the code; user confirms. If GitHub is enabled: create branch, push file, open PR. If disabled: finish locally with file on disk only. |

**Stakeholder takeaway:** “Automation” here means **machine-generated tests** that are **checked by pytest** in a **retry loop**, with a **person in the loop** before anything ships to GitHub.

---

## Step 4 — How RAG keeps tests “on-brand”

| Step | What happens |
|------|----------------|
| **Corpus** | The indexed tree is **`target_framework/`** (for example `src/` and `tests/`). |
| **Pipeline** | `autotest_agent/infrastructure/rag_engine.py`: split files into chunks → **sentence-transformers** embeddings → **FAISS** vector store. |
| **Usage** | **Analyze** (and **Generate**) query this index so suggestions align with **existing fixtures, naming, and mocking style**. |

**Stakeholder takeaway:** Outputs are **grounded in your repository examples**, not generic internet advice.

---

## Architecture at a glance (why this is maintainable)

**Hexagonal / clean-style layout:**

| Layer | Role | Main locations |
|-------|------|----------------|
| **Domain** | Data shapes and **interfaces** (“ports”) only—no vendor SDKs. | `autotest_agent/domain/models.py`, `autotest_agent/domain/ports.py` |
| **Infrastructure** | **Adapters**: JIRA, RAG, Gemini (with usage accounting), Gemini preflight, GitHub, pytest runner. | `autotest_agent/infrastructure/` |
| **Application / orchestration** | LangGraph graph, nodes, prompt assembly. | `autotest_agent/agents/` |
| **Presentation** | CLI (Typer). | `main.py` |

**Stakeholder takeaway:** **Swappable integrations** (for example GitHub off for POC) and a **clear boundary** between workflow logic and external systems.

---

## Configuration and commands (operational)

| Item | Purpose |
|------|---------|
| **`config.yaml`** | API keys, JIRA server, **`gemini`**: `api_key`, `model_name` (e.g. `gemini-2.5-flash-lite`), `max_output_tokens`, **`max_total_tokens_per_run`** (soft cap per CLI run; `null` disables), **`run_preflight`** (verify key/model before work). **`poc`**: `enabled`, `analyze_rag_chunks` / `generate_rag_chunks`, **`max_test_scenarios`** (default **2**). Paths, **`max_retries`**, **`github.enabled`**. See [free-llm-setup.md](free-llm-setup.md). |
| **`python main.py run <TICKET-KEY>`** | Full pipeline for one JIRA issue. |
| **`python main.py index`** | Rebuild only the RAG index (useful after changing `target_framework/`). |

Secrets can also be supplied via environment variables (see `autotest_agent/config.py` for the `AUTOTEST_` prefix pattern).

---

## One-page diagram (for slides)

```text
                    ┌─────────────────────┐
                    │   main.py (CLI)    │
                    └──────────┬──────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         ▼                     ▼                     ▼
   config.yaml           docs/*.md          target_framework/
   (keys, paths)    (personas, rules)      (index for RAG)
         │                     │                     │
         └─────────────────────┼─────────────────────┘
                               ▼
                    ┌─────────────────────────────┐
                    │ Optional: Gemini preflight  │
                    │ (API key + model id check)  │
                    └──────────┬──────────────────┘
                               ▼
                    ┌─────────────────────┐
                    │  Fetch JIRA ticket   │
                    └──────────┬──────────┘
                               ▼
                    ┌─────────────────────┐
                    │ LangGraph workflow   │
                    │ Analyze → Generate   │
                    │   → Verify (pytest)  │
                    │   ⇄ retry on fail    │
                    └──────────┬──────────┘
                               ▼
                    ┌─────────────────────┐
                    │ Human approval       │
                    └──────────┬──────────┘
                               ▼
              ┌────────────────┴────────────────┐
              ▼                                 ▼
     GitHub PR (if enabled)              Local file only
```

---

## Roadmap framing (past → present → next)

| Phase | Status | One-line description |
|-------|--------|----------------------|
| **POC — scaffold** | Delivered | Mock product under `target_framework/`, markdown knowledge base under `docs/`, packaged CLI and dependencies (`pyproject.toml`). |
| **POC — intelligence** | Delivered | JIRA ingestion, RAG over framework, **Gemini-only** structured outputs, **preflight + per-run token budget** (configurable), default **two test scenarios**, LangGraph with pytest verification loop, Rich approval UI, optional GitHub. |
| **Next — hardening** | Optional | Persist FAISS to disk; richer JIRA description handling (e.g. ADF); automated tests for the agent package; CI; secrets only via env/secret store. |
| **Next — product** | Optional | Multi-file outputs, update-in-place of existing tests, stricter placement policies, observability (logging / tracing), usage metrics. |

---

## Elevator pitch (~30 seconds)

> We give the tool a JIRA key. It loads our standards from markdown, indexes our pytest examples, asks the model to propose a test plan and implementation, runs **pytest** in a loop with feedback on failures, then shows us the result. We approve before anything goes to GitHub—or we keep GitHub disabled for a safe internal POC.

---

## File map (for technical readers)

| Path | Responsibility |
|------|----------------|
| `main.py` | CLI: `run`, `index`; wires services and invokes the graph. |
| `config.yaml` | Runtime configuration (not committed with real secrets in production). |
| `docs/agents.md` | Personas: JiraAnalyzer, FrameworkExpert, TestArchitect, GitAutomator. |
| `docs/skills.md` | Conceptual tool list (JIRA, RAG, file write, pytest, git). |
| `docs/knowledge_base.md` | Non-negotiable test style rules for generation. |
| `autotest_agent/config.py` | Typed settings from YAML + env. |
| `autotest_agent/domain/` | `JiraTicket`, `TestPlan`, `GeneratedTest`, ports (interfaces). |
| `autotest_agent/infrastructure/` | JIRA, RAG, **`llm_service.py`** (Gemini + usage/budget), **`gemini_preflight.py`** (key/model check), GitHub, pytest subprocess. |
| `autotest_agent/agents/graph.py` | LangGraph edges and conditional retry routing. |
| `autotest_agent/agents/nodes.py` | Analyze / Generate / Verify / Deploy node bodies. |
| `autotest_agent/agents/prompts.py` | Builds system prompts from `docs/*.md`. |
| `target_framework/` | Example app + sample tests used as RAG context. |

---

## Document control

- **Purpose:** Stakeholder / manager briefing and onboarding.
- **Maintainer:** Update this file when major workflow or config behavior changes.
- **Recent updates:** Gemini-only LLM; removed local Ollama path; added **preflight** and **per-run token guard**; default **two scenarios** and lower **`max_retries`** for free-tier POC; preflight uses **`requests`** (honors `HTTPS_PROXY`). Details: [free-llm-setup.md](free-llm-setup.md).
