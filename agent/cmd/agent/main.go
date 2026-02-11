package main

import (
	"flag"
	"fmt"
	"log"
	"os"

	"github.com/fabricore/agent/internal/mcp"
	"github.com/fabricore/agent/internal/orchestrator"
	"github.com/fabricore/agent/internal/security"
	"github.com/fabricore/agent/internal/sys"
)

func main() {
	// Immediate startup message
	fmt.Println("╔═══════════════════════════════════════════╗")
	fmt.Println("║       FabriCore Agent v0.1.0              ║")
	fmt.Println("╚═══════════════════════════════════════════╝")

	serverURL := flag.String("server", "ws://localhost:8000/api/v1/ws", "Server WebSocket URL")
	token := flag.String("token", "", "Authentication Token")
	flag.Parse()

	log.Println("[INFO] Parsing command line arguments...")
	log.Printf("[INFO] Server URL: %s", *serverURL)
	log.Printf("[INFO] Token: %s***", (*token)[:min(4, len(*token))])

	if *token == "" {
		log.Fatal("[ERROR] Token is required. Use --token <your-token>")
	}

	// Initialize Components
	log.Println("[INFO] Initializing components...")
	systemOps := sys.NewRealSystem()
	mcpManager := mcp.NewManager()
	secManager := security.NewManager()

	// Initialize Orchestrator
	orch := orchestrator.New(*serverURL, *token, systemOps, mcpManager, secManager)

	// Start Agent
	log.Println("[INFO] Starting agent connection...")
	if err := orch.Start(); err != nil {
		log.Fatalf("[FATAL] Agent failed: %v", err)
		os.Exit(1)
	}
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
