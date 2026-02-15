from functools import lru_cache
from typing import Generator
from app.services.data_manager import DataManager
from app.services.agent_manager import AgentManager

@lru_cache()
def get_data_manager() -> DataManager:
    return DataManager()

@lru_cache()
def get_agent_manager() -> AgentManager:
    return AgentManager()

@lru_cache()
def get_model_manager():
    from app.services.model_manager import get_model_manager as _get_mm
    return _get_mm()

@lru_cache()
def get_scheduler_service():
    from app.services.scheduler import SchedulerService
    return SchedulerService()

@lru_cache()
def get_llm_service():
    from app.services.llm_service import get_llm_service as _get_llm
    return _get_llm()

def get_db():
    dm = get_data_manager()
    db = dm.SessionLocal()
    try:
        yield db
    finally:
        db.close()
