package mcp

import (
	"encoding/json"
	"os"

	"github.com/fabricore/agent/internal/types"
)

type Manager interface {
	ScanLocalServers() ([]types.MCPServerInfo, error)
	ProxyRequest(serverName string, request types.JSONRPCRequest) (types.JSONRPCResponse, error)
}

type RealManager struct {
	servers map[string]types.MCPServerInfo
}

func NewManager() *RealManager {
	return &RealManager{
		servers: make(map[string]types.MCPServerInfo),
	}
}

func (m *RealManager) ScanLocalServers() ([]types.MCPServerInfo, error) {
	// Try to read mcp_config.json
	data, err := os.ReadFile("mcp_config.json")
	if err == nil {
		var servers []types.MCPServerInfo
		if err := json.Unmarshal(data, &servers); err == nil {
			for _, s := range servers {
				m.servers[s.Name] = s
			}
			return servers, nil
		}
	}
	return []types.MCPServerInfo{}, nil
}

func (m *RealManager) ProxyRequest(serverName string, request types.JSONRPCRequest) (types.JSONRPCResponse, error) {
	// TODO: Implement actual transport (Stdio/SSE)
	// For now, return a placeholder error
	return types.JSONRPCResponse{
		JSONRPC: "2.0",
		ID:      request.ID,
		Error: &types.JSONRPCError{
			Code:    -32603,
			Message: "MCP Proxy not implemented yet",
		},
	}, nil
}
