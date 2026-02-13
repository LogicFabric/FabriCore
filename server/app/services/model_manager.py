# server/app/services/model_manager.py
"""
Model Manager Service
Handles downloading and managing LLM models from Hugging Face.
Uses huggingface_hub to download GGUF files.
"""

import os
import logging
import math
from pathlib import Path
from typing import Optional, List, Dict, Any
import docker
from huggingface_hub import hf_hub_download, list_repo_files, HfApi
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Try to import GGUF, handle if missing
try:
    import gguf
except ImportError:
    gguf = None

logger = logging.getLogger(__name__)

# Default model storage path
MODELS_DIR = Path(os.getenv("MODELS_PATH", "/server/llm_models"))

# Thread pool for background downloads
executor = ThreadPoolExecutor(max_workers=2)

# Track download progress
download_status: Dict[str, Dict[str, Any]] = {}


class ModelManager:
    def __init__(self, models_dir: Path = MODELS_DIR, hf_token: Optional[str] = None):
        self.models_dir = models_dir
        self.hf_token = hf_token
        self.api = HfApi(token=hf_token) if hf_token else HfApi()
        try:
            self.docker_client = docker.from_env()
        except Exception as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            self.docker_client = None
        
        # Ensure models directory exists
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        # Clear any previous model configuration on startup to prevent auto-loading
        args_file = self.models_dir / "llama_args.txt"
        if args_file.exists():
            try:
                args_file.unlink()
                logger.info("Cleared previous model configuration on startup.")
            except Exception as e:
                logger.warning(f"Failed to clear startup config: {e}")

        # Aggressively reset llama container to ensure clean startup state
        if self.docker_client:
            try:
                containers = self.docker_client.containers.list(all=True, filters={"label": "com.docker.compose.service=llama"})
                if containers:
                    container = containers[0]
                    if container.status == 'running':
                        logger.info("♻️  Resetting Llama container to ensure clean startup state...")
                        container.restart()
                        logger.info("Llama container reset successful.")
            except Exception as e:
                logger.error(f"Failed to reset llama container on startup: {e}")

        logger.info(f"ModelManager initialized. Models directory: {self.models_dir}")

    def set_token(self, token: str):
        """Update Hugging Face token."""
        self.hf_token = token
        self.api = HfApi(token=token)
        logger.info("Hugging Face token updated.")

    def get_local_models(self) -> List[Dict[str, Any]]:
        """Get list of locally installed models."""
        models = []
        if self.models_dir.exists():
            for file in self.models_dir.glob("*.gguf"):
                models.append({
                    "name": file.name,
                    "path": str(file),
                    "size": f"{file.stat().st_size / (1024**3):.2f} GB"
                })
        return models

    def is_model_installed(self, repo_id: str, filename: str) -> bool:
        """Check if a model file is already downloaded."""
        model_path = self.models_dir / filename
        return model_path.exists()

    def download_model_sync(self, repo_id: str, filename: str) -> str:
        """
        Synchronously download a model from Hugging Face.
        This runs in a thread pool to avoid blocking.
        """
        download_status[repo_id] = {'status': 'downloading', 'progress': 0, 'filename': filename}
        
        try:
            logger.info(f"Starting download: {repo_id}/{filename}")
            
            # Download the file
            local_path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=str(self.models_dir),
                local_dir_use_symlinks=False,
                token=self.hf_token
            )
            
            download_status[repo_id] = {'status': 'completed', 'progress': 100, 'filename': filename, 'path': local_path}
            logger.info(f"Download completed: {local_path}")
            return local_path
            
        except Exception as e:
            logger.error(f"Download failed for {repo_id}/{filename}: {e}")
            download_status[repo_id] = {'status': 'failed', 'progress': 0, 'error': str(e)}
            raise

    async def download_model(self, repo_id: str, filename: str) -> str:
        """Async wrapper for model download."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, self.download_model_sync, repo_id, filename)

    async def search_hf_models(self, query: str = "", limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search for GGUF models on Hugging Face.
        Returns a list of model info dicts.
        """
        loop = asyncio.get_event_loop()
        try:
            # Search for models with 'gguf' tag
            # We filter for models that likely have GGUF files
            def _search():
                models = self.api.list_models(
                    filter="gguf",
                    search=query if query else None,
                    sort="downloads",
                    direction=-1,
                    limit=limit
                )
                
                results = []
                for m in models:
                    results.append({
                        "id": m.id,
                        "name": m.id.split('/')[-1],
                        "author": m.author,
                        "downloads": getattr(m, 'downloads', 0),
                        "likes": getattr(m, 'likes', 0),
                        "last_modified": m.last_modified.isoformat() if m.last_modified else None
                    })
                return results

            return await loop.run_in_executor(executor, _search)
        except Exception as e:
            logger.error(f"HF Search failed: {e}")
            return []

    async def get_model_files(self, repo_id: str) -> List[str]:
        """Get list of GGUF files in a repository."""
        loop = asyncio.get_event_loop()
        try:
            def _list():
                files = self.api.list_repo_files(repo_id=repo_id)
                return [f for f in files if f.endswith('.gguf')]
            return await loop.run_in_executor(executor, _list)
        except Exception as e:
            logger.error(f"Failed to list files for {repo_id}: {e}")
            return []

    def _get_model_layers(self, model_path: Path) -> int:
        """Read the GGUF header to find the total number of layers."""
        if not gguf:
            logger.warning("GGUF library not found. Assuming metadata reading unavailable.")
            return 0
            
        try:
            reader = gguf.GGUFReader(str(model_path), mode='r')
            # 1. Get architecture (e.g., 'llama', 'qwen2')
            field = reader.fields.get('general.architecture')
            if not field:
                return 0
            
            arch = bytes(field.parts[-1]).decode('utf-8')
            
            # 2. Get block count (e.g., 'llama.block_count')
            block_count_field = reader.fields.get(f'{arch}.block_count')
            if block_count_field:
                return int(block_count_field.parts[-1][0])
                
        except Exception as e:
            logger.error(f"Failed to read GGUF metadata for {model_path}: {e}")
        
        return 0
    async def load_model(self, model_name: str, n_ctx: int = 4096, n_parallel: int = 1, kv_cache_type: str = "fp16", gpu_offload_percent: int = 100) -> bool:
        """
        Load a model by restarting the llama container with new parameters.
        """
        if not self.docker_client:
            logger.error("Docker client not initialized. Cannot load model.")
            return False

        try:
            # 1. Define paths for both containers
            # Path inside THIS container (server) to read metadata
            local_model_path = self.models_dir / model_name
            # Path inside the LLAMA container to execute
            container_model_path = f"/app/llm_models/{model_name}"
            
            # Calculate layers based on percentage
            n_gpu_layers = -1
            if gpu_offload_percent < 100:
                total_layers = self._get_model_layers(local_model_path)
                if total_layers > 0:
                    n_gpu_layers = math.ceil(total_layers * (gpu_offload_percent / 100.0))
                    logger.info(f"Offloading {gpu_offload_percent}% -> {n_gpu_layers}/{total_layers} layers")
                else:
                    # Fallback if metadata read fails but percentage is requested
                    logger.warning(f"Could not read metadata for {model_name}, falling back to legacy '-1' offloading.")
                    n_gpu_layers = -1

            containers = self.docker_client.containers.list(all=True, filters={"label": "com.docker.compose.service=llama"})
            if not containers:
                logger.error("Llama container not found.")
                return False
            
            llama_container = containers[0]
            
            # 1. Write the new command to the shared volume
            # server container path: /server/llm_models/llama_args.txt
            # llama container path: /app/llm_models/llama_args.txt
            
            # Basic args
            args_list = [
                f"--model {container_model_path}",
                "--host 0.0.0.0",
                "--port 8080",
                f"--n-gpu-layers {n_gpu_layers}",
                f"--ctx-size {n_ctx}",
                f"--parallel {n_parallel}",
                "--flash-attn on"
            ]
            
            # Removed the manual toggle logic here
            
            if kv_cache_type and kv_cache_type != "fp16":
                args_list.append(f"--cache-type-k {kv_cache_type}")
                args_list.append(f"--cache-type-v {kv_cache_type}")

            args_content = " ".join(args_list)
            args_file = self.models_dir / "llama_args.txt"
            args_file.write_text(args_content)
            
            logger.info(f"Restarting llama container...")
            llama_container.restart()
            
            # 2. Wait for llama-server to be ready
            from app.services.llm_service import get_llm_service, LLAMA_BASE_URL
            llm_service = get_llm_service()
            
            # Simple poll for health
            max_retries = 300 # 5 minutes for huge models
            logger.info(f"Waiting up to {max_retries}s for llama-server to be ready...")
            for i in range(max_retries):
                try:
                    import httpx
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(f"{LLAMA_BASE_URL}/health")
                        if resp.status_code == 200:
                            logger.info("llama-server is ready!")
                            break
                        else:
                            if i % 10 == 0:
                                logger.info(f"llama-server status: {resp.status_code}...")
                except Exception:
                    if i % 10 == 0:
                        logger.info("Waiting for llama-server endpoint...")
                    pass
                await asyncio.sleep(1)
            else:
                logger.warning("llama-server timed out during restart.")
                return False

            # 3. Update state (Flash Attention always True)
            await llm_service.set_model_state(str(self.models_dir / model_name), n_ctx=n_ctx, n_parallel=n_parallel, flash_attn=True, kv_cache_type=kv_cache_type, n_gpu_layers=n_gpu_layers)
            return True
            
        except Exception as e:
            logger.error(f"Failed to switch model: {e}")
            return False

    def delete_model(self, filename: str) -> bool:
        """Delete a local model file."""
        model_path = self.models_dir / filename
        if model_path.exists():
            try:
                model_path.unlink()
                logger.info(f"Deleted model file: {filename}")
                return True
            except Exception as e:
                logger.error(f"Failed to delete model {filename}: {e}")
                return False
        return False

    async def release_model(self) -> bool:
        """
        Unload the current model by deleting configuration and stopping the llama container.
        This releases 100% of GPU memory.
        """
        if not self.docker_client:
            return False

        try:
            # 1. Clear configuration
            args_file = self.models_dir / "llama_args.txt"
            if args_file.exists():
                args_file.unlink()
                logger.info("Released model: Cleared llama_args.txt")

            # 2. Stop container
            containers = self.docker_client.containers.list(all=True, filters={"label": "com.docker.compose.service=llama"})
            if containers:
                container = containers[0]
                if container.status == "running":
                    logger.info("Released model: Stopping llama container...")
                    container.stop(timeout=5)
                
            # 3. Update LLM service state
            from app.services.llm_service import get_llm_service
            llm_service = get_llm_service()
            await llm_service.set_model_state(None)
            
            return True
        except Exception as e:
            logger.error(f"Failed to release model: {e}")
            return False


# Singleton instance
_model_manager: Optional[ModelManager] = None


def get_model_manager() -> ModelManager:
    """Get or create the singleton ModelManager instance."""
    global _model_manager
    if _model_manager is None:
        hf_token = os.getenv("HF_TOKEN")
        _model_manager = ModelManager(hf_token=hf_token)
    return _model_manager
