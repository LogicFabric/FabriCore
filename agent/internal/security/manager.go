package security

import (
	"encoding/json"
	"fmt"
	"regexp"
	"sync"

	"github.com/fabricore/agent/internal/types"
)

type Manager interface {
	// UPDATED: Now accepts approvedBy string
	ValidateAction(toolName string, args interface{}, approvedBy string) (bool, error)
	GetPolicy() types.SecurityPolicy
	UpdatePolicy(policy types.SecurityPolicy)
}

type RealManager struct {
	policy types.SecurityPolicy
	mu     sync.RWMutex // Add Mutex for thread safety
}

func NewManager() *RealManager {
	return &RealManager{
		policy: types.SecurityPolicy{
			Rules: []types.SecurityRule{
				{ToolName: "exec_command", ArgPattern: "^rm -rf /$", Action: "block"},
				{ToolName: "restart_service", ArgPattern: ".*", Action: "require_approval"},
				// Add more default rules here
			},
			Default: "allow",
		},
	}
}

// ADD THIS METHOD
func (m *RealManager) UpdatePolicy(policy types.SecurityPolicy) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.policy = policy
}

func (m *RealManager) ValidateAction(toolName string, args interface{}, approvedBy string) (bool, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()

	var argsStr string
	bytes, err := json.Marshal(args)
	if err == nil {
		argsStr = string(bytes)
	}

	for _, rule := range m.policy.Rules {
		if rule.ToolName == toolName {
			matched, err := regexp.MatchString(rule.ArgPattern, argsStr)
			if err != nil {
				continue
			}

			if matched {
				switch rule.Action {
				case "block":
					return false, fmt.Errorf("action blocked by security policy")
				case "require_approval":
					// CHECK APPROVAL TOKEN
					if approvedBy != "" {
						// In production, you would verify a cryptographic signature here.
						// For now, presence of the token (injected by server after HITL) is the check.
						return true, nil
					}
					return false, fmt.Errorf("E_REQUIRES_APPROVAL")
				case "allow":
					return true, nil
				}
			}
		}
	}

	if m.policy.Default == "block" {
		return false, fmt.Errorf("action blocked by default policy")
	}

	return true, nil
}

func (m *RealManager) GetPolicy() types.SecurityPolicy {
	return m.policy
}
