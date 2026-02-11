# server/app/services/llm_service.py
"""
LLM Service - Loads and runs GGUF models using llama-cpp-python.
Provides tool calling support for the AI agent system.
"""

import os
import logging
import json
from typing import Optional, Dict, Any, List, Generator
from pathlib import Path
from llama_cpp import Llama
import asyncio
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Models directory
MODELS_DIR = Path(os.getenv("MODELS_PATH", "/server/llm_models"))

# Thread pool for LLM inference (CPU/GPU bound)
executor = ThreadPoolExecutor(max_workers=1)


class LLMService:
    """Service for loading and running local GGUF models."""
    
    def __init__(self):
        self.model: Optional[Llama] = None
        self.model_path: Optional[str] = None
        self.model_name: Optional[str] = None
        self.is_loading: bool = False
        self.context_size: int = 4096
        self.n_gpu_layers: int = -1  # -1 = all layers on GPU if available
        
    def get_status(self) -> Dict[str, Any]:
        """Get current LLM status."""
        return {
            "loaded": self.model is not None,
            "model_name": self.model_name,
            "model_path": self.model_path,
            "is_loading": self.is_loading,
            "context_size": self.context_size
        }
    
    def load_model_sync(self, model_path: str, n_ctx: int = 4096, n_gpu_layers: int = -1) -> bool:
        """
        Synchronously load a GGUF model.
        This should be called in a thread pool to avoid blocking.
        """
        try:
            self.is_loading = True
            logger.info(f"Loading model: {model_path}")
            
            # Unload existing model first
            if self.model is not None:
                self.unload_model()
            
            # Load the new model
            self.model = Llama(
                model_path=model_path,
                n_ctx=n_ctx,
                n_gpu_layers=n_gpu_layers,
                verbose=True,
                chat_format="chatml"  # Works with most models
            )
            
            self.model_path = model_path
            self.model_name = Path(model_path).name
            self.context_size = n_ctx
            self.n_gpu_layers = n_gpu_layers
            self.is_loading = False
            
            logger.info(f"Model loaded successfully: {self.model_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            self.is_loading = False
            self.model = None
            raise
    
    async def load_model(self, model_path: str, n_ctx: int = 4096, n_gpu_layers: int = -1) -> bool:
        """Async wrapper for model loading."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, self.load_model_sync, model_path, n_ctx, n_gpu_layers)
    
    def unload_model(self):
        """Unload the current model to free memory."""
        if self.model is not None:
            logger.info(f"Unloading model: {self.model_name}")
            del self.model
            self.model = None
            self.model_path = None
            self.model_name = None
    
    def generate_sync(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        stop: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Synchronous generation with optional tool calling.
        Returns the full response including any tool calls.
        """
        if self.model is None:
            raise RuntimeError("No model loaded. Please load a model first.")
        
        try:
            # Build the system prompt with tool definitions if provided
            if tools:
                tool_prompt = self._build_tool_prompt(tools)
                # Inject tool prompt into system message or prepend
                if messages and messages[0]["role"] == "system":
                    messages[0]["content"] += f"\n\n{tool_prompt}"
                else:
                    messages.insert(0, {"role": "system", "content": tool_prompt})
            
            # Generate response
            response = self.model.create_chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=stop or ["</s>", "<|im_end|>", "<|end|>"]
            )
            
            content = response["choices"][0]["message"]["content"]
            
            # Check if response contains a tool call
            tool_call = self._parse_tool_call(content)
            
            return {
                "content": content,
                "tool_call": tool_call,
                "usage": response.get("usage", {})
            }
            
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            raise
    
    async def generate(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """Async wrapper for generation."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            executor, 
            lambda: self.generate_sync(messages, tools, max_tokens, temperature)
        )
    
    def stream_sync(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.7
    ) -> Generator[str, None, None]:
        """Synchronous streaming generation."""
        if self.model is None:
            raise RuntimeError("No model loaded. Please load a model first.")
        
        response = self.model.create_chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True
        )
        
        for chunk in response:
            delta = chunk["choices"][0].get("delta", {})
            if "content" in delta:
                yield delta["content"]
    
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
            # Look for tool_call code block
            if "```tool_call" in content:
                start = content.find("```tool_call") + len("```tool_call")
                end = content.find("```", start)
                if end > start:
                    json_str = content[start:end].strip()
                    return json.loads(json_str)
            
            # Also try to find raw JSON with tool key
            if '"tool"' in content and '"params"' in content:
                # Try to extract JSON object
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
