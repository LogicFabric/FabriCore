package types

import (
	"encoding/json"
)

// JSON-RPC 2.0 Constants
const (
	JSONRPCVersion = "2.0"
)

// JSONRPCRequest represents a JSON-RPC 2.0 request
type JSONRPCRequest struct {
	JSONRPC string          `json:"jsonrpc"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params,omitempty"`
	ID      interface{}     `json:"id"` // string or int
}

// JSONRPCResponse represents a JSON-RPC 2.0 response
type JSONRPCResponse struct {
	JSONRPC string          `json:"jsonrpc"`
	Result  json.RawMessage `json:"result,omitempty"`
	Error   *JSONRPCError   `json:"error,omitempty"`
	ID      interface{}     `json:"id"`
}

// JSONRPCError represents a JSON-RPC 2.0 error
type JSONRPCError struct {
	Code    int             `json:"code"`
	Message string          `json:"message"`
	Data    json.RawMessage `json:"data,omitempty"`
}

func (e *JSONRPCError) Error() string {
	return e.Message
}

// AgentIdentity represents the parameters for agent.identify
type AgentIdentity struct {
	AgentID        string          `json:"agent_id"`
	Token          string          `json:"token"`
	OSInfo         OSInfo          `json:"os_info"`
	Capabilities   Capabilities    `json:"capabilities"`
	MCPServers     []MCPServerInfo `json:"mcp_servers"`
	SecurityPolicy SecurityPolicy  `json:"security_policy"`
}

type OSInfo struct {
	Platform      string `json:"platform"`
	Hostname      string `json:"hostname"`
	Arch          string `json:"arch"`
	Release       string `json:"release"`
	UptimeSeconds uint64 `json:"uptime_seconds"`
}

type Capabilities struct {
	NativeTools  []string `json:"native_tools"`
	FileTransfer bool     `json:"file_transfer"`
	PTYSupport   bool     `json:"pty_support"`
}

type MCPServerInfo struct {
	Name      string   `json:"name"`
	Transport string   `json:"transport"`
	Command   []string `json:"command,omitempty"`
	URL       string   `json:"url,omitempty"`
	Status    string   `json:"status"`
}

type SecurityRule struct {
	ToolName   string `json:"tool_name"`
	ArgPattern string `json:"arg_pattern"` // Regex (e.g., "^rm.*" or ".*")
	Action     string `json:"action"`      // "allow", "block", "require_approval"
}

type SecurityPolicy struct {
	Rules   []SecurityRule `json:"rules"`
	Default string         `json:"default_action"` // "block" is safest
}

// ToolExecuteParams represents parameters for tool.execute
type ToolExecuteParams struct {
	ToolName    string          `json:"tool_name"`
	Arguments   json.RawMessage `json:"arguments"`
	ExecutionID string          `json:"execution_id"`
	ApprovedBy  string          `json:"approved_by,omitempty"`
}

// MCPProxyParams represents parameters for mcp.proxy
type MCPProxyParams struct {
	TargetServer string         `json:"target_server"`
	InnerRequest JSONRPCRequest `json:"inner_request"`
}
