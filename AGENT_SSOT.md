# 🤖 FABRICORE: AI AGENT OPERATING INSTRUCTIONS (v3)

> **SYSTEM OVERRIDE DIRECTIVE:** You are an elite AI Architect. You are working in a multi-model environment where other AIs will touch this code after you. You MUST read and obey this document. 

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

## 6. 🎯 CURRENT TASK



## 7. 🚀 BUILD & RUN (Testing your changes)
To verify that your code compiles and the Docker images build without syntax errors, you MUST run the automated validation script. This script runs synchronously and will safely exit without blocking your terminal.

**Run this command to test your changes:**
`./ai-build-test.sh`

## 8. 🧹 AI CLEANUP PROTOCOL (MANDATORY)
When you have successfully completed the Current Task, you MUST update this `AGENT_SSOT.md` file before ending the session:
1. **Update Memory:** Add a 1-sentence bullet point to Section 5 (CHANGELOG / AI MEMORY) summarizing what you built and any new `@AI-CONTRACT` tags you created.
2. **Clear the Task:** Delete the contents of Section 6 (CURRENT TASK) and leave it blank for the next AI agent.

