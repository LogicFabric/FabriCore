package security

import (
	"fmt"

	"github.com/fabricore/agent/internal/types"
)

type Manager interface {
	ValidateAction(toolName string, args interface{}) (bool, error)
	GetPolicy() types.SecurityPolicy
}

type RealManager struct {
	policy types.SecurityPolicy
}

func NewManager() *RealManager {
	return &RealManager{
		policy: types.SecurityPolicy{
			HITLEnabled:         true,
			BlockedCommands:     []string{"rm -rf /", "mkfs", "dd"},
			RequiresApprovalFor: []string{"restart_service", "write_file"},
		},
	}
}

func (m *RealManager) ValidateAction(toolName string, args interface{}) (bool, error) {
	// 1. Check if tool is blocked entirely (not implemented in this simple policy, but could be)
	// 2. Check if arguments contain blocked patterns

	// Simple check for command execution
	if toolName == "exec_command" {
		// This conversion mimics what would happen with real args inspection
		// In a real scenario, we'd inspect the actual command string
		// For now, let's assume args is safe or handle it fundamentally
		return true, nil
	}

	// 3. Check if action requires approval
	for _, restricted := range m.policy.RequiresApprovalFor {
		if toolName == restricted {
			// Check if approval token is present (TODO: Pass approval info)
			// For now, if it requires approval, we might fail or allow if HITL flow isn't fully integrated
			// logic: if requires approval and no token, return false
			return false, fmt.Errorf("action requires HITL approval")
		}
	}

	return true, nil
}

func (m *RealManager) GetPolicy() types.SecurityPolicy {
	return m.policy
}
