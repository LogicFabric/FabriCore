# server/app/services/data_manager.py
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from app.models.db import Base, Agent, AuditLog, User, GlobalSettings, ChatSession, ChatMessage, Schedule, PendingApproval
from datetime import datetime, timedelta
import os
import logging
import json

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
        self._run_migrations()

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
                            type_map = {"VARCHAR": "TEXT", "INTEGER": "INTEGER", "JSON": "TEXT", "TEXT": "TEXT", "BOOLEAN": "INTEGER"}
                            sql = f"ALTER TABLE agents ADD COLUMN {col_name} {type_map[type_name]}"
                        
                        conn.execute(text(sql))
                        conn.commit()
                        logger.info(f"Migration: Successfully added column {col_name} to agents table.")
                    except Exception as e:
                        logger.warning(f"Migration failed for column {col_name}: {e}")

                # --- Migrate chat_sessions table ---
                self._migrate_table(conn, is_sqlite, 'chat_sessions', [
                    ("has_unread", "BOOLEAN", "ALTER TABLE chat_sessions ADD COLUMN has_unread BOOLEAN DEFAULT FALSE"),
                ])

                # --- Migrate schedules table ---
                self._migrate_table(conn, is_sqlite, 'schedules', [
                    ("use_persistent_chat", "BOOLEAN", "ALTER TABLE schedules ADD COLUMN use_persistent_chat BOOLEAN DEFAULT FALSE"),
                    ("chat_session_id", "VARCHAR", "ALTER TABLE schedules ADD COLUMN chat_session_id VARCHAR"),
                ])

                # --- Migrate pending_approvals table ---
                self._migrate_table(conn, is_sqlite, 'pending_approvals', [
                    ("session_id", "VARCHAR", "ALTER TABLE pending_approvals ADD COLUMN session_id VARCHAR"),
                ])
                             
        except Exception as e:
            logger.warning(f"Global migration error: {e}")

    def _migrate_table(self, conn, is_sqlite: bool, table_name: str, columns: list):
        """Helper to add missing columns to a table."""
        try:
            existing = []
            if is_sqlite:
                res = conn.execute(text(f"PRAGMA table_info({table_name})"))
                existing = [row[1] for row in res.fetchall()]
            else:
                res = conn.execute(text(
                    f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}'"
                ))
                existing = [row[0] for row in res.fetchall()]

            type_map = {"VARCHAR": "TEXT", "INTEGER": "INTEGER", "JSON": "TEXT", "TEXT": "TEXT", "BOOLEAN": "INTEGER"}
            for col_name, type_name, pg_sql in columns:
                if col_name in existing:
                    continue
                try:
                    sql = pg_sql if not is_sqlite else f"ALTER TABLE {table_name} ADD COLUMN {col_name} {type_map.get(type_name, 'TEXT')}"
                    conn.execute(text(sql))
                    conn.commit()
                    logger.info(f"Migration: Added column {col_name} to {table_name}.")
                except Exception as e:
                    logger.warning(f"Migration failed for {table_name}.{col_name}: {e}")
        except Exception as e:
            logger.warning(f"Migration inspection failed for {table_name}: {e}")

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

    def update_agent_policy(self, agent_id: str, policy: dict):
        """Updates the security policy for a specific agent."""
        db = self.SessionLocal()
        try:
            agent = db.query(Agent).filter(Agent.id == agent_id).first()
            if agent:
                agent.security_policy_json = json.dumps(policy)
                db.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to update policy for {agent_id}: {e}")
            db.rollback()
            return False
        finally:
            db.close()

    def get_agent_policy(self, agent_id: str) -> dict:
        db = self.SessionLocal()
        try:
            agent = db.query(Agent).filter(Agent.id == agent_id).first()
            if agent and agent.security_policy_json:
                return json.loads(agent.security_policy_json)
            return {"hitl_enabled": False, "blocked_commands": [], "requires_approval_for": []} # Default
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
        db = self.SessionLocal()
        try:
            # Must delete child messages first — query-level delete() bypasses ORM cascade
            db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
            db.query(ChatSession).filter(ChatSession.id == session_id).delete()
            db.commit()
        finally:
            db.close()

    def mark_session_unread(self, session_id: str):
        """Mark a chat session as having unread AI responses."""
        db = self.SessionLocal()
        try:
            session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
            if session:
                session.has_unread = True
                db.commit()
        finally:
            db.close()

    def mark_session_read(self, session_id: str):
        """Clear unread indicator for a chat session."""
        db = self.SessionLocal()
        try:
            session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
            if session:
                session.has_unread = False
                db.commit()
        finally:
            db.close()

    def get_pending_approvals_for_session(self, session_id: str):
        """Get pending approvals linked to a specific chat session."""
        db = self.SessionLocal()
        try:
            return db.query(PendingApproval).filter(
                PendingApproval.session_id == session_id,
                PendingApproval.status == "pending"
            ).all()
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