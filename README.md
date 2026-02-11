# FabriCore: Agentic AI RMM

FabriCore is a modern Remote Monitoring & Management (RMM) tool powered by AI. It orchestrates intelligent agents across your infrastructure to automate system administration securely and efficiently.

## ✨ Features
- **Intelligent Orchestration:** Plan and execute complex sysadmin tasks using natural language.
- **Hub-and-Spoke Architecture:** Centralized control with specialized managers.
- **Native Go Agents:** High-performance, stateless agents that run directly on the host OS.
- **Security First:** Built-in Human-in-the-Loop (HITL) approvals and strict JSON-RPC protocol.
- **Extensible Capabilities:** Seamlessly integrate third-party tools via the Model Context Protocol (MCP).

## 🚀 Quick Start

### 1. Server (Docker)
The server runs containerized for easy deployment.
```bash
cd server
docker-compose up --build
# Dashboard accessible at http://localhost:8000
```

### 2. Agent (Native)
The agent must run natively on the host OS to access system resources.
```bash
cd agent
go run cmd/agent/main.go --server "ws://localhost:8000/api/v1/ws" --token "your-auth-token"
```

## 🏗 Project Structure
- **/server**: Python-based hub orchestrating managers and AI logic.
- **/agent**: Go-based client binary for system execution.
- **/docs**: Legacy documentation and diagrams (see `AGENT_SSOT.md` for latest).

---

## 🤖 For AI Agents & Developers
Technical implementation details, protocol specifications, and architecture standards are maintained in the Single Source of Truth:

👉 **[AGENT_SSOT.md](AGENT_SSOT.md)**
