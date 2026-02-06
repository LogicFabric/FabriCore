# FabriCore

FabriCore is a agentic AI RMM tool with MCP servers. It uses agents on client devices to give an AI agent on the host machine access and handles security and permissions with MCP servers.

# Project Structure: AI Agent RMM System

## Root Directory
|-- /server                 # The Host Machine Code (Python/FastAPI)
|-- /agent                  # The Client Machine Code (Go)
|-- /docs                   # Architecture diagrams and specifications
|-- docker-compose.yml      # For hosting the SERVER only (DB + Python)
|-- Makefile                # Automation for building Agent and running Server
|-- README.md

---

## 1. The Server (The Brain)
**Path:** `/server`
**Tech:** Python, FastAPI, Llama-cpp-python, SQLAlchemy, React/Vue (Frontend)

|-- /app
|   |-- /api                # API Endpoints
|   |   |-- /v1
|   |       |-- endpoints.py      # HTTP routes for the Web UI
|   |       |-- websocket.py      # WS endpoint for Agents to connect
|   |
|   |-- /core               # Core Config
|   |   |-- config.py             # Env vars, settings
|   |   |-- security.py           # Auth logic (JWT for UI, Tokens for Agents)
|   |
|   |-- /services           # Business Logic (The Heavy Lifting)
|   |   |-- agent_manager.py      # Manages connected WS sessions (The "Switchboard")
|   |   |-- llm_engine.py         # Wraps llama-cpp-python. Loads model, handles inference.
|   |   |-- mcp_translator.py     # Converts LLM text -> Valid MCP JSON-RPC
|   |   |-- tool_registry.py      # Definitions of what tools the agents have
|   |
|   |-- /models             # Database & Pydantic Models
|   |   |-- agent.py              # DB Table: Agent status, last seen, OS info
|   |   |-- audit_log.py          # DB Table: History of commands executed
|   |
|   |-- main.py             # Application Entrypoint
|
|-- /ui                     # The Web Dashboard (React/Vue/Svelte)
|-- /llm_models             # Folder to store .gguf model files
|-- requirements.txt

---

## 2. The Agent (The Hands)
**Path:** `/agent`
**Tech:** Go (Golang)
**Concept:** "Native Supervisor" (No Docker for tools)

|-- /cmd
|   |-- /agent
|       |-- main.go         # Entry point. Parses flags (--server, --token), starts loop.
|
|-- /internal
|   |-- /transport          # Network Logic
|   |   |-- websocket.go          # Connects to Server, handles Reconnects, Heartbeats.
|   |
|   |-- /mcp                # Protocol Handler
|   |   |-- jsonrpc.go            # Decodes incoming JSON -> Calls internal function.
|   |   |-- schema.go             # Structs matching the MCP spec.
|   |
|   |-- /tools              # The "Safe" Native Tools (The most critical part)
|   |   |-- filesystem.go         # Safe read/write/list with rollback logic.
|   |   |-- system.go             # ps, top, kill, service restart (cross-platform).
|   |   |-- network.go            # curl, ping, netstat.
|   |
|   |-- /security           # Safety Features
|   |   |-- hitl.go               # "Human In The Loop". Blocks execution until Server confirms.
|   |   |-- backup.go             # Creates file backups before modification.
|   |
|   |-- /config             # Local config management
|
|-- go.mod                  # Go Dependencies
|-- go.sum



# Design pattern:
Command and control (c2) Event-Driven, not Request-Response.

Initiator: The Agent (Go) always initiates the connection (WebSocket Client).

Persistence: The connection stays open.

Asynchrony: The Server (Python) sends a command and does not wait for an immediate return value in the same function call. It waits for an event to come back later.

Statelessness (Agent): The Agent remembers nothing between restarts. All "memory" (history, config, user preferences) lives on the Server.




# Big Picture:


---
config:
  layout: dagre
