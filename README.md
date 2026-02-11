# FabriCore

FabriCore is an agentic AI RMM (Remote Monitoring & Management) tool. It uses a **Hub-and-Spoke** architecture where a Python host orchestrates intelligent agents on client devices to perform system administration tasks securely.

# 🏗 System Architecture

## Core Design Pattern: "Hub and Spoke"
* **The Hub (Orchestrator):** The central brain. It receives user inputs, plans actions with the LLM, and coordinates the specialized Managers (Spokes) to execute tasks.
* **The Spokes (Managers):** Specialized services (Data, Scheduler, Communication) that handle specific infrastructure tasks.
* **The Hands (Agent):** A stateless Go binary running on client machines that executes approved commands.

## Tech Stack
* **Backend:** Python 3.10+, FastAPI (API), NiceGUI (Frontend & UI).
* **Database:** PostgreSQL (SQLAlchemy + Pydantic).
* **AI Engine:** Llama-cpp-python (Local) & OpenAI/Anthropic/Gemini APIs (Online).
* **Agent:** Go (Golang) 1.24+.
* **Protocol:** WebSocket + JSON-RPC 2.0.
* **Deployment:** Docker (Docker Compose). The server must be containerized.

---

# 📂 Project Structure

## 1. Server (The Hub) - `Python`
The server is a Monolithic Application divided into functional layers.

### **GUI (Presentation Layer)**
* **Location:** `app/ui/`
* **Purpose:** Contains all NiceGUI UI logic.
* **Responsibilities:** Renders the Dashboard, Agent Terminals, Settings pages, and handles user interactions.

### **Core (Application Layer)**
* **Location:** `app/services/`
* **Purpose:** Contains the business logic and the "Hub and Spoke" managers.
* **Responsibilities:**
    * **Orchestrator:** The workflow engine connecting AI planning to execution.
    * **DataManager:** The **Single Source of Truth**. Manages PostgreSQL, Local Files, and holds the **Authenticator** for user identity.
    * **CommunicationManager:** The "Switchboard". Routes WebSocket traffic and handles Notifications/Alerts.
    * **Scheduler:** Manages Cron jobs and automated maintenance tasks.

### **Interfaces (Connectivity Layer)**
* **Location:** `app/api/` & `app/llm/`
* **Purpose:** Handles connections to the "Outside World" and "AI Brains".
* **Responsibilities:**
    * **API:** REST endpoints and WebSocket handlers.
    * **LLM:** Strategy pattern for switching between Local (Llama) and Online (GPT/Claude) models.

### **Data (Persistence Layer)**
* **Location:** `app/models/`
* **Purpose:** Defines the data structure.
* **Responsibilities:**
    * **SQL Models:** Database tables (Agents, Users, Logs).
    * **Schemas:** Pydantic validators for API requests.

---

## 2. Agent (The Client) - `Go`
The Agent is a **Native Compiled Binary**. It runs directly on the Host OS to access system resources (Services, Files, Processes).
**⚠️ NOTE: The Agent must NOT run in a Docker container.**

### **Core (Supervision)**
* **Location:** `cmd/` & `internal/orchestrator/`
* **Purpose:** The main entry point and supervision loop.
* **Responsibilities:** Handles connection lifecycle, parses incoming JSON-RPC, and routes tasks.

### **Interfaces (Capabilities)**
* **Location:** `internal/sys/` & `internal/mcp/`
* **Purpose:** The tools the agent uses to interact with the OS.
* **Responsibilities:**
    * **Sys:** Native System Calls (Process, File I/O).
    * **MCP:** Wrapper for external MCP servers (Docker/Stdio).

### **Security (Guardrails)**
* **Location:** `internal/security/`
* **Purpose:** Ensures the agent never executes dangerous commands without permission.
* **Responsibilities:** Policy enforcement, HITL (Human-in-the-Loop) token verification, and command blocking.

---

# 🚀 Getting Started

## Server (Docker)
```bash
docker-compose up --build
# UI accessible at http://localhost:8000
```

## Agent (Local Dev)
```bash
cd agent
go run cmd/agent/main.go --server "ws://localhost:8000/api/v1/ws" --token "dev-token"
```

## 🛡 Security Principles
* Stateless Agent: The agent pulls its config from the server on every connection.
* Human-in-the-Loop (HITL): Critical actions (Write/Delete) require an approval token from the Server.
* Sanitized Protocol: All traffic is strict JSON-RPC 2.0. No arbitrary code execution.
