package mcp

// JSONRPCRequest represents a JSON-RPC 2.0 request
type JSONRPCRequest struct {
	JSONRPC string      `json:"jsonrpc"`
	Method  string      `json:"method"`
	Params  interface{} `json:"params,omitempty"`
	ID      interface{} `json:"id"`
}

// JSONRPCResponse represents a JSON-RPC 2.0 response
type JSONRPCResponse struct {
	JSONRPC string        `json:"jsonrpc"`
	Result  interface{}   `json:"result,omitempty"`
	Error   *JSONRPCError `json:"error,omitempty"`
	ID      interface{}   `json:"id"`
}

// JSONRPCError represents a JSON-RPC 2.0 error
type JSONRPCError struct {
	Code    int         `json:"code"`
	Message string      `json:"message"`
	Data    interface{} `json:"data,omitempty"`
}

// OSInfo represents operating system information
type OSInfo struct {
	Platform    string `json:"platform"`
	Hostname    string `json:"hostname"`
	Arch        string `json:"arch"`
	MemoryTotal uint64 `json:"memory_total"`
}

// AgentIdentity represents the parameters for the agent.identify method
type AgentIdentity struct {
	AgentID        string   `json:"agent_id"`
	Token          string   `json:"token"`
	OSInfo         OSInfo   `json:"os_info"`
	SupportedTools []string `json:"supported_tools"`
}
