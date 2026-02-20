# FabriCore: AI Agent SSoT (Comprehensive Technical Reference)

This document is the absolute source of truth for AI agents working on FabriCore.
It should be kept in perfect sync with the codebase.

## 🏗 System Architecture
- **Server:** Python 3.10+, FastAPI, NiceGUI (Modular Components), SQLAlchemy, PostgreSQL.
- **Inference Engine:** `llama-server` (Official C++ binary) on `http://llama:8080`.
- **Agent:** Go 1.24+, WebSocket (JSON-RPC 2.0) on `/api/v1/ws`.
- **UI:** Modularized components in `server/app/ui/components/` orchestrated by `main.py`.

## 📡 Protocol Specification (JSON-RPC 2.0)

### 1. Handshake (`agent.identify`)
Sent by Agent immediately upon connection.
- **Params:** `agent_id`, `token`, `os_info` (platform, hostname, arch), `capabilities` (native_tools, mcp_servers), `security_policy`.

### 2. Command Execution (`tool.execute`)
Server -> Agent. Dispatched by `ToolExecutor` after policy check.
- **Params:** `tool_name`, `arguments`, `execution_id`, `approved_by` (if HITL required).

### 3. MCP Proxying (`mcp.proxy`)
Server -> Agent. Forwards requests to local MCP servers discovered by the agent.

## 🤖 LLM & Tool Calling
- **Pattern:** ReAct (Reason+Act) Loop.
- **Max Turns:** Default 15 (max 50).
- **Core Loop:**
  1. LLM output parsed for `tool_call` blocks.
  2. Server checks security policy (HITL).
  3. Action executed; result fed back as a `system` message.
- **Parsing:** Handled by `_parse_tool_call` in `llm_service.py`.

## 🛡 Security & HITL
- **Multi-Layered Enforcement:**
  1. **Server-Side:** `ToolExecutor` validates against agent policies before dispatch.
  2. **Agent-Side:** `SecurityManager` regex blocks or requires approval.
- **HITL:** Sensitive tools pause execution. Approval is handled via inline cards in the chat; clicking "Approve" resumes the loop turn with an `approved_by` flag.

## ⏰ Scheduling & Automation
- **Service:** `SchedulerService` using `APScheduler`.
- **Logic:** Can switch models via Docker SDK and execute ReAct loops autonomously.
- **Persistence:** Jobs stored in `schedules` table with Cron expressions.

## 🎨 UI Architecture
- **Modular Components:**
  - `SettingsDialog`: Model management and system configuration.
  - `SchedulerDialog`: Cron job management.
  - `HITLDialog`: Security policy configuration.
  - `ChatInterface`: Encapsulates the agent interaction loop and session state.
- **Theme-Aware:** CSS uses `.body--dark` and `.body--light` for consistent mode switching.
- **PWA:** Service Worker (`sw.js`) and Manifest (`manifest.json`) support standalone installation and Web Push notifications.

## 🗄 Persistence (PostgreSQL)
- `agents`: Identity and security policies.
- `audit_log`: History of all tool executions.
- `chat_sessions` & `chat_messages`: Dialog history and state.
- `schedules`: Registered autonomous tasks.
- `pending_approvals`: HITL queue.
- `push_subscriptions`: VAPID-based notification targets.
- **VAPID Implementation:** Follows standard PEM-based approach. Use `vapid --generate` to refresh keys. Store path in `VAPID_PRIVATE_KEY_PATH`.

## 💡 Development Guidelines
1. **Concurrency:** Use non-blocking `asyncio` (Python) and `goroutines` (Go).
2. **State:** Strictly centralized in `DataManager`. No local state in agents.
3. **DI:** Use `app.core.dependencies` for singleton service access.
