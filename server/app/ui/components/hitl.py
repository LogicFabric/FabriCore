from nicegui import ui, app
import logging
import json

logger = logging.getLogger(__name__)

class HITLDialog:
    def __init__(self, data_manager):
        self.data_manager = data_manager
        self.dialog = ui.dialog().props('maximized')
        self._build_dialog()

    def open(self):
        self.refresh_hitl_dialog()
        self.dialog.open()

    def _build_dialog(self):
        with self.dialog:
            with ui.card().classes('w-full max-w-4xl mx-auto').style('max-height: 90vh; overflow-y: auto'):
                with ui.row().classes('w-full items-center justify-between mb-4'):
                    ui.label('🛡️ Human-in-the-Loop Security').classes('text-2xl font-bold')
                    ui.button(icon='close', on_click=self.dialog.close).props('flat round')

                ui.markdown(
                    '**Configure which tools require human approval before execution, and which commands are blocked entirely.**\n\n'
                    'Each agent can have its own security policy. Changes are synced to the agent immediately.'
                ).classes('text-sm text-gray-600 dark:text-gray-400 mb-4')

                self.hitl_agents_container = ui.column().classes('w-full gap-4')

    def refresh_hitl_dialog(self):
        self.hitl_agents_container.clear()
        from app.models.db import Agent, PendingApproval
        db = self.data_manager.get_db()
        try:
            agents = db.query(Agent).all()
            with self.hitl_agents_container:
                if not agents:
                    ui.label("No agents registered. Connect an agent first.").classes('italic text-gray-500')
                else:
                    for agent in agents:
                        self._render_agent_policy_card(agent)

                # Pending approvals summary
                pending = db.query(PendingApproval).filter(PendingApproval.status == "pending").all()
                if pending:
                    ui.separator().classes('my-4')
                    ui.label(f'⏳ {len(pending)} Pending Approval(s)').classes('text-lg font-bold text-orange-500')
                    for p in pending:
                        with ui.card().classes('w-full p-3 border border-orange-300 dark:border-orange-700 bg-orange-50 dark:bg-orange-900/20'):
                            with ui.row().classes('w-full items-center justify-between'):
                                with ui.column().classes('gap-0'):
                                    ui.label(f"Tool: {p.tool_name}").classes('font-bold')
                                    ui.label(f"Agent: {p.agent_id[:12]}... | Args: {json.dumps(p.arguments)[:60]}...").classes('text-xs text-gray-500')
                                ui.label('View in chat →').classes('text-xs text-blue-500 italic')
        finally:
            db.close()

    def _render_agent_policy_card(self, agent):
        current_policy = self.data_manager.get_agent_policy(agent.id)
        is_online = agent.status == 'online'
        hitl_enabled = current_policy.get('hitl_enabled', False)

        with ui.card().classes('w-full p-4 border-l-4').classes('border-green-500' if is_online else 'border-gray-400'):
            with ui.row().classes('w-full items-center justify-between mb-3'):
                with ui.column().classes('gap-0'):
                    ui.label(f"{agent.hostname} ({agent.id[:8]}...)").classes('text-lg font-bold')
                    ui.label(f"{agent.platform} | {agent.status.upper()}").classes('text-sm text-gray-500')

                if hitl_enabled: ui.badge('HITL ACTIVE', color='orange').props('outline')
                else: ui.badge('HITL OFF', color='gray').props('outline')

            hitl_switch = ui.switch('Enable Human-in-the-Loop', value=hitl_enabled).classes('mb-2')
            ui.label('Blocked Commands').classes('font-semibold text-sm mt-2')
            ui.label('Commands that will be refused outright (comma separated)').classes('text-xs text-gray-500')
            blocked_input = ui.textarea(value=", ".join(current_policy.get('blocked_commands', [])), placeholder='rm -rf /, shutdown, reboot...').classes('w-full').props('rows=2')

            ui.label('Require Approval For').classes('font-semibold text-sm mt-2')
            ui.label('Tool names that need admin approval before execution (comma separated)').classes('text-xs text-gray-500')
            approval_input = ui.textarea(value=", ".join(current_policy.get('requires_approval_for', [])), placeholder='run_command, write_file...').classes('w-full').props('rows=2')

            async def save_hitl_policy():
                new_policy = {
                    "hitl_enabled": hitl_switch.value,
                    "blocked_commands": [x.strip() for x in blocked_input.value.split(',') if x.strip()],
                    "requires_approval_for": [x.strip() for x in approval_input.value.split(',') if x.strip()]
                }
                if self.data_manager.update_agent_policy(agent.id, new_policy):
                    from app.core.dependencies import get_agent_manager
                    am = get_agent_manager()
                    await am.sync_policy(agent.id, new_policy)
                    ui.notify(f"✅ Policy synced to {agent.hostname}", type='positive')
                    self.refresh_hitl_dialog()
                else: ui.notify("Failed to update policy", type='negative')

            ui.button('Save Policy', icon='save', on_click=save_hitl_policy).props('color=primary outline').classes('mt-3')
