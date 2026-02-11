# Interface definitions

<br>

## Agent <-> Server Communication
Protocol: WebSocket + JSON-RPC 2.0 Direction: Bidirectional (Server commands Agent, Agent reports status)

<br>

### Handshake (Agent -> Server)
Sent immediately upon connection. Now includes discovered MCP servers and security posture.

Method: agent.identify


```json
{
  "jsonrpc": "2.0",
  "method": "agent.identify",
  "params": {
    "agent_id": "uuid-550e8400-e29b",
    "token": "auth-token-secret-123",
    "os_info": {
      "platform": "linux",
      "hostname": "prod-db-01",
      "arch": "amd64",
      "release": "Ubuntu 22.04 LTS",
      "uptime_seconds": 36005
    },
    "capabilities": {
      "native_tools": ["list_files", "read_file", "exec_command", "system_stats", "download_file"],
      "file_transfer": true,
      "pty_support": true
    },
    "mcp_servers": [
      {
        "name": "postgres-mcp",
        "transport": "stdio",
        "command": ["docker", "run", "-i", "mcp/postgres"],
        "status": "available"
      },
      {
        "name": "brave-search",
        "transport": "sse",
        "url": "http://localhost:8080/sse",
        "status": "ready"
      }
    ],
    "security_policy": {
      "hitl_enabled": true,
      "blocked_commands": ["rm -rf /", "mkfs"],
      "requires_approval_for": ["write_file", "restart_service"]
    }
  },
  "id": 1
}
```

<br>

### Native Tool Execution (Server -> Agent)
Standard command execution for built-in syscalls.

Method: tool.execute


```json
{
  "jsonrpc": "2.0",
  "method": "tool.execute",
  "params": {
    "tool_name": "exec_command",
    "arguments": {
        "command": "systemctl restart nginx",
        "timeout": 30
    },
    "execution_id": "task-999",
    "approved_by": "admin_user_id" 
  },
  "id": "req-101"
}
```
Note: approved_by is optional but serves as a cryptographic proof that the Orchestrator/SecurityManager authorized this action, allowing the Agent's SecurityManager to validate it.

<br>

### MCP Proxy Request (Server -> Agent)
Wraps a request intended for a third-party MCP server running on the agent.

Method: mcp.proxy

```json
{
  "jsonrpc": "2.0",
  "method": "mcp.proxy",
  "params": {
    "target_server": "postgres-mcp",
    "inner_request": {
      "jsonrpc": "2.0",
      "method": "tools/call",
      "params": {
        "name": "query_database",
        "arguments": { "sql": "SELECT count(*) FROM users;" }
      },
      "id": 50
    }
  },
  "id": "req-102"
}
```

<br>

### File Transfer (Server -> Agent)
Instructs the agent to download a file from the backend's FileManager.

Method: tool.execute (using download_file)

```json
{
  "jsonrpc": "2.0",
  "method": "tool.execute",
  "params": {
    "tool_name": "download_file",
    "arguments": {
        "source_url": "https://fabricore-server/api/v1/files/scripts/update_agent.sh",
        "destination_path": "/tmp/update_agent.sh",
        "verify_hash": "sha256:e3b0c44298..."
    }
  },
  "id": "req-103"
}
```

<br>

### Responses & HITL Errors (Agent -> Server)
Success Response:

```json
{
  "jsonrpc": "2.0",
  "result": {
    "status": "success",
    "output": "Service restarted successfully.",
    "exit_code": 0,
    "timestamp": "2024-02-05T12:00:00Z"
  },
  "id": "req-101"
}
```
Security Violation (HITL Trigger): If the Server sends a sensitive command without an approval token, or if the Agent's local policy blocks it.

```json

{
  "jsonrpc": "2.0",
  "error": {
    "code": -32003,
    "message": "Security Violation: Action requires HITL Approval.",
    "data": {
      "policy_rule": "restart_service_requires_approval",
      "remediation": "Request admin approval via Dashboard."
    }
  },
  "id": "req-101"
}
```

<br>

## Frontend <-> Backend API
Protocol: HTTP REST + WebSocket (for live updates)

| Category | Method | Endpoint | Description |
| :--- | :--- | :--- | :--- |
| Auth | POST | /auth/login | Login (returns JWT). |
| POST | /auth/logout | Invalidate session. |
| Agents | GET | /agents | List all agents (Live status). |
| GET | /agents/{id}/details | Hardware, OS, and Security Policy info. |
| POST | /agents/{id}/command | Manual tool execution (Bypasses LLM). |
| Orchestrator | POST | /orchestrator/chat | Send prompt to AI. |
| POST | /orchestrator/approve | HITL: Approve a pending action. |
| POST | /orchestrator/deny | HITL: Deny a pending action. |
| GET | /orchestrator/pending | List actions waiting for approval. |
| Scheduler | GET | /scheduler/jobs | List active Cron jobs. |
| POST | /scheduler/jobs | Create a new scheduled task (e.g., "Daily Disk Check"). |
| DELETE | /scheduler/jobs/{id} | Cancel a job. |
| Files | POST | /files/upload | Upload script/installer to Server. |
| GET | /files/list | List available artifacts. |
| GET | /files/{name} | Download file (Used by Agents). |
| Settings | GET | /settings/global | Get API Keys, Thresholds, Email configs. |
| PUT | /settings/global | Update settings. |
| GET | /settings/notifications | Test Email/Slack/SMS alerts. |
| Models | GET | /models/available | List downloadable open-source models. |
| | POST | /models/download | Queue a model for download. |
| | GET | /models/local | List locally installed models. |
| | DELETE | /models/{id} | Remove a local model. |
| Chat History | GET | /chat/sessions | List all chat sessions. |
| | GET | /chat/sessions/{id}/messages | Retrieve messages for a session. |
| | DELETE | /chat/sessions/{id} | Delete a chat session. |


<br>

## Go Internal Interfaces (Agent)

Syscall Interface (internal/sys/syscall.go)

```go 
type SystemOps interface {
    ExecCommand(cmd string, args []string, timeout time.Duration) (string, error)
    GetSystemResources() (CPUStats, RAMStats, DiskStats, error)
    DownloadFile(url string, destPath string, hash string) error
    ManageService(action string, serviceName string) error
}
```


MCP Manager Interface (internal/mcp/manager.go)

```go
type MCPManager interface {
    // Looks for 'mcp_config.json' or standard paths for servers
    ScanLocalServers() ([]ServerConfig, error) 
    
    // Wraps the JSON-RPC message and sends it to the stdio pipe of the target tool
    ProxyRequest(serverName string, request JSONRPCRequest) (JSONRPCResponse, error)
}
```
Security Manager Interface (internal/security/manager.go)

```go
type SecurityOps interface {
    // Returns true if the action is safe to run immediately
    ValidateAction(toolName string, args map[string]interface{}) (bool, Reason)
    
    // Checks if the incoming request has a valid cryptographic approval signature (optional)
    VerifyApproval(token string) bool
}
```

