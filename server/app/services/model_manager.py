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
from huggingface_hub import hf_hub_download, list_repo_files, HfApi
import asyncio
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Default model storage path
MODELS_DIR = Path(os.getenv("MODELS_PATH", "/server/llm_models"))

# Popular GGUF models with their quantization options
AVAILABLE_GGUF_MODELS = [
    {
        "id": "TheBloke/Llama-2-7B-Chat-GGUF",
        "name": "Llama 2 7B Chat",
        "files": ["llama-2-7b-chat.Q4_K_M.gguf", "llama-2-7b-chat.Q5_K_M.gguf", "llama-2-7b-chat.Q8_0.gguf"],
        "recommended": "llama-2-7b-chat.Q4_K_M.gguf",
        "size": "4.08 GB"
    },
    {
        "id": "TheBloke/Mistral-7B-Instruct-v0.2-GGUF",
        "name": "Mistral 7B Instruct v0.2",
        "files": ["mistral-7b-instruct-v0.2.Q4_K_M.gguf", "mistral-7b-instruct-v0.2.Q5_K_M.gguf"],
        "recommended": "mistral-7b-instruct-v0.2.Q4_K_M.gguf",
        "size": "4.37 GB"
    },
    {
        "id": "TheBloke/CodeLlama-7B-Instruct-GGUF",
        "name": "CodeLlama 7B Instruct",
        "files": ["codellama-7b-instruct.Q4_K_M.gguf", "codellama-7b-instruct.Q5_K_M.gguf"],
        "recommended": "codellama-7b-instruct.Q4_K_M.gguf",
        "size": "4.08 GB"
    },
    {
        "id": "TheBloke/Llama-2-13B-chat-GGUF",
        "name": "Llama 2 13B Chat",
        "files": ["llama-2-13b-chat.Q4_K_M.gguf", "llama-2-13b-chat.Q5_K_M.gguf"],
        "recommended": "llama-2-13b-chat.Q4_K_M.gguf",
        "size": "7.87 GB"
    },
    {
        "id": "TheBloke/zephyr-7B-beta-GGUF",
        "name": "Zephyr 7B Beta",
        "files": ["zephyr-7b-beta.Q4_K_M.gguf", "zephyr-7b-beta.Q5_K_M.gguf"],
        "recommended": "zephyr-7b-beta.Q4_K_M.gguf",
        "size": "4.37 GB"
    },
    {
        "id": "TheBloke/Phi-2-GGUF",
        "name": "Microsoft Phi-2",
        "files": ["phi-2.Q4_K_M.gguf", "phi-2.Q5_K_M.gguf", "phi-2.Q8_0.gguf"],
        "recommended": "phi-2.Q4_K_M.gguf",
        "size": "1.61 GB"
    },
    {
        "id": "TheBloke/neural-chat-7B-v3-3-GGUF",
        "name": "Intel Neural Chat 7B v3.3",
        "files": ["neural-chat-7b-v3-3.Q4_K_M.gguf"],
        "recommended": "neural-chat-7b-v3-3.Q4_K_M.gguf",
        "size": "4.37 GB"
    },
    {
        "id": "TheBloke/Mixtral-8x7B-Instruct-v0.1-GGUF",
        "name": "Mixtral 8x7B Instruct",
        "files": ["mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf"],
        "recommended": "mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf",
        "size": "26.4 GB"
    },
    {
        "id": "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF",
        "name": "TinyLlama 1.1B Chat",
        "files": ["tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf", "tinyllama-1.1b-chat-v1.0.Q8_0.gguf"],
        "recommended": "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
        "size": "0.67 GB"
    },
    {
        "id": "TheBloke/dolphin-2.6-mistral-7B-GGUF",
        "name": "Dolphin 2.6 Mistral 7B",
        "files": ["dolphin-2.6-mistral-7b.Q4_K_M.gguf"],
        "recommended": "dolphin-2.6-mistral-7b.Q4_K_M.gguf",
        "size": "4.37 GB"
    },
]

# Thread pool for background downloads
executor = ThreadPoolExecutor(max_workers=2)

# Track download progress
download_status: Dict[str, Dict[str, Any]] = {}


class ModelManager:
    def __init__(self, models_dir: Path = MODELS_DIR, hf_token: Optional[str] = None):
        self.models_dir = models_dir
        self.hf_token = hf_token
        self.api = HfApi(token=hf_token) if hf_token else HfApi()
        
        # Ensure models directory exists
        self.models_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"ModelManager initialized. Models directory: {self.models_dir}")

    def set_token(self, token: str):
        """Update Hugging Face token."""
        self.hf_token = token
        self.api = HfApi(token=token)
        logger.info("Hugging Face token updated.")

    def get_available_models(self) -> List[Dict[str, Any]]:
        """Get list of available GGUF models."""
        models = []
        for model in AVAILABLE_GGUF_MODELS:
            model_info = model.copy()
            model_info['installed'] = self.is_model_installed(model['id'], model['recommended'])
            model_info['status'] = download_status.get(model['id'], {}).get('status', 'ready')
            model_info['progress'] = download_status.get(model['id'], {}).get('progress', 0)
            models.append(model_info)
        return models

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

    def get_download_status(self, repo_id: str) -> Dict[str, Any]:
        """Get download status for a model."""
        return download_status.get(repo_id, {'status': 'ready', 'progress': 0})

    def delete_model(self, filename: str) -> bool:
        """Delete a local model file."""
        model_path = self.models_dir / filename
        if model_path.exists():
            model_path.unlink()
            logger.info(f"Deleted model: {filename}")
            return True
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
