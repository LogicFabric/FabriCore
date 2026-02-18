# server/app/services/scheduler.py
from datetime import datetime
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.core.dependencies import get_db, get_agent_manager, get_model_manager, get_data_manager, get_llm_service
from app.models.db import Schedule, Agent, AuditLog, PendingApproval
from app.services.tools import ToolExecutor, get_tool_definitions
import uuid
import json

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.llm_service = get_llm_service()
        self.data_manager = get_data_manager()
        self.tool_executor = ToolExecutor(self.data_manager)

    def start(self):
        """Start the scheduler and load existing jobs from DB."""
        self.scheduler.start()
        self._load_existing_jobs()
        logger.info("Scheduler started.")

    def _load_existing_jobs(self):
        """Register all active schedules from the database."""
        db = next(get_db())
        try:
            schedules = db.query(Schedule).filter(Schedule.is_active == True).all()
            for s in schedules:
                self.add_job(
                    s.id, s.cron_expression, s.task_instruction,
                    s.required_model, s.agent_id
                )
            logger.info(f"Loaded {len(schedules)} existing schedules.")
        except Exception as e:
            logger.error(f"Failed to load existing schedules: {e}")
        finally:
            db.close()

    def add_job(self, schedule_id: str, cron_expression: str, task_instruction: str,
                model_name: str, agent_id: str):
        self.scheduler.add_job(
            self.run_scheduled_job,
            CronTrigger.from_crontab(cron_expression),
            id=schedule_id,
            args=[schedule_id],
            replace_existing=True
        )
        logger.info(f"Added job {schedule_id}: {task_instruction}")

    def remove_job(self, schedule_id: str):
        """Remove a job from the scheduler."""
        try:
            self.scheduler.remove_job(schedule_id)
            logger.info(f"Removed job {schedule_id}")
        except Exception as e:
            logger.warning(f"Failed to remove job {schedule_id}: {e}")

    def get_next_run_time(self, schedule_id: str):
        """Get the next scheduled run time for a job."""
        try:
            job = self.scheduler.get_job(schedule_id)
            if job and job.next_run_time:
                return job.next_run_time.isoformat()
        except Exception:
            pass
        return None

    async def run_scheduled_job(self, schedule_id: str):
        logger.info(f"Running scheduled job: {schedule_id}")
        db = next(get_db())
        job = db.query(Schedule).get(schedule_id)

        if not job or not job.is_active:
            db.close()
            return

        try:
            # 1. Check/Switch Model (if needed)
            if job.required_model:
                model_manager = get_model_manager()
                current_model = self.llm_service.model_name
                if current_model != job.required_model:
                    logger.info(f"Switching model to {job.required_model} for scheduled task...")
                    await model_manager.load_model(job.required_model)

            # 2. Resolve or create chat session
            session_id = None
            if job.use_persistent_chat and job.chat_session_id:
                session_id = job.chat_session_id
            else:
                # Create a new chat session for this run
                session_title = f"[Scheduled] {job.task_instruction[:30]}"
                session = self.data_manager.create_chat_session(title=session_title)
                session_id = session.id
                if job.use_persistent_chat:
                    # Save this session ID for future runs
                    job.chat_session_id = session_id
                    db.commit()

            # 3. Run Agent Loop
            system_prompt = f"You are executing a scheduled task: {job.task_instruction}. You are an autonomous agent."
            messages = [{"role": "system", "content": system_prompt}]

            # Save initial user-like message to chat
            self.data_manager.save_chat_message(
                session_id, 'user',
                f"🤖 **Scheduled Task**: {job.task_instruction}",
                metadata={"type": "scheduled_trigger", "schedule_id": schedule_id}
            )

            final_content = ""
            for turn in range(5):
                response = await self.llm_service.generate(
                    messages=messages,
                    tools=get_tool_definitions(),
                    max_tokens=1024
                )

                tool_call = response.get("tool_call")
                content = response["content"]

                if not tool_call:
                    final_content = content
                    logger.info(f"Job {schedule_id} finished: {content}")
                    break

                # Execute Tool
                tool_name = tool_call["tool"]
                tool_args = tool_call.get("params", {})

                if "agent_id" not in tool_args and job.agent_id:
                    tool_args["agent_id"] = job.agent_id

                tool_result = await self.tool_executor.execute(tool_name, tool_args)

                messages.append({"role": "assistant", "content": json.dumps(tool_call)})
                messages.append({"role": "system", "content": f"Observation: {json.dumps(tool_result)}"})

                # Check for HITL pause
                if tool_result.get("status") == "paused":
                    logger.info(f"Job {schedule_id} paused for approval.")
                    approval_entry = PendingApproval(
                        id=str(uuid.uuid4()),
                        execution_id=schedule_id,
                        agent_id=tool_args.get("agent_id", "unknown"),
                        tool_name=tool_name,
                        arguments=tool_args,
                        status="pending",
                        session_id=session_id
                    )
                    db.add(approval_entry)
                    db.commit()

                    # Save approval request to chat
                    self.data_manager.save_chat_message(
                        session_id, 'assistant',
                        f"🛡️ **Approval Required**\n\nTool: `{tool_name}`\nArgs: `{json.dumps(tool_args)}`",
                        metadata={"type": "approval_request", "approval_id": approval_entry.id}
                    )
                    break
            else:
                final_content = "Agent stopped after max turns."

            # Save final response to chat
            if final_content:
                self.data_manager.save_chat_message(session_id, 'assistant', final_content)

            # Mark session as unread
            self.data_manager.mark_session_unread(session_id)

        except Exception as e:
            logger.error(f"Job {schedule_id} failed: {e}")
        finally:
            db.close()
