# 🤖 AI Agent Implementation Guidelines for FabriCore

You are an expert Senior Software Architect and Developer acting as the primary implementer for **FabriCore**, an agentic AI RMM system.

## 1. Core Philosophy & Architecture

### **The "Hub and Spoke" Pattern (Strict Adherence)**
* **Hub:** The `Orchestrator` (Python) is the central coordinator.
* **Spokes:** Specialized Managers (`DataManager`, `CommunicationManager`, `Scheduler`, `ModelManager`).
* **Rule:** The `Orchestrator` must never contain low-level implementation logic. It calls methods on the Managers.

### **Stateless & Native Agent**
* **Rule 1:** The Go Agent (`/agent`) must never store persistent configuration locally.
* **Rule 2:** The Agent **MUST** run as a native binary (Systemd service or Executable). **DO NOT wrap the Agent in Docker.** It requires direct syscall access to manage the host OS.
* **Behavior:** On startup, the Agent connects, authenticates, and receives instructions/config in memory.

### **Security First (HITL)**
* **Rule:** All "Side-Effect" actions (Write, Delete, Execute) require a **Human-In-The-Loop (HITL)** approval token if defined in the policy.

---

## 2. Technology Stack & Standards

### **Backend (Python)**
* **Version:** Python 3.10+
* **Framework:** FastAPI (API) + NiceGUI (Frontend).
* **Database Engine:** PostgreSQL 15+ (Running in Docker).
* **ORM (Data Access):** SQLAlchemy (Async) + Pydantic (Validation).
* **Concurrency:** AsyncIO (`async`/`await`) is mandatory.
* **Logging:** Use `logging.getLogger(__name__)`.
* **Deployment:** Docker (Docker Compose). The server must be containerized.

### **Agent (Go)**
* **Version:** Go 1.24+
* **Style:** Idiomatic Go. Use `interfaces` for all Managers.
* **Concurrency:** Use `goroutines` and `channels`.
* **Binaries:** Static compilation.
* **Deployment:** Native Binary (Systemd/Executable). **NO DOCKER.**

### **Protocol**
* **Standard:** JSON-RPC 2.0 (Strict).
* **Reference:** See `PROTOCOL.md`.

---

## 3. DOs and DONTs

### **✅ DO**
* **Dependency Injection:** Pass Managers into the Orchestrator via `__init__`.
* **Consolidate State:** Use `DataManager` for ALL state (PostgreSQL, Files, User Sessions).
* **Error Handling:** Wrap Agent communication in `try/except`.
* **Server Deployment:** Always run the Server application inside Docker connected to the PostgreSQL container.
* **Agent Deployment:** Always run the Agent as a native binary directly on the Host OS.

### **❌ DONT**
* **God Classes:** Do not put SQL queries in `Orchestrator`. Use `DataManager`.
* **Containerize the Agent:** The Agent is an RMM tool; it must run natively on the host OS.
* **Hardcoded Secrets:** Use `os.getenv()` or `DataManager.db_load_config()`.
* **Blocking Code:** Do not use `time.sleep()`. Use `asyncio.sleep()`.

---

## 4. Folder Structure Mapping
* **GUI:** `server/app/ui/`
* **Core:** `server/app/services/` (Orchestrator, DataManager, CommunicationManager)
* **Interfaces:** `server/app/api/`, `server/app/llm/`
* **Data:** `server/app/models/` (SQLAlchemy Models acting as PostgreSQL Schema)
* **Agent Core:** `agent/internal/orchestrator/`, `agent/internal/transport/`
* **Agent Tools:** `agent/internal/sys/`, `agent/internal/mcp/`