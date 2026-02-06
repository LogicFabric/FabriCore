package tools

import (
	"fmt"
	"sync"
)

// Tool represents a capability of the agent.
type Tool interface {
	Name() string
	Execute(args map[string]interface{}) (interface{}, error)
}

// Registry manages the available tools.
type Registry struct {
	tools map[string]Tool
	mu    sync.RWMutex
}

// NewRegistry creates a new tool registry.
func NewRegistry() *Registry {
	return &Registry{
		tools: make(map[string]Tool),
	}
}

// Register adds a tool to the registry.
func (r *Registry) Register(t Tool) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.tools[t.Name()] = t
}

// GetTool retrieves a tool by name.
func (r *Registry) GetTool(name string) (Tool, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	t, ok := r.tools[name]
	if !ok {
		return nil, fmt.Errorf("tool not found: %s", name)
	}
	return t, nil
}

// ToolList returns a list of registered tool names.
func (r *Registry) ToolList() []string {
	r.mu.RLock()
	defer r.mu.RUnlock()
	var names []string
	for name := range r.tools {
		names = append(names, name)
	}
	return names
}

// ExecuteTool helper to find and execute a tool safely.
func (r *Registry) ExecuteTool(name string, args map[string]interface{}) (interface{}, error) {
	tool, err := r.GetTool(name)
	if err != nil {
		return nil, err
	}
	return tool.Execute(args)
}
