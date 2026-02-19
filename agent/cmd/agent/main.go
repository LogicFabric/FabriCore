package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

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
	if *token != "" {
		log.Printf("[INFO] Token: %s***", (*token)[:min(4, len(*token))])
	}

	if *token == "" {
		log.Fatal("[ERROR] Token is required. Use --token <your-token>")
	}

	// Setup context with signal handling
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	// Initialize Components
	log.Println("[INFO] Initializing components...")
	systemOps := sys.NewRealSystem()
	mcpManager := mcp.NewManager()
	secManager := security.NewManager()

	// Initialize Orchestrator
	orch := orchestrator.New(*serverURL, *token, systemOps, mcpManager, secManager)

	// Start Agent with retry logic
	log.Println("[INFO] Starting agent service loop...")
	for {
		err := orch.Start(ctx)
		if err != nil {
			if ctx.Err() != nil {
				log.Println("[INFO] Agent shutting down gracefully.")
				break
			}
			log.Printf("[ERROR] Agent connection failed: %v", err)
			log.Println("[INFO] Retrying in 10 seconds...")

			select {
			case <-time.After(10 * time.Second):
				log.Println("[INFO] Reconnection attempt...")
			case <-ctx.Done():
				log.Println("[INFO] Agent shutting down gracefully.")
				return
			}
		} else {
			// If Start returns nil, it might have been a clean exit or unexpected
			if ctx.Err() != nil {
				break
			}
			log.Println("[WARN] Orchestrator stopped unexpectedly without error. Retrying in 10s...")
			time.Sleep(10 * time.Second)
		}
	}
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
