from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
import uuid

from app.models.agent import Base

class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(String, ForeignKey("agents.id"), nullable=False)
    tool_name = Column(String, nullable=False)
    arguments = Column(JSON, nullable=False)
    result = Column(JSON, nullable=True)
    status = Column(String, default="pending") # pending, success, error
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
