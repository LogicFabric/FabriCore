from nicegui import ui, app
import logging
import uuid
import json
import asyncio
from app.services.tools import get_tool_definitions

logger = logging.getLogger(__name__)

class ChatInterface:
    def __init__(self, data_manager, llm_service, tool_executor, context_label, context_bar, session_list_refresh_callback):
        self.data_manager = data_manager
        self.llm_service = llm_service
        self.tool_executor = tool_executor
        self.context_label = context_label
        self.context_bar = context_bar
        self.session_list_refresh_callback = session_list_refresh_callback
        
        self.active_session_id = app.storage.user.get('current_session_id')
        self.chat_messages = []
        self.total_tokens_used = 0
        self.chat_container = None

    def set_container(self, container):
        self.chat_container = container

    async def load_chat(self, session_id: str):
        """Load messages from a session into the UI."""
        self.active_session_id = session_id
        app.storage.user['current_session_id'] = session_id
        self.data_manager.mark_session_read(session_id)

        self.chat_container.clear()
        self.chat_messages = []
        self.total_tokens_used = 0
        self._update_context_usage()

        messages = self.data_manager.get_chat_messages(session_id)
        for msg in messages:
            self.chat_messages.append({"role": msg.role, "content": msg.content})
            estimated_tokens = max(1, len(msg.content) // 4)
            self.total_tokens_used += estimated_tokens

            metadata = msg.metadata_json or {}
            with self.chat_container:
                if metadata.get('type') == 'approval_request':
                    self._render_approval_card(metadata.get('approval_id'), msg.content, metadata.get('status', 'pending'))
                elif msg.role == 'user':
                    self._render_user_message(msg.content)
                else:
                    self._render_assistant_message(msg.content)

        self._update_context_usage()
        self.session_list_refresh_callback()

    def _update_context_usage(self):
        ctx_size = self.llm_service.context_size or 4096
        self.context_label.set_text(f'{self.total_tokens_used} / {ctx_size}')
        self.context_bar.set_value(self.total_tokens_used / ctx_size if ctx_size > 0 else 0.0)

    async def send_message(self, text_input):
        msg = text_input.value
        if not msg: return
        text_input.set_value('')

        self.chat_messages.append({"role": "user", "content": msg})
        with self.chat_container:
            self._render_user_message(msg)

        if not self.llm_service.model:
            with self.chat_container:
                self._render_assistant_message('⚠️ **No model loaded.** Please go to Settings → Models to load a model.')
            return

        if not self.active_session_id:
            session_title = msg[:30] + ('...' if len(msg) > 30 else '')
            session = self.data_manager.create_chat_session(title=session_title)
            self.active_session_id = session.id
            app.storage.user['current_session_id'] = self.active_session_id
            self.session_list_refresh_callback()

        pinned_session_id = self.active_session_id
        pinned_chat_container = self.chat_container
        pinned_chat_messages = self.chat_messages
        self.data_manager.save_chat_message(pinned_session_id, 'user', msg)

        system_prompt = app.storage.user.get('system_prompt', 'You are FabriCore, an AI assistant...')
        loop_messages = [{"role": "system", "content": system_prompt}] + list(pinned_chat_messages[-10:])
        
        await self._run_agent_loop(pinned_session_id, pinned_chat_container, pinned_chat_messages, loop_messages)

    async def _run_agent_loop(self, pinned_session_id, pinned_chat_container, pinned_chat_messages, loop_messages):
        with pinned_chat_container:
            thinking_row = ui.row().classes('w-full justify-start')
            with thinking_row:
                with ui.avatar(color='primary', text_color='white'): ui.icon('smart_toy')
                ui.spinner('dots', size='2em')

        try:
            temperature = app.storage.user.get('model_temperature', 0.7)
            max_tokens = int(app.storage.user.get('model_max_tokens', 1024))
            max_agent_turns = int(app.storage.user.get('agent_max_turns', 15))

            for turn in range(max_agent_turns):
                response = await self.llm_service.generate(messages=loop_messages, tools=get_tool_definitions(), max_tokens=max_tokens, temperature=temperature)
                content = response["content"]
                tool_call = response.get("tool_call")

                usage = response.get("usage", {})
                self.total_tokens_used += usage.get("total_tokens", usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0))
                self._update_context_usage()

                if not tool_call:
                    pinned_chat_messages.append({"role": "assistant", "content": content})
                    self.data_manager.save_chat_message(pinned_session_id, 'assistant', content)
                    if self.active_session_id == pinned_session_id:
                        with pinned_chat_container: self._render_assistant_message(content)
                    else:
                        self.data_manager.mark_session_unread(pinned_session_id)
                        self.session_list_refresh_callback()
                    break

                loop_messages.append({"role": "assistant", "content": json.dumps(tool_call)})
                tool_name, tool_args = tool_call["tool"], tool_call.get("params", {})
                tool_result = await self.tool_executor.execute(tool_name, tool_args)

                if isinstance(tool_result, dict) and tool_result.get("status") == "paused":
                    await self._handle_hitl_pause(pinned_session_id, pinned_chat_container, tool_name, tool_args)
                    break

                loop_messages.append({"role": "system", "content": f"Observation: {json.dumps(tool_result)}"})
            else:
                if self.active_session_id == pinned_session_id:
                    with pinned_chat_container: ui.label("⚠️ Max turns reached.").classes('text-red-500 text-xs')
        except Exception as e:
            logger.error(f"Generation error: {e}")
            if self.active_session_id == pinned_session_id:
                with pinned_chat_container:
                    with ui.row().classes('w-full justify-start'):
                        with ui.avatar(color='red', text_color='white'): ui.icon('error')
                        with ui.card().classes('bg-red-100 dark:bg-red-900 p-3'): ui.markdown(f'❌ **Error:** {str(e)}')
        finally:
            try: thinking_row.delete()
            except: pass

    async def _handle_hitl_pause(self, session_id, container, tool_name, tool_args):
        approval_id, exec_id = str(uuid.uuid4()), str(uuid.uuid4())
        from app.models.db import PendingApproval
        from app.core.dependencies import get_db
        db = next(get_db())
        db.add(PendingApproval(id=approval_id, execution_id=exec_id, agent_id=tool_args.get("agent_id", "unknown"), tool_name=tool_name, arguments=tool_args, status="pending", session_id=session_id))
        db.commit()
        db.close()

        approval_content = f"🛡️ **Approval Required**\n\nTool: `{tool_name}`\nArgs: `{json.dumps(tool_args)}`"
        self.data_manager.save_chat_message(session_id, 'assistant', approval_content, metadata={"type": "approval_request", "approval_id": approval_id, "status": "pending"})
        if self.active_session_id == session_id:
            with container: self._render_approval_card(approval_id, approval_content, 'pending')
        else:
            self.data_manager.mark_session_unread(session_id)
            self.session_list_refresh_callback()

    def _render_user_message(self, content: str):
        with ui.row().classes('w-full justify-end'):
            with ui.card().classes('bg-blue-600 text-white p-3 rounded-tl-xl rounded-bl-xl rounded-br-xl'): ui.markdown(content)
            with ui.avatar(color='gray-300'): ui.icon('person')

    def _render_assistant_message(self, content: str):
        with ui.row().classes('w-full justify-start'):
            with ui.avatar(color='primary', text_color='white'): ui.icon('smart_toy')
            with ui.card().classes('bg-gray-100 dark:bg-gray-700 p-3 rounded-tr-xl rounded-br-xl rounded-bl-xl'): ui.markdown(content)

    def _render_approval_card(self, approval_id: str, content: str, status: str = 'pending'):
        with ui.row().classes('w-full justify-start'):
            with ui.avatar(color='orange', text_color='white'): ui.icon('shield')
            with ui.card().classes('bg-amber-50 dark:bg-amber-900/30 border border-amber-300 dark:border-amber-700 p-4 rounded-tr-xl rounded-br-xl rounded-bl-xl w-full max-w-2xl'):
                ui.markdown(content)
                if status == 'pending' and approval_id:
                    with ui.row().classes('gap-2 mt-3'):
                        ui.button("✅ Approve", on_click=lambda: self._handle_approval(approval_id, True)).props('color=positive outline')
                        ui.button("❌ Deny", on_click=lambda: self._handle_approval(approval_id, False)).props('color=negative outline')
                elif status == 'approved': ui.label('✅ Approved').classes('text-green-600 text-sm font-bold mt-2')
                elif status == 'rejected': ui.label('❌ Denied').classes('text-red-600 text-sm font-bold mt-2')

    async def _handle_approval(self, approval_id, approved):
        from app.models.db import PendingApproval
        from app.core.dependencies import get_db
        db = next(get_db())
        item = db.query(PendingApproval).get(approval_id)
        if not item: 
            db.close()
            return
        
        if approved:
            item.status = "approved"
            db.commit()
            ui.notify(f"Approved {item.tool_name}", type='positive')
            try:
                res = await self.tool_executor.execute(item.tool_name, item.arguments, approved_by="admin")
                result_msg = f"✅ **Approved & Executed**: `{item.tool_name}`\n\nResult: ```\n{json.dumps(res, indent=2)}\n```"
                self.data_manager.save_chat_message(item.session_id, 'assistant', result_msg, metadata={"type": "approval_result", "approval_id": approval_id, "raw_result": res})
                
                if self.active_session_id == item.session_id:
                    self.chat_messages.append({"role": "assistant", "content": result_msg})
                    with self.chat_container: self._render_assistant_message(result_msg)
                    # Resume loop logic simplified for brevity - in production you'd rebuild history
                    await self.load_chat(item.session_id) # Refresh to show result and potentially resume
            except Exception as e: ui.notify(f"Failed: {e}", type='negative')
        else:
            item.status = "rejected"
            db.commit()
            deny_msg = f"❌ **Denied**: `{item.tool_name}`"
            self.data_manager.save_chat_message(item.session_id, 'assistant', deny_msg, metadata={"type": "approval_result", "approval_id": approval_id})
            if self.active_session_id == item.session_id:
                self.chat_messages.append({"role": "assistant", "content": deny_msg})
                with self.chat_container: self._render_assistant_message(deny_msg)
        db.close()
        self.session_list_refresh_callback()
