package orchestrator

import (
	"encoding/json"
	"fmt"
	"log"
	"net/url"
	"os"
	"os/signal"
	"time"

	"github.com/fabricore/agent/internal/mcp"
	"github.com/fabricore/agent/internal/security"
	"github.com/fabricore/agent/internal/sys"
	"github.com/fabricore/agent/internal/types"

	"github.com/gorilla/websocket"
)

type Orchestrator struct {
	serverURL string
	token     string
	agentID   string
	conn      *websocket.Conn
	sys       sys.SystemOps
	mcp       mcp.Manager
	security  security.Manager
	done      chan struct{}
}

func New(serverURL, token string, sys sys.SystemOps, mcp mcp.Manager, sec security.Manager) *Orchestrator {
	return &Orchestrator{
		serverURL: serverURL,
		token:     token,
		agentID:   "agent-" + token[:8], // TODO: Generate proper ID
		sys:       sys,
		mcp:       mcp,
		security:  sec,
		done:      make(chan struct{}),
	}
}

func (o *Orchestrator) Start() error {
	u, err := url.Parse(o.serverURL)
	if err != nil {
		log.Printf("[ERROR] Invalid server URL: %v", err)
		return err
	}

	log.Printf("[INFO] Connecting to server: %s", u.String())
	log.Printf("[INFO] Agent ID: %s", o.agentID)

	c, resp, err := websocket.DefaultDialer.Dial(u.String(), nil)
	if err != nil {
		if resp != nil {
			log.Printf("[ERROR] Connection failed with HTTP status: %d", resp.StatusCode)
		}
		log.Printf("[ERROR] WebSocket dial failed: %v", err)
		return err
	}
	o.conn = c
	defer c.Close()

	log.Println("[OK] WebSocket connection established successfully!")

	// Send Handshake
	log.Println("[INFO] Sending agent.identify handshake...")
	if err := o.sendHandshake(); err != nil {
		log.Printf("[ERROR] Handshake failed: %v", err)
		return fmt.Errorf("handshake failed: %w", err)
	}
	log.Println("[OK] Handshake sent successfully. Waiting for server commands...")

	// Main Loop
	interrupt := make(chan os.Signal, 1)
	signal.Notify(interrupt, os.Interrupt)

	go func() {
		defer close(o.done)
		for {
			_, message, err := c.ReadMessage()
			if err != nil {
				log.Printf("[WARN] Read error (connection may have closed): %v", err)
				return
			}
			log.Printf("[DEBUG] Received message: %s", string(message))
			go o.handleMessage(message)
		}
	}()

	select {
	case <-interrupt:
		log.Println("[INFO] Interrupt received (Ctrl+C), shutting down gracefully...")
		err := c.WriteMessage(websocket.CloseMessage, websocket.FormatCloseMessage(websocket.CloseNormalClosure, ""))
		if err != nil {
			log.Println("write close:", err)
			return nil
		}
		select {
		case <-o.done:
		case <-time.After(time.Second):
		}
	case <-o.done:
		log.Println("[WARN] Server connection closed unexpectedly.")
	}

	return nil
}

func (o *Orchestrator) sendHandshake() error {
	sysInfo := o.sys.GetSystemInfo()
	mcpServers, _ := o.mcp.ScanLocalServers()
	policy := o.security.GetPolicy()

	identity := types.AgentIdentity{
		AgentID: o.agentID,
		Token:   o.token,
		OSInfo:  sysInfo,
		Capabilities: types.Capabilities{
			NativeTools:  []string{"exec_command", "get_system_info"}, // Dynamic later
			FileTransfer: true,
			PTYSupport:   true,
		},
		MCPServers:     mcpServers,
		SecurityPolicy: policy,
	}

	// Wrap in JSONRPCRequest
	params, _ := json.Marshal(identity)
	req := types.JSONRPCRequest{
		JSONRPC: "2.0",
		Method:  "agent.identify",
		Params:  params,
		ID:      1,
	}

	return o.conn.WriteJSON(req)
}

func (o *Orchestrator) handleMessage(msg []byte) {
	var req types.JSONRPCRequest
	if err := json.Unmarshal(msg, &req); err != nil {
		log.Printf("Failed to parse message: %v", err)
		return
	}

	log.Printf("Received method: %s", req.Method)

	var response types.JSONRPCResponse
	response.JSONRPC = "2.0"
	response.ID = req.ID

	switch req.Method {
	case "tool.execute":
		result, err := o.handleToolExecute(req.Params)
		if err != nil {
			// Check if it's our special error type
			if jsonErr, ok := err.(*types.JSONRPCError); ok {
				response.Error = jsonErr
			} else {
				response.Error = &types.JSONRPCError{
					Code:    -32603,
					Message: err.Error(),
				}
			}
		} else {
			response.Result = result
		}
	case "mcp.proxy":
		// TODO: Implement MCP Proxy
		result, err := o.handleMCPProxy(req.Params)
		if err != nil {
			response.Error = &types.JSONRPCError{Code: -32603, Message: err.Error()}
		} else {
			response.Result = result
		}
	default:
		response.Error = &types.JSONRPCError{
			Code:    -32601,
			Message: "Method not found",
		}
	}

	o.conn.WriteJSON(response)
}

