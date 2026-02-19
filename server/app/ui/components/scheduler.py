from nicegui import ui, app
import logging
import uuid
import json
from app.services.scheduler import SchedulerService

logger = logging.getLogger(__name__)

class SchedulerDialog:
    def __init__(self, data_manager, scheduler_service):
        self.data_manager = data_manager
        self.scheduler_service = scheduler_service
        self.dialog = ui.dialog().props('maximized')
        self.editing_schedule_id = None
        self._build_dialog()

    def open(self):
        self._refresh_agents_list()
        self.refresh_schedules_dialog()
        self.dialog.open()

    def _refresh_agents_list(self):
        from app.models.db import Agent
        db = self.data_manager.get_db()
        try:
            agents = db.query(Agent).all()
            options = {a.id: f"{a.hostname} ({a.id[:12]}...)" for a in agents}
            self.sched_agent_input.options = options
            self.sched_agent_input.update()
        finally:
            db.close()

    def _build_dialog(self):
        with self.dialog:
            with ui.card().classes('w-full max-w-4xl mx-auto').style('max-height: 90vh; overflow-y: auto'):
                with ui.row().classes('w-full items-center justify-between mb-4'):
                    ui.label('⏰ Autonomous Schedules').classes('text-2xl font-bold')
                    ui.button(icon='close', on_click=self.dialog.close).props('flat round')

                # --- Add New Schedule Form ---
                with ui.card().classes('w-full p-4 mb-4 border border-gray-200 dark:border-gray-700'):
                    ui.label("Add/Edit Schedule").classes('text-lg font-bold mb-2')
                    with ui.grid(columns=2).classes('w-full gap-4'):
                        self.sched_cron_input = ui.input("Cron Expression", placeholder="*/30 * * * *")
                        self.sched_agent_input = ui.select(options={}, label="Agent", with_input=True).tooltip('Select the target agent')
                        self.sched_task_input = ui.textarea("Task Instruction", placeholder="Check disk space...").classes('col-span-2')
                        self.sched_model_input = ui.input("Required Model (Optional)", placeholder="model-name.gguf").classes('col-span-2')

                    with ui.row().classes('w-full items-center gap-4 mt-2'):
                        self.sched_persistent_switch = ui.switch('Use Persistent Chat', value=False).tooltip('ON: Reuse the same chat session for every run. OFF: Create a new chat each time.')

                    with ui.row().classes('gap-2'):
                        self.add_btn = ui.button("Add Schedule", on_click=self.add_schedule_handler, icon="add").props('color=primary').classes('mt-2')
                        self.cancel_btn = ui.button("Cancel", on_click=self.cancel_edit, icon="cancel").props('flat').classes('mt-2')
                        self.cancel_btn.set_visibility(False)

                ui.separator().classes('my-4')
                ui.label("Active Schedules").classes('text-lg font-bold mb-2')
                self.schedules_list_container = ui.column().classes('w-full gap-2')

    def cancel_edit(self):
        self.editing_schedule_id = None
        self.sched_cron_input.value = ""
        self.sched_task_input.value = ""
        self.sched_model_input.value = ""
        self.sched_agent_input.value = ""
        self.sched_persistent_switch.value = False
        self.add_btn.set_text("Add Schedule")
        self.add_btn.props('color=primary')
        self.cancel_btn.set_visibility(False)

    async def add_schedule_handler(self):
        if not self.sched_cron_input.value or not self.sched_task_input.value:
            ui.notify("Cron and Task are required", type="warning")
            return

        from app.models.db import Schedule
        from app.core.dependencies import get_db as dep_get_db

        try:
            db = next(dep_get_db())
            sch_id = self.editing_schedule_id or str(uuid.uuid4())
            cron_val = self.sched_cron_input.value
            task_val = self.sched_task_input.value
            model_val = self.sched_model_input.value or None
            agent_val = self.sched_agent_input.value or None
            persistent_val = self.sched_persistent_switch.value

            if self.editing_schedule_id:
                sch = db.query(Schedule).get(self.editing_schedule_id)
                if sch:
                    sch.cron_expression = cron_val
                    sch.task_instruction = task_val
                    sch.required_model = model_val
                    sch.agent_id = agent_val
                    sch.use_persistent_chat = persistent_val
                    ui.notify("Schedule updated", type="positive")
            else:
                sch = Schedule(id=sch_id, cron_expression=cron_val, task_instruction=task_val, required_model=model_val, agent_id=agent_val, use_persistent_chat=persistent_val)
                db.add(sch)
                ui.notify("Schedule added", type="positive")
            
            db.commit()
            db.close()

            if self.editing_schedule_id:
                self.scheduler_service.remove_job(sch_id)
            self.scheduler_service.add_job(sch_id, cron_val, task_val, model_val, agent_val)
            self.cancel_edit()
            self.refresh_schedules_dialog()
        except Exception as e:
            ui.notify(f"Error saving schedule: {e}", type="negative")

    def refresh_schedules_dialog(self):
        self.schedules_list_container.clear()
        from app.models.db import Schedule
        from app.core.dependencies import get_db as dep_get_db
        try:
            db = next(dep_get_db())
            schedules = db.query(Schedule).all()
            with self.schedules_list_container:
                if not schedules:
                    ui.label("No active schedules.").classes('text-gray-500 italic')
                else:
                    for s in schedules:
                        self._render_schedule_item(s)
            db.close()
        except Exception as e:
            ui.notify(f"Error loading schedules: {e}", type="negative")

    def _render_schedule_item(self, s):
        next_run = self.scheduler_service.get_next_run_time(s.id)
        with ui.card().classes('w-full p-3 border border-gray-200 dark:border-gray-700'):
            with ui.row().classes('w-full items-center justify-between'):
                with ui.column().classes('gap-0 flex-grow'):
                    ui.label(f"⏱ {s.cron_expression}").classes('font-bold font-mono')
                    ui.label(f"{s.task_instruction}").classes('text-sm')
                    with ui.row().classes('gap-4'):
                        if s.agent_id: ui.label(f"Agent: {s.agent_id[:12]}...").classes('text-xs text-gray-500')
                        if s.required_model: ui.label(f"Model: {s.required_model}").classes('text-xs text-gray-500')
                        ui.label(f"{'🔄 Persistent' if s.use_persistent_chat else '🆕 New chat each run'}").classes('text-xs text-blue-500')
                        if next_run: ui.label(f"Next: {next_run}").classes('text-xs text-green-500')

                with ui.row().classes('gap-1'):
                    async def toggle_active(s_id=s.id, currently_active=s.is_active):
                        from app.models.db import Schedule
                        from app.core.dependencies import get_db as dep_get_db
                        try:
                            d_db = next(dep_get_db())
                            sched = d_db.query(Schedule).get(s_id)
                            if sched:
                                sched.is_active = not currently_active
                                d_db.commit()
                                if not sched.is_active: self.scheduler_service.remove_job(s_id)
                                else: self.scheduler_service.add_job(s_id, sched.cron_expression, sched.task_instruction, sched.required_model, sched.agent_id)
                            d_db.close()
                            self.refresh_schedules_dialog()
                        except Exception as ex: ui.notify(f"Error: {ex}", type="negative")

                    async def delete_schedule(s_id=s.id):
                        from app.models.db import Schedule
                        from app.core.dependencies import get_db as dep_get_db
                        try:
                            d_db = next(dep_get_db())
                            d_db.query(Schedule).filter(Schedule.id == s_id).delete()
                            d_db.commit()
                            d_db.close()
                            self.scheduler_service.remove_job(s_id)
                            ui.notify("Schedule deleted", type="info")
                            self.refresh_schedules_dialog()
                        except Exception as ex: ui.notify(f"Error deleting: {ex}", type="negative")

                    def edit_schedule(sched=s):
                        self.editing_schedule_id = sched.id
                        self.sched_cron_input.value = sched.cron_expression
                        self.sched_task_input.value = sched.task_instruction
                        self.sched_model_input.value = sched.required_model or ""
                        self.sched_agent_input.value = sched.agent_id or ""
                        self.sched_persistent_switch.value = sched.use_persistent_chat
                        self.add_btn.set_text("Update Schedule")
                        self.add_btn.props('color=orange')
                        self.cancel_btn.set_visibility(True)
                        ui.notify(f"Editing schedule {sched.id[:8]}", type="info")

                    icon = 'pause' if s.is_active else 'play_arrow'
                    ui.button(icon='edit', on_click=edit_schedule).props('flat round').tooltip('Edit')
                    ui.button(icon=icon, on_click=lambda: toggle_active()).props('flat round').tooltip('Pause/Resume')
                    ui.button(icon='delete', on_click=lambda: delete_schedule()).props('flat round color=negative').tooltip('Delete')
