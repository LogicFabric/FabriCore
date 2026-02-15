from datetime import datetime
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.core.dependencies import get_db, get_agent_manager, get_model_manager, get_data_manager, get_llm_service
from app.models.db import Schedule, Agent, AuditLog, PendingApproval
from app.services.tools import ToolExecutor
import uuid
import json

logger = logging.getLogger(__name__)

class SchedulerService:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.llm_service = get_llm_service()
        self.tool_executor = ToolExecutor(get_data_manager())
        
    def start(self):
        self.scheduler.start()
        logger.info("Scheduler started.")
        
    def add_job(self, schedule_id: str, cron_expression: str, task_instruction: str, model_name: str, agent_id: str):
        self.scheduler.add_job(
            self.run_scheduled_job,
            CronTrigger.from_crontab(cron_expression),
            id=schedule_id,
            args=[schedule_id],
            replace_existing=True
        )
        logger.info(f"Added job {schedule_id}: {task_instruction}")

    async def run_scheduled_job(self, schedule_id: str):
        logger.info(f"Running scheduled job: {schedule_id}")
        db = next(get_db())
        job = db.query(Schedule).get(schedule_id)
        
        if not job or not job.is_active:
            return

        try:
            # 1. Check/Switch Model
            model_manager = get_model_manager()
            current_model = model_manager.current_model
            if job.required_model and current_model != job.required_model:
                logger.info(f"Switching model to {job.required_model} for scheduled task...")
                await model_manager.load_model(job.required_model)
                # Wait a bit for model to load? load_model is async and should wait.
            
            # 2. Run Agent Loop (Simplified version of main.py loop)
            # We need to construct a "chat" context or just run the LLM loop here.
            # Reuse logic? ideally extract agent loop from main.py to a service.
            # For now, let's implement a concise loop here.
            
            system_prompt = f"You are executing a scheduled task: {job.task_instruction}. You are an autonomous agent."
            messages = [{"role": "system", "content": system_prompt}]
            
            # Max 5 turns
            for turn in range(5):
                response = await self.llm_service.generate(
                    messages=messages,
                    tools=self.tool_executor.get_tool_definitions(),
                    max_tokens=1024
                )
                
                tool_call = response.get("tool_call")
                content = response["content"]
                
                if not tool_call:
                    # Done
                    logger.info(f"Job {schedule_id} finished: {content}")
                    # Log successful completion?
                    break
                
                # Execute Tool
                tool_name = tool_call["tool"]
                tool_args = tool_call.get("params", {})
                
                # We need to inject agent_id if missing?
                # The prompt should ensure LLM uses the correct agent_id if known.
                # Or we force it here?
                if "agent_id" not in tool_args and job.agent_id:
                     tool_args["agent_id"] = job.agent_id

                tool_result = await self.tool_executor.execute(tool_name, tool_args)
                
                # Append to history
                messages.append({"role": "assistant", "content": json.dumps(tool_call)})
                messages.append({"role": "system", "content": f"Observation: {json.dumps(tool_result)}"})
                
                # Check for HITL pause
                if tool_result.get("status") == "paused":
                    logger.info(f"Job {schedule_id} paused for approval.")
                    
                    # Create PendingApproval
                    approval_entry = PendingApproval(
                        id=str(uuid.uuid4()),
                        execution_id=schedule_id, # Linking to schedule ID for now
                        agent_id=tool_args.get("agent_id", "unknown"),
                        tool_name=tool_name,
                        arguments=tool_args,
                        status="pending"
                    )
                    db.add(approval_entry)
                    db.commit()
                    break

        except Exception as e:
            logger.error(f"Job {schedule_id} failed: {e}")
        finally:
            db.close()