func (o *Orchestrator) handleToolExecute(paramsRaw json.RawMessage) (json.RawMessage, error) {
	var params types.ToolExecuteParams
	if err := json.Unmarshal(paramsRaw, &params); err != nil {
		return nil, err
	}

	// UPDATED: Pass params.ApprovedBy
	allowed, err := o.security.ValidateAction(params.ToolName, params.Arguments, params.ApprovedBy)
	if err != nil {
		// UPDATED: Check for specific approval error
		if err.Error() == "E_REQUIRES_APPROVAL" {
			// Return JSON-RPC error with specific code -32001
			return nil, &types.JSONRPCError{
				Code:    -32001,
				Message: "Action requires human approval",
				Data:    json.RawMessage(fmt.Sprintf(`{"execution_id": "%s"}`, params.ExecutionID)),
			}
		}
		// Normal block
		return nil, fmt.Errorf("security policy validation failed: %v", err)
	}

	if !allowed {
		return nil, fmt.Errorf("security policy validation failed")
	}

	switch params.ToolName {
	case "exec_command":
		var args struct {
			Command string   `json:"command"`
			Args    []string `json:"args"`
			Timeout int      `json:"timeout"`
		}
		if err := json.Unmarshal(params.Arguments, &args); err != nil {
			return nil, err
		}
		output, err := o.sys.ExecCommand(args.Command, args.Args, args.Timeout)
		if err != nil {
			return nil, err
		}
		return json.Marshal(map[string]string{"output": output})
	default:
		return nil, fmt.Errorf("unknown tool: %s", params.ToolName)
	}
}

// ADD THIS NEW FUNCTION
func (o *Orchestrator) handleUpdatePolicy(paramsRaw json.RawMessage) (json.RawMessage, error) {
	var params struct {
		Policy types.SecurityPolicy `json:"policy"`
	}
	if err := json.Unmarshal(paramsRaw, &params); err != nil {
		return nil, err
	}

	// Apply the policy
	o.security.UpdatePolicy(params.Policy)
	log.Printf("[INFO] Security policy updated. Rules: %d", len(params.Policy.Rules))

	return json.Marshal(map[string]string{"status": "updated"})
}

// UPDATE THE SWITCH STATEMENT
func (o *Orchestrator) handleMessageNew(msg []byte) {
	var req types.JSONRPCRequest
	if err := json.Unmarshal(msg, &req); err != nil {
		log.Printf("Failed to parse message: %v", err)
		return
	}

	log.Printf("Received method: %s", req.Method)

	var response types.JSONRPCResponse
	response.JSONRPC = "2.0"
	response.ID = req.ID

	switch req.Method {
	case "tool.execute":
		result, err := o.handleToolExecute(req.Params)
		if err != nil {
			// Check if it's our special error type
			if jsonErr, ok := err.(*types.JSONRPCError); ok {
				response.Error = jsonErr
			} else {
				response.Error = &types.JSONRPCError{
					Code:    -32603,
					Message: err.Error(),
				}
			}
		} else {
			response.Result = result
		}
	case "mcp.proxy":
		// TODO: Implement MCP Proxy
		result, err := o.handleMCPProxy(req.Params)
		if err != nil {
			response.Error = &types.JSONRPCError{Code: -32603, Message: err.Error()}
		} else {
			response.Result = result
		}
	case "agent.update_policy":
		result, err := o.handleUpdatePolicy(req.Params)
		if err != nil {
			response.Error = &types.JSONRPCError{Code: -32603, Message: err.Error()}
		} else {
			response.Result = result
		}
	default:
		response.Error = &types.JSONRPCError{
			Code:    -32601,
			Message: "Method not found",
		}
	}

	o.conn.WriteJSON(response)
}

func (o *Orchestrator) handleMCPProxy(paramsRaw json.RawMessage) (json.RawMessage, error) {
	var params types.MCPProxyParams
	if err := json.Unmarshal(paramsRaw, &params); err != nil {
		return nil, err
	}

	resp, err := o.mcp.ProxyRequest(params.TargetServer, params.InnerRequest)
	if err != nil {
		return nil, err
	}
	return json.Marshal(resp)
}
