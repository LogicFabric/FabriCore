# 🤖 FABRICORE: AI AGENT OPERATING INSTRUCTIONS (v3)

> **SYSTEM OVERRIDE DIRECTIVE:** You are an elite AI Architect. You are working in a multi-model environment where other AIs will touch this code after you. You MUST read and obey this document. 

## 0. 🌟 PROJECT OVERVIEW & PURPOSE: AI-POWERED RMM ORCHESTRATOR
**FabriCore** is a next-generation Remote Monitoring & Management (RMM) platform powered by agentic AI. It allows system administrators to orchestrate, monitor, and automate a fleet of machines using natural language and AI-driven cron jobs. 

The system utilizes a strict **Hub-and-Spoke** architecture divided into two core components:
* **🧠 The Server (The Hub):** A containerized Python backend that hosts the central WebUI and runs the local AI inference engine (GGUF models via `llama.cpp` in Docker). The WebUI serves as the central command center to manage the fleet, schedule AI automation jobs (cron), and oversee system logs.
* **⚙️ The Agents (The Spokes):** High-performance, cross-platform native binaries written in Go. Agents run directly on the host operating systems of the target machines. They receive instructions via secure WebSockets, execute system commands on behalf of the AI, and stream the results back to the server.

**The Core Paradigm (Security First):** Because the AI can execute direct system commands via the Go agents, security is the top priority. The platform relies heavily on **HITL (Human-in-the-Loop)** mechanics. Administrators use the WebUI to define strict security boundaries, approve sensitive execution steps, and monitor the AI's exact system calls (JSON-RPC) in real-time.

## 1. 🏷️ THE AI SEMANTIC TAGGING PROTOCOL (The Legend)
When reading or writing code in this repository, you must obey and utilize these tags in the comments:

* `@AI-LOCKED`: **[RESTRICTIVE]** Do not modify this logic. It exists for a specific historical reason (e.g., avoiding integer overflow in DB, Quasar dark mode sync). If you absolutely must change it, you must explicitly ask the user.
* `@AI-CONTRACT`: **[CAUTION]** This is an interface (WebSocket schema, DB Model, API endpoint, CLI arg). If you change this, you MUST also change the system that consumes it (e.g., if you change a Go Agent payload, you must change the Python Server handler). 
* `@AI-FREE`: **[FREEDOM]** Internal implementation logic. You are free to rewrite, optimize, and refactor this to achieve your current goal.
* **YOUR DUTY:** When you write complex logic or fix a bug, you MUST add an `@AI-LOCKED` comment explaining *why* you did it, so the next AI doesn't break it.

## 2. 🏛️ CURRENT `@AI-CONTRACT` BOUNDARIES (Do Not Break)
* **Database:** `memory_total` is mapped as `BigInteger` (Bytes). Standard Ints will crash.
* **WS Handshake:** The Server expects `token` to be used as `agent_id`.
* **Llama Docker:** Server identifies inference containers strictly via label `fabricore.role=inference` or `com.docker.compose.service=llama`.
* **Agent Syscalls:** `agent/internal/sys/syscall.go` MUST return raw stdout/stderr to the Go orchestrator.

## 3. 🛑 PRE-FLIGHT CHECKLIST (MANDATORY)
Before you write or modify ANY code for your current task, you MUST output a brief plan formatted exactly like this:
1. **Goal:** (What are you trying to do?)
2. **Blast Radius:** (If I change X, what else might break? Which `@AI-CONTRACT` boundaries am I touching?)
3. **Execution Plan:** (Brief step-by-step).
*Wait for the user to approve this plan if the Blast Radius touches an `@AI-CONTRACT`.*

## 4. 🗺️ ARCHITECTURE MAP
* **Server (Python/FastAPI):** Dockerized. Entry points: `server/app/main.py`, WS via `server/app/api/v1/websocket.py`.
* **Agent (Go):** Dockerized (Alpine). Entry point: `agent/internal/orchestrator/orchestrator.go`.
* **UI:** NiceGUI/Quasar. Theme toggle relies on JS watcher in `server/app/ui/main.py` `@AI-LOCKED`.

## 5. 📖 CHANGELOG / AI MEMORY
* *[Memory]*: Set UI theme toggle to JS watcher (Python logic breaks Quasar sync).
* *[Memory]*: Set RAM to BigInt (32GB systems were overflowing).
* *[Memory]*: Injected initial @AI-CONTRACT and @AI-LOCKED tags across the codebase.
* *[Memory]*: Implemented real-time model download progress bar with ETA and agent status indicators (green/red icons) in Settings UI.
* *[Memory]*: Fixed chat 500 errors by consolidating system messages at the start and changing tool observation roles to `user`.
* *[Memory]*: Fixed `audit_log` schema migration bug and restored tool result persistence with `completed_at` timestamps.
* *[Memory]*: Added WebUI features: Shift+Enter line breaks, Abort generation button, and drag-and-drop file uploads that are deleted upon chat session removal.
* *[Memory]*: Documented `start_llama.sh` with `@AI-LOCKED` to preserve dynamic Llama args reload behavior.
* *[Memory]*: Implemented Python logger ISO timestamps and passed ChatMessage DB timestamps into UI UI render functions.
* *[Memory]*: Increased default `model_max_tokens` from 1024 to 4096 to solve tool calling truncation bugs. Added lifecycle `.deactivate()` to settings timers to prevent NiceGUI log spam.
* *[Memory]*: Fixed `_parse_tool_call` regression where large files truncated the non-greedy regex matcher and prevented successful generation. `model_max_tokens` parameter resets gracefully over client reconnections and tool calls dynamically parse with deep nested `{}` counting logic. Added nicegui logger exception filter.
* *[Memory]*: Major agentic behavior overhaul: (1) Replaced broken brace-counting parser with `json.JSONDecoder.raw_decode()` for correct nested JSON extraction. (2) Fixed `_run_command` to wrap commands in `sh -c` instead of naive `split()` — critical for heredocs, pipes, redirections. (3) Added retry loop: when tool call parsing fails, the agent re-prompts the LLM to break into smaller commands instead of silently stopping. (4) Strengthened system prompt to enforce autonomous looping behavior. (5) Raised `max_tokens` default to 8192 and `max_agent_turns` to 25.
* *[Memory]*: Implemented real-time Agent Status Panel in chat UI. Collapsible card shows live turn counter, tool calls, results, and token usage per step. Auto-expands on errors or max-turns to show full execution trace for debugging. Replaced the old simple spinner with a persistent status widget.
* *[Memory]*: Fixed context usage counter to show current turn tokens instead of accumulating session-wide. Updated Go Agent `ExecCommand` to return output on non-zero exit codes (ExitError) to enable AI debugging.

## 6. 🎯 CURRENT TASK


