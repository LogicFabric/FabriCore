package security

import (
	"encoding/json"
	"fmt"
	"regexp"

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
			Rules: []types.SecurityRule{
				{ToolName: "exec_command", ArgPattern: "^rm -rf /$", Action: "block"},
				{ToolName: "exec_command", ArgPattern: "^mkfs.*", Action: "block"},
				{ToolName: "exec_command", ArgPattern: "^dd.*", Action: "block"},
				{ToolName: "restart_service", ArgPattern: ".*", Action: "require_approval"},
				{ToolName: "write_file", ArgPattern: ".*", Action: "require_approval"},
			},
			Default: "allow", // Default to allow for now, can be strict "block" later
		},
	}
}

func (m *RealManager) ValidateAction(toolName string, args interface{}) (bool, error) {
	// Convert args to string for regex matching
	// For exec_command, args is a struct, but we need the command string
	var argsStr string

	// Attempt to marshal args to string to match against pattern
	// In a real scenario, we might want deeper inspection of specific fields
	// For now, we'll try to extract the "command" if it exists, or just marshal the whole thing
	bytes, err := json.Marshal(args)
	if err == nil {
		argsStr = string(bytes)
	}

	// 1. Iterate through Rules
	for _, rule := range m.policy.Rules {
		if rule.ToolName == toolName {
			matched, err := regexp.MatchString(rule.ArgPattern, argsStr)
			if err != nil {
				continue // Invalid regex in policy?
			}

			if matched {
				switch rule.Action {
				case "block":
					return false, fmt.Errorf("action blocked by security policy")
				case "require_approval":
					// We need to check if approval is present.
					// Since ValidateAction interface signature currently doesn't accept the full context (like params),
					// we are limited here. However, the Orchestrator calls this.
					// The Orchestrator should interpret a specific error from here.
					return false, fmt.Errorf("E_REQUIRES_APPROVAL")
				case "allow":
					return true, nil
				}
			}
		}
	}

	// 2. Default Action
	if m.policy.Default == "block" {
		return false, fmt.Errorf("action blocked by default policy")
	}

	return true, nil
}

func (m *RealManager) GetPolicy() types.SecurityPolicy {
	return m.policy
}
