package transport

import (
	"encoding/json"
	"log"
	"net/url"
	"os"
	"os/signal"
	"runtime"
	"time"

	"github.com/fabricore/agent/internal/config"
	"github.com/fabricore/agent/internal/mcp"
	"github.com/fabricore/agent/internal/tools"
	"github.com/gorilla/websocket"
)

type Client struct {
	config     *config.Config
	conn       *websocket.Conn
	dispatcher *mcp.Dispatcher
}

func NewClient(cfg *config.Config) *Client {
	// Initialize Tools
	registry := tools.NewRegistry()
	registry.Register(&tools.ListFilesTool{})

	dispatcher := mcp.NewDispatcher(registry)

	return &Client{
		config:     cfg,
		dispatcher: dispatcher,
	}
}

func (c *Client) Connect() error {
	// Generate Agent ID (simple version)
	hostname, _ := os.Hostname()
	agentID := "agent-" + hostname

	// Construct URL with Agent ID
	// Assumes ServerURL ends with /ws or equivalent base
	// In a real app we'd handle trailing slashes more robustly
	fullURL := c.config.ServerURL + "/" + agentID

	u, err := url.Parse(fullURL)
	if err != nil {
		return err
	}

	log.Printf("Connecting to %s", u.String())

	conn, _, err := websocket.DefaultDialer.Dial(u.String(), nil)
	if err != nil {
		return err
	}
	c.conn = conn
	defer c.conn.Close()

	log.Println("Connected to server")

	// Handshake
	if err := c.sendIdentity(agentID); err != nil {
		log.Printf("Failed to send identity: %v", err)
		return err
	}

	// Simple loop
	done := make(chan struct{})

	go func() {
		defer close(done)
		for {
			_, message, err := c.conn.ReadMessage()
			if err != nil {
				log.Println("read:", err)
				return
			}
			log.Printf("recv: %s", message)

			// Process Message via Dispatcher
			response := c.dispatcher.ProcessMessage(message)
			if response != nil {
				respBytes, err := json.Marshal(response)
				if err != nil {
					log.Printf("Failed to marshal response: %v", err)
					continue
				}
				if err := c.conn.WriteMessage(websocket.TextMessage, respBytes); err != nil {
					log.Printf("Failed to write response: %v", err)
					return
				}
			}
		}
	}()

	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	interrupt := make(chan os.Signal, 1)
	signal.Notify(interrupt, os.Interrupt)

	for {
		select {
		case <-done:
			return nil
		case <-ticker.C:
			// Heartbeat
			hb := mcp.JSONRPCRequest{
				JSONRPC: "2.0",
				Method:  "agent.heartbeat",
				ID:      0, // Notification or 0
			}
			data, _ := json.Marshal(hb)
			err := c.conn.WriteMessage(websocket.TextMessage, data)
			if err != nil {
				log.Println("write:", err)
				return err
			}
		case <-interrupt:
			log.Println("interrupt")
			err := c.conn.WriteMessage(websocket.CloseMessage, websocket.FormatCloseMessage(websocket.CloseNormalClosure, ""))
			if err != nil {
				log.Println("write close:", err)
				return err
			}
			select {
			case <-done:
			case <-time.After(time.Second):
			}
			return nil
		}
	}
}

func (c *Client) sendIdentity(agentID string) error {
	hostname, _ := os.Hostname()

	identity := mcp.AgentIdentity{
		AgentID: agentID,
		Token:   c.config.Token,
		OSInfo: mcp.OSInfo{
			Platform:    runtime.GOOS,
			Hostname:    hostname,
			Arch:        runtime.GOARCH,
			MemoryTotal: 0,
		},
		SupportedTools: c.dispatcher.Registry.ToolList(),
	}

	request := mcp.JSONRPCRequest{
		JSONRPC: "2.0",
		Method:  "agent.identify",
		Params:  identity,
		ID:      1,
	}

	data, err := json.Marshal(request)
	if err != nil {
		return err
	}

	return c.conn.WriteMessage(websocket.TextMessage, data)
}

func (c *Client) Disconnect() {
	if c.conn != nil {
		c.conn.Close()
	}
}