---
flowchart TB
 subgraph Host["Host Machine (Server)"]
    direction TB
        UI[("Web Frontend<br>(React/Vue)")]
        API[("FastAPI Backend")]
        DB[("Database<br>(SQLite/Postgres)")]
        LLM[("AI Engine<br>(Llama-cpp)")]
  end
 subgraph Client["Client Machine (Agent)"]
        Agent[("Go Agent Binary")]
        OS[("Operating System<br>(Files/Process)")]
        MCP[("MCP Servers<br>(Other programs)")]
  end
    UI <-- HTTP/REST --> API
    API <-- SQL --> DB
    API <-- Internal Call --> LLM
    Agent <-- "WebSocket (JSON-RPC)" --> API
    Agent <-- Native Syscalls --> OS
    Agent <-- Wrapper --> MCP

     UI:::host
     API:::host
     DB:::host
     LLM:::host
     Agent:::client
     OS:::client
     MCP:::client
    classDef host fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef client fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px




## Interface definitions

# Go Agent with Backend Server

JSON-RPC 2.0 (compatible with MCP)

Handshake (Authentication)
{
  "jsonrpc": "2.0",
  "method": "agent.identify",
  "params": {
    "agent_id": "uuid-1234",
    "token": "secret-auth-token",
    "os_info": {
      "platform": "linux",
      "hostname": "ubuntu-server-01",
      "arch": "amd64",
      "memory_total": 16000
    },
    "supported_tools": ["list_files", "read_file", "exec_command"]
  },
  "id": 1
}


Server Command (Request)
{
  "jsonrpc": "2.0",
  "method": "tool.execute",
  "params": {
    "tool_name": "read_file_tail",
    "arguments": {
        "path": "/var/log/syslog",
        "lines": 50
    },
    "require_approval": false
  },
  "id": "req-555"
}


Agent Response (Result)
{
  "jsonrpc": "2.0",
  "result": {
    "status": "success",
    "output": "Feb 5 10:00:01 ubuntu CRON[123]: ...",
    "timestamp": "2024-02-05T10:00:05Z"
  },
  "error": null,
  "id": "req-555"
}


# Go agent with OS systemcalls:

type SystemOps interface {
    GetCPUUsage() (float64, error)
    RestartService(serviceName string) error
    ListProcesses() ([]ProcessInfo, error)
}

Linux (system_linux.go): Uses /proc filesystem or syscall library.

Windows (system_windows.go): Uses golang.org/x/sys/windows (Win32 API).

MacOS (system_darwin.go): Uses sysctl (Cgo calls).


# Go agent with External MCP Servers

The Go agent wraps the MCP in a JSON-RPC 2.0 communication layer.
https://modelcontextprotocol.io/specification/2025-06-18



# Frontend with Backend

Method,Endpoint,Description
POST,     /auth/login,              Login for the Admin (returns JWT).
POST,     /auth/refresh,            Refresh session token.
GET,      /system/status,           Backend health, AI model loaded status, memory usage.
POST,     /system/config,           Update global settings (e.g., Change AI Model path).
GET,      /agents,                  List all agents (ID, Name, Status, OS, IP).
GET,      /agents/{id},             Get detailed hardware specs (CPU, RAM, Disk).
PATCH,    /agents/{id},             Rename agent (e.g., ""Server-Room-1"").
DELETE,   /agents/{id},             Remove agent from DB (and disconnect if active).
POST,     /agents/{id}/approve,     Security: Approve a pending ""Write"" action (HITL).
POST,     /chat/completion,         Send user prompt -> Orchestrator -> Agent.
GET,      /chat/history/{agent_id}, Get past conversation/command logs.
POST,     /chat/interrupt,          Stop the AI if it's stuck in a loop.
GET,      /mcp/{agent_id}/tools,    List all capabilities of this specific agent (Native + External).
GET,      /mcp/store,               (Optional) A ""Store"" of downloadable MCP tool definitions.


# AI Engine with Backend


# Internal Architecture (Python Server)

Since the AI Engine runs within the Python process, there is no network protocol. Instead, we use the **Orchestrator Pattern** to manage the logic.

## Class Diagram (The Wiring)
```mermaid
classDiagram
    class AgentOrchestrator {
        -connection_mgr: ConnectionManager
        -model_mgr: ModelManager
        +process_user_request(text, agent_id)
        +handle_tool_output(json_result)
    }

    class ConnectionManager {
        -active_sockets: Dict
        +send_json(agent_id, payload)
    }

    class ModelManager {
        -llm: Llama
        +generate_plan(user_input, tools_schema) -> JSON
    }

    AgentOrchestrator --> ConnectionManager : Controls
    AgentOrchestrator --> ModelManager : Consults


