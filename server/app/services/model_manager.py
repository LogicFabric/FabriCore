# server/app/services/model_manager.py
"""
Model Manager Service
Handles downloading and managing LLM models from Hugging Face.
Uses huggingface_hub to download GGUF files.
"""

import os
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
import docker
from huggingface_hub import hf_hub_download, list_repo_files, HfApi
import asyncio
from concurrent.futures import ThreadPoolExecutor

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
    async def load_model(self, model_name: str, n_ctx: int = 4096) -> bool:
        """
        Load a model by restarting the llama container with new parameters.
        """
        if not self.docker_client:
            logger.error("Docker client not initialized. Cannot load model.")
            return False

        try:
            # The llama container sees models in /app/llm_models/
            # We just need the filename
            container_model_path = f"/app/llm_models/{model_name}"
            
            # Find the llama container (usually named 'server-llama-1' or similar in compose)
            # We look for a container with the label 'com.docker.compose.service=llama'
            containers = self.docker_client.containers.list(filters={"label": "com.docker.compose.service=llama"})
            if not containers:
                logger.error("Llama container not found.")
                return False
            
            llama_container = containers[0]
            
            # 1. Write the new command to the shared volume
            # server container path: /server/llm_models/llama_args.txt
            # llama container path: /app/llm_models/llama_args.txt
            args_content = f"--model {container_model_path} --host 0.0.0.0 --port 8080 --n-gpu-layers -1 --ctx-size {n_ctx}"
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

            # 3. Update state
            await llm_service.set_model_state(str(self.models_dir / model_name), n_ctx=n_ctx)
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


# Singleton instance
_model_manager: Optional[ModelManager] = None


def get_model_manager() -> ModelManager:
    """Get or create the singleton ModelManager instance."""
    global _model_manager
    if _model_manager is None:
        hf_token = os.getenv("HF_TOKEN")
        _model_manager = ModelManager(hf_token=hf_token)
    return _model_manager
