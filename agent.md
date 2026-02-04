# Project Definition: FabriCore
***"The Operating System for Agentic Automation."***

## 1. Project Identity & Scope
**FabriCore** is a self-hosted platform designed to orchestrate AI agents across distributed infrastructure. Unlike traditional chat interfaces (Open WebUI), FabriCore focuses on **headless automation**, **scheduled jobs**, and **remote infrastructure management**.

* **Core Philosophy:** "Brain in the Center, Hands on the Edge."
* **Primary LLM Backend:** **LM Studio** (Local/Offline first), with fallbacks to OpenAI/Anthropic.
* **Architecture Pattern:** Hub-and-Spoke (Central Python Core <-> Many Go Nodes).

## 2. Technical Stack (The "Best Practice" Choice)

### A. The Core (Web UI & Orchestrator)
* **Language:** **Python 3.11+**
* **Framework:** **FastAPI** (Backend API) + **React/Vue** (Frontend).
* **Automation Engine:** **APScheduler** (Time-based triggers) + **Celery** (Task Queue).
* **LLM Interface:** `openai-python` (configured for LM Studio `base_url`) or `lmstudio-python` SDK.
* **Database:** **SQLite** (Single-file simplicity for easy self-hosting) or PostgreSQL (Enterprise mode).

### B. The Node (Remote Agent)
* **Language:** **Go (Golang)** 1.22+
* **Deployment:** Single static binary (Zero dependencies on target).
* **Runtime Control:** **Docker SDK** (to spawn MCP containers) + **os/exec** (for raw shell tasks if permitted).
* **Protocol:** **WebSocket (WSS)** (Reverse tunnel to Core; no inbound ports needed on Node).

## 3. The Golden Rules (DOs and DON'Ts)

### DOs
* **DO Enforce "Supervisor Pattern":** The Go Node is the *only* process allowed to talk to the Docker Socket (`/var/run/docker.sock`) on the target machine.
* **DO Use "Least Privilege":** When the Core requests a new MCP server (e.g., "File Manager"), the Node must spin up a Docker container with *only* the specific volume mounts requested (e.g., `-v /var/www:/data`), never the host root.
* **DO Encrypt Secrets:** All API keys and environment variables stored in the Python Core must be encrypted at rest (AES-256).
* **DO Design for "Offline":** The system must function (scheduler running) even if the browser UI is closed.

### DON'Ts
* **DON'T Run Python on Nodes:** The remote servers should not require Python/Pip. The Node must be a standalone Go binary.
* **DON'T Hardcode Models:** The Core must allow selecting different models per Job (e.g., "Use Llama-3-8B for logs, Qwen-2.5-Coder for scripts").
* **DON'T Expose Nodes Publicly:** Nodes should never listen on a public HTTP port. They must *dial out* to the Core via WebSocket.

## 4. Detailed Architecture

### Component A: FabriCore Nexus (Python Web UI)
The central brain. It does not run tools itself; it delegates them.

1.  **Agentic Job System:**
    * **Trigger:** Cron (`0 8 * * *`) or Webhook (`POST /api/webhook/deploy`).
    * **Workflow:**
        1.  Job starts.
        2.  Core retrieves context (e.g., "Check disk space on Server A").
        3.  Core constructs an LLM Request including the **Tool Definitions** available on Server A.
        4.  LLM (LM Studio) returns a **Tool Call** (JSON).
        5.  Core routes this JSON to **Server A's Node** via WebSocket.
        6.  Node executes and returns result.
        7.  Loop continues until task is done.
2.  **MCP Manager UI:**
    * **Marketplace:** A list of "Presets" (Docker images for standard MCPs: Filesystem, Git, Postgres, Brave Search).
    * **Pass-Through:** Ability to register an existing local MCP port (e.g., "This Node has an MCP server already running on port 3000").

### Component B: FabriCore Node (Go Binary)
The remote worker.

1.  **Capabilities Manager:**
    * **Managed MCPs:** The Node can `docker pull` and `docker run` compliant MCP images.
    * **Native Tools:** The Node provides basic built-in tools: `read_file`, `exec_command` (if enabled), `system_stats`.
2.  **Connection Manager:**
    * Maintains a persistent `ws://` connection to the Core.
    * Handles re-connection logic and authentication (via Token).

## 5. Directory Structure (Monorepo)

```text
fabricore/
├── agent.md                # THIS FILE (Source of Truth)
├── docker-compose.yml      # Runs the Core (UI + DB)
├── Makefile                # "make build-node", "make run-core"
├── core/                   # [THE BRAIN] - Python
│   ├── main.py             # FastAPI Entrypoint
│   ├── scheduler/          # APScheduler Logic
│   ├── llm/                # LM Studio / OpenAI Client Adapter
│   ├── database/           # Models (SQLAlchemy)
│   ├── api/                # REST Endpoints
│   └── ui/                 # React/Vue Source Code
└── node/                   # [THE HANDS] - Go
    ├── main.go             # Entrypoint
    ├── comms/              # WebSocket Client
    ├── runtime/            # Docker Container Manager
    └── mcp/                # Protocol Handler (JSON-RPC)
