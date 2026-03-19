# server/app/services/llm_service.py
"""
LLM Service - Connects to the external llama-server HTTP API.
Provides tool calling support for the AI agent system.
"""

import os
import logging
import json
import httpx
from typing import Optional, Dict, Any, List, AsyncGenerator
from pathlib import Path
import asyncio

logger = logging.getLogger(__name__)

# llama-server endpoint
LLAMA_BASE_URL = os.getenv("LLAMA_BASE_URL", "http://llama:8080")


class LLMService:
    """Service for running local GGUF models via llama-server API."""
    
    def __init__(self):
        self.model_path: Optional[str] = None
        self.model_name: Optional[str] = None
        self.is_loading: bool = False
        self.context_size: int = 4096
        self.client = httpx.AsyncClient(base_url=LLAMA_BASE_URL, timeout=None)
        
    @property
    def model(self) -> Optional[str]:
        """Compatibility property for UI."""
        return self.model_name
        
    def get_status(self) -> Dict[str, Any]:
        """Get current LLM status."""
        return {
            "loaded": self.model_name is not None,
            "model_name": self.model_name,
            "model_path": self.model_path,
            "is_loading": self.is_loading,
            "context_size": self.context_size
        }
    
    async def set_model_state(
        self, 
        model_path: Optional[str], 
        n_ctx: int = 4096, 
        n_parallel: int = 1,
        flash_attn: bool = False,
        kv_cache_type: str = "fp16",
        n_gpu_layers: int = -1
    ) -> bool:
        """
        Update the service state after a model has been loaded via container restart.
        """
        if model_path:
            self.model_path = model_path
            self.model_name = Path(model_path).name
            self.context_size = n_ctx
            self.n_parallel = n_parallel
            self.flash_attn = flash_attn
            self.kv_cache_type = kv_cache_type
            self.n_gpu_layers = n_gpu_layers
            logger.info(f"LLMService state updated for model: {self.model_name} (ctx={n_ctx}, parallel={n_parallel}, flash={flash_attn}, kv={kv_cache_type}, layers={n_gpu_layers})")
        else:
            self.model_path = None
            self.model_name = None
            self.context_size = 4096
            self.n_parallel = 1
            self.flash_attn = False
            self.kv_cache_type = "fp16"
            self.n_gpu_layers = -1
            logger.info("LLMService state cleared (Model released).")
        return True
    
    async def generate(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """Async generation with optional tool calling."""
        try:
            # Sanitize messages to ensure system prompt is at the beginning
            messages = self._sanitize_messages(messages)
            
            # Build the system prompt with tool definitions if provided
            if tools:
                tool_prompt = self._build_tool_prompt(tools)
                if messages and messages[0]["role"] == "system":
                    messages[0]["content"] += f"\n\n{tool_prompt}"
                else:
                    messages.insert(0, {"role": "system", "content": tool_prompt})
            
            # Map messages to llama-server format if needed, but llama-server supports OpenAI-like chat completions
            payload = {
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": False
            }
            
            response = await self.client.post("/v1/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            
            choice = data["choices"][0]
            message = choice["message"]
            content = message.get("content", "")
            tool_calls = message.get("tool_calls", [])
            
            # Extract Usage
            usage = data.get("usage", {"total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0})
            
            result = {
                "content": content,
                "tool_call": None,
                "usage": usage
            }

            # Parse Tool Call (simplify to single tool for ReAct loop)
            if tool_calls:
                tc = tool_calls[0]
                func = tc["function"]
                try:
                    args = json.loads(func["arguments"])
                    result["tool_call"] = {
                        "tool": func["name"],
                        "params": args
                    }
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse tool arguments: {func['arguments']}")
            
            # 2. Fallback: Parse Content for Text-based Tool Call
            # This is the missing piece causing your issue
            elif content:
                parsed_tool = self._parse_tool_call(content)
                if parsed_tool:
                    result["tool_call"] = parsed_tool
                    # Optional: Clean up content so the user doesn't see the raw JSON
                    # result["content"] = ""
            
            return result

        except Exception as e:
            logger.error(f"Generation failed: {e}")
            raise
    
    async def stream_response(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.7
    ) -> AsyncGenerator[str, None]:
        """Async streaming generation."""
        try:
            # Sanitize messages
            messages = self._sanitize_messages(messages)
            
            payload = {
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True
            }
            
            async with self.client.stream("POST", "/v1/chat/completions", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data["choices"][0].get("delta", {})
                            if "content" in delta:
                                yield delta["content"]
                        except json.JSONDecodeError:
                            continue
                            
        except Exception as e:
            logger.error(f"Streaming failed: {e}")
            raise

    def _sanitize_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Consolidate all system messages into one at the beginning.
        Ensures model-specific chat templates don't crash on misplaced system prompts.
        """
        if not messages:
            return messages

        system_contents = []
        other_messages = []

        for msg in messages:
            if msg.get("role") == "system":
                content = msg.get("content", "").strip()
                if content:
                    system_contents.append(content)
            else:
                other_messages.append(msg)

        if not system_contents:
            return other_messages

        # Create single consolidated system message
        consolidated_system = {
            "role": "system",
            "content": "\n\n".join(system_contents)
        }
        
        return [consolidated_system] + other_messages

    def _build_tool_prompt(self, tools: List[Dict]) -> str:
        """Build a strict tool description prompt with examples."""
        tool_descriptions = []
        for tool in tools:
            desc = f"- {tool['name']}: {tool['description']}\n"
            if "parameters" in tool:
                # Simplify parameter description for the LLM
                params = {k: v.get('description', '') for k, v in tool['parameters'].items()}
                desc += f"  REQUIRED Params: {json.dumps(params)}"
            tool_descriptions.append(desc)
        
        return f"""### IDENTITY
You are FabriCore, a fully autonomous AI system administrator agent.
You are NOT a chatbot. You NEVER ask questions. You ACT.

### CRITICAL RULES
1. You are an AUTONOMOUS AGENT. You execute tools in a loop until the task is 100% done.
2. ALWAYS respond with EXACTLY ONE tool_call per message. After seeing the tool result, decide the NEXT action.
3. When writing files, keep commands SHORT. Use multiple small tool calls instead of one giant heredoc.
4. Verify your results. If a tool fails, TRY A DIFFERENT WAY immediately.
5. Use `list_agents` first if you don't know the agent_id.
6. Only use the tools listed below. Do not invent tools.
7. When creating files, prefer using `echo` with `>>` (append) for large files, or `tee`, instead of giant `cat << EOF` blocks.
8. After ALL tool work is complete, respond with a plain-text summary of what you did. This is the ONLY time you use plain text.

### AVAILABLE TOOLS
{chr(10).join(tool_descriptions)}

### RESPONSE FORMAT
To use a tool, respond with ONLY this format (no extra text before or after):
```tool_call
{{"tool": "tool_name", "params": {{"param_name": "value"}}}}
```

To report completion (ONLY after all work is done):
Plain text summary of what was accomplished.

### EXAMPLES
User: "Create a config file on agent-main"
Assistant:
```tool_call
{{"tool": "run_command", "params": {{"agent_id": "agent-main", "command": "echo 'key=value' > /etc/app.conf"}}}}
```

User: "Observation: {{\"success\": true, ...}}"
Assistant:
Done. Created /etc/app.conf with the configuration."""
    
    def _parse_tool_call(self, content: str) -> Optional[Dict[str, Any]]:
        """Robustly parse tool calls from mixed text using json.JSONDecoder."""
        import re
        try:
            # 1. Try markdown-fenced blocks: ```tool_call ... ``` or ```toolcall ... ``` or ```json ... ```
            # Use a greedy search between fences to get the full block
            fence_match = re.search(r'```(?:tool_call|toolcall|json)?\s*\n?(\{.+)```', content, re.DOTALL | re.IGNORECASE)
            if fence_match:
                json_text = fence_match.group(1).strip()
                try:
                    return json.loads(json_text)
                except json.JSONDecodeError:
                    pass

            # 2. Use json.JSONDecoder.raw_decode to find the first valid JSON object
            #    This is the only correct way to extract JSON with nested content
            decoder = json.JSONDecoder()
            # Find potential start positions
            for pattern in ['{"tool":', '{ "tool":', '{\n"tool":', '{\n  "tool":']:
                start_idx = content.find(pattern)
                if start_idx != -1:
                    try:
                        obj, end_idx = decoder.raw_decode(content, start_idx)
                        if isinstance(obj, dict) and 'tool' in obj:
                            return obj
                    except json.JSONDecodeError:
                        continue
            
            # 3. Regex to find any {... "tool" ...} pattern and try raw_decode from there
            for m in re.finditer(r'\{', content):
                try:
                    obj, _ = decoder.raw_decode(content, m.start())
                    if isinstance(obj, dict) and 'tool' in obj:
                        return obj
                except (json.JSONDecodeError, ValueError):
                    continue

        except Exception as e:
            logger.warning(f"Failed to parse tool call: {e}")
        
        return None


# Singleton instance
_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Get or create the singleton LLMService instance."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
