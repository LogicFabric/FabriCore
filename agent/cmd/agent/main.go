package main

import (
	"flag"
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/fabricore/agent/internal/config"
	"github.com/fabricore/agent/internal/transport"
)

func main() {
	serverURL := flag.String("server", "ws://localhost:8000/api/v1/ws", "Server WebSocket URL")
	token := flag.String("token", "", "Authentication token")
	flag.Parse()

	if *token == "" {
		// In a real scenario we might require a token, or load from config
		log.Println("Warning: No token provided")
	}

	cfg := &config.Config{
		ServerURL: *serverURL,
		Token:     *token,
	}

	client := transport.NewClient(cfg)

	// Handle graceful shutdown
	interrupt := make(chan os.Signal, 1)
	signal.Notify(interrupt, os.Interrupt, syscall.SIGTERM)

	go func() {
		if err := client.Connect(); err != nil {
			log.Fatalf("Failed to connect: %v", err)
		}
	}()

	<-interrupt
	log.Println("Shutting down agent...")
	client.Disconnect()
}
