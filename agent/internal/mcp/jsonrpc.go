package mcp

import (
	"encoding/json"
	"log"

	"github.com/fabricore/agent/internal/tools"
)

type Dispatcher struct {
	Registry *tools.Registry
}

func NewDispatcher(registry *tools.Registry) *Dispatcher {
	return &Dispatcher{
		Registry: registry,
	}
}

// ProcessMessage handles raw incoming JSON-RPC messages
func (d *Dispatcher) ProcessMessage(msg []byte) *JSONRPCResponse {
	var req JSONRPCRequest
	if err := json.Unmarshal(msg, &req); err != nil {
		log.Printf("Invalid JSON: %v", err)
		return nil // Or return Parse Error
	}

	// If it's a response to a request WE sent, we might ignore it or handle it elsewhere.
	// For this phase, we assume everything is a request FROM the server.
	if req.Method == "" {
		return nil
	}

	switch req.Method {
	case "tool.execute":
		return d.handleToolExecute(req)
	default:
		return &JSONRPCResponse{
			JSONRPC: "2.0",
			ID:      req.ID,
			Error: &JSONRPCError{
				Code:    -32601,
				Message: "Method not found",
			},
		}
	}
}

func (d *Dispatcher) handleToolExecute(req JSONRPCRequest) *JSONRPCResponse {
	// Parse Params
	// Expecting params to be a map or a struct matching our schema
	// Since req.Params is interface{}, we need to marshal/unmarshal or type assert carefully

	// Quick hack: marshal params back to json and unmarshal to a struct
	paramBytes, _ := json.Marshal(req.Params)
	var toolParams struct {
		ToolName  string                 `json:"tool_name"`
		Arguments map[string]interface{} `json:"arguments"`
	}
	if err := json.Unmarshal(paramBytes, &toolParams); err != nil {
		return &JSONRPCResponse{
			JSONRPC: "2.0",
			ID:      req.ID,
			Error: &JSONRPCError{
				Code:    -32602,
				Message: "Invalid params",
			},
		}
	}

	log.Printf("Executing tool: %s", toolParams.ToolName)

	result, err := d.Registry.ExecuteTool(toolParams.ToolName, toolParams.Arguments)
	if err != nil {
		return &JSONRPCResponse{
			JSONRPC: "2.0",
			ID:      req.ID,
			Error: &JSONRPCError{
				Code:    -32000,
				Message: err.Error(),
			},
		}
	}

	return &JSONRPCResponse{
		JSONRPC: "2.0",
		ID:      req.ID,
		Result:  result,
	}
}
