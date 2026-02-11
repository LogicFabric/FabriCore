# server/app/services/data_manager.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.models.db import Base, Agent, AuditLog, User, GlobalSettings, ChatSession, ChatMessage
from datetime import datetime, timedelta
import os

class DataManager:
    def __init__(self, db_url=None):
        if db_url is None:
            db_url = os.getenv("DATABASE_URL", "sqlite:///./fabricore.db")
        connect_args = {}
        if "sqlite" in db_url:
            connect_args = {"check_same_thread": False}
        
        self.engine = create_engine(db_url, connect_args=connect_args)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

    def get_db(self) -> Session:
        db = self.SessionLocal()
        try:
            return db
        finally:
            db.close()

    def register_agent(self, agent_data: dict):
        db = self.SessionLocal()
        try:
            agent = db.query(Agent).filter(Agent.id == agent_data['id']).first()
            if not agent:
                agent = Agent(**agent_data)
                db.add(agent)
            else:
                for key, value in agent_data.items():
                    setattr(agent, key, value)
            db.commit()
            return agent
        finally:
            db.close()

    def update_agent_status(self, agent_id: str, status: str):
        db = self.SessionLocal()
        try:
            agent = db.query(Agent).filter(Agent.id == agent_id).first()
            if agent:
                agent.status = status
                agent.last_seen = datetime.utcnow()
                db.commit()
        finally:
            db.close()
            
    def db_cleanup_old_logs(self, days: int = 30):
        db = self.get_db()
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            db.query(AuditLog).filter(AuditLog.timestamp < cutoff).delete()
            db.commit()
        finally:
            db.close()

    # --- Chat History Methods ---

    def create_chat_session(self, title: str = "New Chat", session_id: str = None) -> ChatSession:
        import uuid
        db = self.get_db()
        try:
            if not session_id:
                session_id = str(uuid.uuid4())
            session = ChatSession(id=session_id, title=title)
            db.add(session)
            db.commit()
            db.refresh(session)
            return session
        finally:
            db.close()

    def get_chat_sessions(self, limit: int = 50):
        db = self.get_db()
        try:
            return db.query(ChatSession).order_by(ChatSession.created_at.desc()).limit(limit).all()
        finally:
            db.close()

    def get_chat_messages(self, session_id: str):
        db = self.get_db()
        try:
            return db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.timestamp.asc()).all()
        finally:
            db.close()

    def save_chat_message(self, session_id: str, role: str, content: str, metadata: dict = None):
        db = self.get_db()
        try:
            message = ChatMessage(
                session_id=session_id,
                role=role,
                content=content,
                metadata_json=metadata
            )
            db.add(message)
            db.commit()
            return message
        finally:
            db.close()

    def delete_chat_session(self, session_id: str):
        db = self.get_db()
        try:
            db.query(ChatSession).filter(ChatSession.id == session_id).delete()
            db.commit()
        finally:
            db.close()

    def update_session_title(self, session_id: str, title: str):
        db = self.get_db()
        try:
            session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
            if session:
                session.title = title
                db.commit()
        finally:
            db.close()
            
    def log_event(self, agent_id: str, action: str, details: dict, status: str = "info"):
        db = self.SessionLocal()
        try:
            log = AuditLog(
                agent_id=agent_id,
                action=action,
                details=details,
                status=status
            )
            db.add(log)
            db.commit()
        finally:
            db.close()
            

