# server/app/services/data_manager.py
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from app.models.db import Base, Agent, AuditLog, User, GlobalSettings, ChatSession, ChatMessage
from datetime import datetime, timedelta
import os
import logging

logger = logging.getLogger(__name__)

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

    def _run_migrations(self):
        """Add missing columns safely if they don't exist"""
        try:
            with self.engine.connect() as conn:
                # Handling for SQLite vs PostgreSQL
                is_sqlite = "sqlite" in str(self.engine.url)
                
                # Check current columns in 'agents' table
                existing_columns = []
                try:
                    if is_sqlite:
                        res = conn.execute(text("PRAGMA table_info(agents)"))
                        existing_columns = [row[1] for row in res.fetchall()]
                    else:
                        # PostgreSQL
                        res = conn.execute(text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = 'agents'"
                        ))
                        existing_columns = [row[0] for row in res.fetchall()]
                except Exception as e:
                    logger.error(f"Failed to inspect agents table: {e}")
                    return

                columns_to_add = [
                    ("name", "VARCHAR", "ALTER TABLE agents ADD COLUMN name VARCHAR"),
                    ("arch", "VARCHAR", "ALTER TABLE agents ADD COLUMN arch VARCHAR"),
                    ("memory_total", "INTEGER", "ALTER TABLE agents ADD COLUMN memory_total INTEGER"),
                    ("supported_tools", "JSON", "ALTER TABLE agents ADD COLUMN supported_tools JSON"),
                    ("security_policy_json", "TEXT", "ALTER TABLE agents ADD COLUMN security_policy_json TEXT")
                ]
                
                for col_name, type_name, pg_sql in columns_to_add:
                    if col_name in existing_columns:
                        continue
                        
                    try:
                        sql = pg_sql
                        if is_sqlite:
                            type_map = {"VARCHAR": "TEXT", "INTEGER": "INTEGER", "JSON": "TEXT", "TEXT": "TEXT"}
                            sql = f"ALTER TABLE agents ADD COLUMN {col_name} {type_map[type_name]}"
                        
                        conn.execute(text(sql))
                        conn.commit()
                        logger.info(f"Migration: Successfully added column {col_name} to agents table.")
                    except Exception as e:
                        logger.warning(f"Migration failed for column {col_name}: {e}")
                            
        except Exception as e:
            logger.warning(f"Global migration error: {e}")

    def reset_agent_statuses(self):
        """
        Resets all agents to 'offline' status on server startup.
        This prevents the UI from showing ghosts of previous sessions.
        """
        db = self.SessionLocal()
        try:
            # efficient bulk update
            db.query(Agent).update({Agent.status: "offline"})
            db.commit()
            logger.info("All agent statuses reset to 'offline'.")
        except Exception as e:
            logger.error(f"Failed to reset agent statuses: {e}")
            db.rollback()
        finally:
            db.close()


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
            

