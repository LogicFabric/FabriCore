# FabriCore: AI Agent SSoT (Comprehensive Technical Reference)

This document is the absolute source of truth for AI agents working on FabriCore.
Update this file on every change or mismatch. This file should always in sync with the codebase.

## 🏗 System Architecture
- **Hub-and-Spoke:** `Orchestrator` -> `Managers` -> `Agents`.
- **Server:** Python 3.10+, FastAPI, NiceGUI, SQLAlchemy, PostgreSQL.
- **Inference Engine:** `llama-server` (Official C++ binary), Debian 13 (Debian Trixie), Vulkan support.
- **Agent:** Go 1.24+, Native Binary (Systemd/Exec), WebSocket + JSON-RPC 2.0.

## 🔗 Internal Communication
- **Server <-> Inference:** HTTP API (`/v1/chat/completions`) on `http://llama:8080`.
- **Server <-> DB:** PostgreSQL (SQLAlchemy).
- **Server <-> Agent:** WebSocket (JSON-RPC 2.0).
- **Model Switching:** Server updates `/app/llm_models/llama_args.txt` and restarts the `llama` container via Docker SDK.

## 📡 Protocol Specification (JSON-RPC 2.0)

### 1. Handshake (`agent.identify`)
Sent by Agent immediately upon connection.
**Schema (`AgentIdentity`):**
```json
{
  "jsonrpc": "2.0",
  "method": "agent.identify",
  "params": {
    "agent_id": "string (uuid)",
    "token": "string",
    "os_info": {
      "platform": "string (linux|windows|darwin)",
      "hostname": "string",
      "arch": "string",
      "release": "string",
      "uptime_seconds": "uint64"
    },
    "capabilities": {
      "native_tools": ["string"],
      "file_transfer": "bool",
      "pty_support": "bool"
    },
    "mcp_servers": [
      {
        "name": "string",
        "transport": "string (stdio|sse)",
        "command": ["string"],
        "url": "string (optional)",
        "status": "string"
      }
    ],
    "security_policy": {
      "hitl_enabled": "bool",
      "blocked_commands": ["string"],
      "requires_approval_for": ["string"]
    }
  },
  "id": 1
}
```

### 2. Command Execution (`tool.execute`)
Server -> Agent.
**Params (`ToolExecuteParams`):**
- `tool_name`: Name of the registered native tool.
- `arguments`: Map of tool-specific arguments.
- `execution_id`: Tracking ID (v4 UUID).
- `approved_by`: Required for sensitive actions (HITL).

### 3. MCP Proxying (`mcp.proxy`)
Server -> Agent (forwards to 3rd-party MCP servers).
**Params (`MCPProxyParams`):**
- `target_server`: Name of the MCP server.
- `inner_request`: Raw JSON-RPC request for the target tool.

## 🤖 LLM & Tool Calling
- **Format:** ChatML.
- **Tool Trigger:** LLM must output a block formatted as:
  ```tool_call
  {"tool": "tool_name", "params": {"key": "value"}}
  ```
- **Parsing:** Handled by `_parse_tool_call` in `llm_service.py`.

## 📂 Implementation & Discovery
- **Agent Tools:** Registed in `agent/internal/tools/`.
- **Local MCP Discovery:** Agent scans `mcp_config.json` on startup.
- **Audit Logs:** Every command creates an `AuditLog` entry via `AgentManager.send_command`.

## 🗄 Persistence (PostgreSQL)
- **`agents`**: Core metadata + `capabilities`, `os_info` (JSON).
- **`audit_logs`**: `id` (int), `agent_id`, `timestamp`, `action`, `details` (JSON), `status` (success|failed|pending_approval), `approved_by`.
- **`chat_sessions` / `chat_messages`**: Standard history with UUID for sessions.

## 💡 Guidelines
1. **Concurrency:** Use `asyncio` for Python and `goroutines` for Go. No blocking calls.
2. **State:** No local state in Agents. All persistence goes through `DataManager`.
3. **Security:** Native Go `Registry` manages tool availability; `SecurityManager` enforces policies.
