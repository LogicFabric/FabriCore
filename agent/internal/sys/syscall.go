package sys

import (
	"bytes"
	"context"
	"fmt"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"time"

	"github.com/fabricore/agent/internal/types"
)

type SystemOps interface {
	ExecCommand(cmd string, args []string, timeout int) (string, error)
	GetSystemInfo() types.OSInfo
}

type RealSystem struct{}

func NewRealSystem() *RealSystem {
	return &RealSystem{}
}

func (s *RealSystem) ExecCommand(cmd string, args []string, timeout int) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeout)*time.Second)
	defer cancel()

	command := exec.CommandContext(ctx, cmd, args...)
	var stdout, stderr bytes.Buffer
	command.Stdout = &stdout
	command.Stderr = &stderr

	err := command.Run()

	if ctx.Err() == context.DeadlineExceeded {
		return "", fmt.Errorf("command timed out after %d seconds", timeout)
	}

	if err != nil {
		return "", fmt.Errorf("command failed: %v, stderr: %s", err, stderr.String())
	}

	return stdout.String(), nil
}

func (s *RealSystem) GetSystemInfo() types.OSInfo {
	hostname, _ := os.Hostname()
	uptime := getUptime()

	return types.OSInfo{
		Platform:      runtime.GOOS,
		Hostname:      hostname,
		Arch:          runtime.GOARCH,
		Release:       getRelease(),
		UptimeSeconds: uptime,
	}
}

func getUptime() uint64 {
	// Simple Linux implementation
	data, err := os.ReadFile("/proc/uptime")
	if err != nil {
		return 0
	}
	parts := strings.Fields(string(data))
	if len(parts) > 0 {
		var uptime float64
		fmt.Sscanf(parts[0], "%f", &uptime)
		return uint64(uptime)
	}
	return 0
}

func getRelease() string {
	// Simple Linux implementation
	data, err := os.ReadFile("/etc/os-release")
	if err == nil {
		lines := strings.Split(string(data), "\n")
		for _, line := range lines {
			if strings.HasPrefix(line, "PRETTY_NAME=") {
				return strings.Trim(strings.TrimPrefix(line, "PRETTY_NAME="), "\"")
			}
		}
	}
	return "Unknown"
}
