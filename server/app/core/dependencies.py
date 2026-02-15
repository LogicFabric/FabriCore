from functools import lru_cache
from app.services.data_manager import DataManager
from app.services.agent_manager import AgentManager
from app.services.model_manager import ModelManager
from app.services.llm_service import LLMService
# Import Scheduler only inside the function to avoid circular imports if necessary, 
# but usually top level is fine if organized correctly.
# For safety given the structure:
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.services.scheduler import SchedulerService

@lru_cache()
def get_data_manager() -> DataManager:
    return DataManager()

@lru_cache()
def get_agent_manager() -> AgentManager:
    return AgentManager()

@lru_cache()
def get_model_manager() -> ModelManager:
    return ModelManager()

@lru_cache()
def get_llm_service() -> LLMService:
    return LLMService()

# Scheduler singleton
_scheduler = None
def get_scheduler_service():
    global _scheduler
    if _scheduler is None:
        from app.services.scheduler import SchedulerService
        _scheduler = SchedulerService()
    return _scheduler

def get_db():
    dm = get_data_manager()
    db = dm.SessionLocal()
    try:
        yield db
    finally:
        db.close()