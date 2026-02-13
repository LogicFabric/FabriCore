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
        flash_attn: bool = True,
        kv_cache_type: str = "fp16"
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
            logger.info(f"LLMService state updated for model: {self.model_name} (ctx={n_ctx}, parallel={n_parallel}, flash={flash_attn}, kv={kv_cache_type})")
        else:
            self.model_path = None
            self.model_name = None
            logger.info("LLMService state cleared.")
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
            
            content = data["choices"][0]["message"]["content"]
            tool_call = self._parse_tool_call(content)
            
            return {
                "content": content,
                "tool_call": tool_call,
                "usage": data.get("usage", {})
            }
            
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

    def _build_tool_prompt(self, tools: List[Dict]) -> str:
        """Build a tool description prompt for the model."""
        tool_descriptions = []
        for tool in tools:
            desc = f"- **{tool['name']}**: {tool['description']}\n"
            if "parameters" in tool:
                desc += f"  Parameters: {json.dumps(tool['parameters'])}\n"
            tool_descriptions.append(desc)
        
        return f"""You are an AI assistant that can use tools to help users manage their systems.

Available tools:
{chr(10).join(tool_descriptions)}

When you need to use a tool, respond with a JSON block in this format:
```tool_call
{{"tool": "tool_name", "params": {{"param1": "value1"}}}}
```

After receiving tool results, provide a helpful response to the user."""
    
    def _parse_tool_call(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse a tool call from the model's response."""
        try:
            if "```tool_call" in content:
                start = content.find("```tool_call") + len("```tool_call")
                end = content.find("```", start)
                if end > start:
                    json_str = content[start:end].strip()
                    return json.loads(json_str)
            
            if '"tool"' in content and '"params"' in content:
                start = content.find("{")
                end = content.rfind("}") + 1
                if start != -1 and end > start:
                    json_str = content[start:end]
                    parsed = json.loads(json_str)
                    if "tool" in parsed:
                        return parsed
                        
        except json.JSONDecodeError:
            pass
        
        return None


# Singleton instance
_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Get or create the singleton LLMService instance."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
