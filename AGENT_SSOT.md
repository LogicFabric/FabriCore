# FabriCore: AI Agent SSoT (Comprehensive Technical Reference)

This document is the absolute source of truth for AI agents working on FabriCore.
Update this file on every change or mismatch. This file should always in sync with the codebase.

## 🏗 System Architecture
- **Hub-and-Spoke:** `Orchestrator` -> `Managers` -> `Agents`.
- **Server:** Python 3.10+, FastAPI, NiceGUI, SQLAlchemy, PostgreSQL.
- **Inference Engine:** `llama-server` (Official C++ binary), Debian 13 (Debian Trixie), Vulkan support.
- **Agent:** Go 1.24+, Native Binary (Systemd/Exec), WebSocket + JSON-RPC 2.0.
- **Development:** `go run` types for Agent, `docker-compose` for Server.

## 🔗 Internal Communication
- **Server <-> Inference:** HTTP API (`/v1/chat/completions`) on `http://llama:8080`.
- **Server <-> DB:** PostgreSQL (SQLAlchemy).
- **Server <-> Agent:** WebSocket (JSON-RPC 2.0) on `/api/v1/ws`. Accepts `token` query parameter.
- **Model Switching:** Server updates `/app/llm_models/llama_args.txt` and restarts the `llama` container via Docker SDK.
- **Inference Config:** Supports `--flash-attn`, `--parallel` (np), and `--cache-type-k/v` (quantization).

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
      "platform": "string",
      "hostname": "string",
      "arch": "string",
      "memory_total": "int (optional)"
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
- **Architecture:** ReAct (Reason+Act) Loop.
- **Max Turns:** Configurable (default: 15, up to 50). (Think -> Act -> Observe).
- **Prompting Strategy:** System prompt enforces "Autonomous System Administrator" persona. Critical rules enforce result verification and self-correction.
- **Request Flow:**
  1. User sends message.
  2. **Loop Start:**
     a. LLM generates thought/action (`tool_call` JSON).
     b. **IF** no tool call -> Break loop, show answer.
     c. **IF** tool call -> Server executes tool (handling errors gracefully).
     d. Server appends `assistant` message (Tool Call) to history.
     e. Server appends `system` message (Observation/Result) to history.
     f. **Continue Loop** (LLM analyzes result and decides next step).
- **Tool Protocol:** LLM must output a block formatted as:
  ```tool_call
  {"tool": "tool_name", "params": {"key": "value"}}
  ```
  *Regex parsing is used as a fallback for mixed output.*
- **Parsing:** Handled by `_parse_tool_call` in `llm_service.py` (Robust JSON text search).

### 6. Security & Policy
The system implements a multi-layer security model:

1.  **Agent-Side Kernel (Go)**:
    -   `SecurityManager` enforces rules locally using regex patterns.
    -   Actions can be `allow`, `block`, or `require_approval`.
    -   Default policy is `allow` (for now) but specific dangerous commands like `rm -rf /` are blocked.

2.  **Server-Side Policy**:
    -   Policies are stored in the `agents` table and synced to agents.
    -   Server UI allows configuring policies per agent (Settings → Agents).

3.  **Human-in-the-Loop (HITL)**:
    -   If an action requires approval (either by direct tool name or mapped shell command), the execution pauses.
    -   **Command-to-Tool Mapping**: Server maps shell commands like `ls`, `cat`, `rm` to their respective internal tools (`list_files`, `read_file`, `run_command`).
    -   Server-side check in `ToolExecutor` validates policy *before* dispatching to Agent.
    -   **Inline Approval Cards**: Rendered directly in the chat with Approve/Deny buttons. Approval re-triggers execution immediately with an `approved_by` flag.

### 7. Scheduling & Automation
-   **Scheduler Service**: Runs inside the server container using `APScheduler`. Loaded on startup.
-   **Context-Aware**: Can switch models dynamically based on task requirements.
-   **Autonomous Loop**: Executes tasks using the same ReAct loop logic as the chat interface.
-   **Database**: Stores schedules in the `schedules` table with Cron expressions.
-   **Persistent Chat**: Schedules can optionally reuse a single chat session (`use_persistent_chat`, `chat_session_id`), or create a new chat per trigger.
-   **UI**: Managed via a dedicated Scheduler dialog (clock icon in header), not a tab.

### 8. UI Architecture
-   **Chat-First Layout**: Single full-viewport chat window (no tabs).
-   **Session Pinning**: The `send_message` loop pins the `pinned_session_id`, `pinned_chat_container`, and `pinned_chat_messages` snapshot upon initiation. This prevents cross-chat contamination if a user navigates away mid-generation.
-   **Unread Background Handling**: If a response completes while the user is away, the session is marked as unread (blue dot), and the history is updated silently in the database.
-   **Left Drawer**: Chat history with hover-reveal delete buttons and blue unread indicators.
-   **Header**: Model indicator, HITL Shield icon (security dialog), Scheduler button (clock icon), Settings button (gear icon).
-   **Dropdowns over Text**: Sensitive inputs like "Agent ID" in the Scheduler are implemented as `ui.select` dropdowns populated from registered agents to prevent user typos.

## 📂 Implementation & Discovery
- **Agent Tools:** Registed in `agent/internal/tools/`.
- **Local MCP Discovery:** Agent scans `mcp_config.json` on startup.
- **Audit Logs:** Every command creates an `AuditLog` entry via `AgentManager.send_command`.

## 🗄 Persistence (PostgreSQL)
- **`agents`**: `id`, `name`, `hostname`, `platform`, `arch`, `memory_total`, `supported_tools` (JSON), `os_info` (JSON), `status`, `last_seen`, `security_policy_json`.
- **`audit_log`**: `id` (UUID string), `agent_id`, `tool_name`, `arguments` (JSON), `result` (JSON), `status` (pending|success|error), `created_at`, `completed_at`.
- **`chat_sessions`**: `id`, `title`, `has_unread` (bool), `created_at`. Messages via `chat_messages`.
- **`chat_messages`**: `id`, `session_id` (FK), `role`, `content`, `metadata_json` (JSON), `created_at`.
- **`schedules`**: `id`, `agent_id` (FK), `cron_expression`, `task_instruction`, `required_model`, `is_active`, `use_persistent_chat` (bool), `chat_session_id` (FK nullable), `created_at`.
- **`pending_approvals`**: `id`, `execution_id`, `agent_id`, `tool_name`, `arguments` (JSON), `status`, `session_id` (FK nullable), `created_at`.

## 💡 Guidelines
1. **Concurrency:** Use `asyncio` for Python and `goroutines` for Go. No blocking calls.
2. **State:** No local state in Agents. All persistence goes through `DataManager`.
3. **Dependency Injection:** Use `app.core.dependencies` for Singleton services (`AgentManager`, `DataManager`).
4. **Security:** Native Go `Registry` manages tool availability; `SecurityManager` enforces policies.
