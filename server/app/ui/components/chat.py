from nicegui import ui, app
import logging
import uuid
import json
import asyncio
from pathlib import Path
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
                    timestamp_str = msg.timestamp.strftime('%H:%M:%S') if msg.timestamp else None
                    self._render_user_message(msg.content, timestamp_str)
                else:
                    timestamp_str = msg.timestamp.strftime('%H:%M:%S') if msg.timestamp else None
                    self._render_assistant_message(msg.content, timestamp_str)

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
        from datetime import datetime
        now_str = datetime.now().strftime('%H:%M:%S')
        with self.chat_container:
            self._render_user_message(msg, now_str)

        if not self.llm_service.model:
            with self.chat_container:
                self._render_assistant_message('⚠️ **No model loaded.** Please go to Settings → Models to load a model.', now_str)
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
        
        self.current_task = asyncio.create_task(self._run_agent_loop(pinned_session_id, pinned_chat_container, pinned_chat_messages, loop_messages))
        try:
            await self.current_task
        except asyncio.CancelledError:
            pass

    def abort_generation(self):
        if hasattr(self, 'current_task') and self.current_task and not self.current_task.done():
            self.current_task.cancel()
            msg = "⚠️ **Generation aborted by user.**"
            if getattr(self, 'active_session_id', None):
                self.chat_messages.append({"role": "assistant", "content": msg})
                from datetime import datetime
                now_str = datetime.now().strftime('%H:%M:%S')
                with self.chat_container: self._render_assistant_message(msg, now_str)
                self.data_manager.save_chat_message(self.active_session_id, 'assistant', msg)

    def handle_upload(self, e):
        if not self.active_session_id:
            session = self.data_manager.create_chat_session(title="New Chat")
            self.active_session_id = session.id
            app.storage.user['current_session_id'] = self.active_session_id
            self.session_list_refresh_callback()

        upload_dir = Path("server/data/uploads") / self.active_session_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = upload_dir / e.name
        with open(file_path, "wb") as f:
            f.write(e.content.read())
            
        msg = f"📎 Uploaded file: `{e.name}`. File path for tool usage: `{file_path.absolute()}`"
        self.chat_messages.append({"role": "user", "content": msg})
        from datetime import datetime
        now_str = datetime.now().strftime('%H:%M:%S')
        with self.chat_container:
            self._render_user_message(msg, now_str)
        self.data_manager.save_chat_message(self.active_session_id, 'user', msg)
        ui.notify(f"Uploaded {e.name}", type='positive')

    async def _run_agent_loop(self, pinned_session_id, pinned_chat_container, pinned_chat_messages, loop_messages):
        from datetime import datetime

        # --- Build the Agent Status Panel ---
        with pinned_chat_container:
            status_card = ui.card().classes(
                'w-full max-w-3xl bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 '
                'rounded-xl p-0 overflow-hidden'
            )
        
        with status_card:
            # Header row: always visible
            with ui.row().classes('w-full items-center gap-2 px-4 py-2 bg-gray-100 dark:bg-gray-900/50 cursor-pointer').on(
                'click', lambda: steps_container.set_visibility(not steps_container.visible)
            ) as header_row:
                status_spinner = ui.spinner('dots', size='1.5em').classes('text-primary')
                status_icon = ui.icon('smart_toy').classes('text-primary text-lg')
                status_icon.set_visibility(False)
                status_label = ui.label('🤖 Thinking...').classes('text-sm font-medium text-gray-700 dark:text-gray-300 flex-grow')
                turn_badge = ui.badge('0', color='primary').classes('text-xs')
                expand_icon = ui.icon('expand_more').classes('text-gray-400 text-lg transition-transform')
                abort_btn = ui.button(icon='stop', on_click=self.abort_generation).props(
                    'flat round color=negative size=xs'
                ).tooltip('Abort')

            # Expandable steps log area (collapsed by default)
            steps_container = ui.column().classes('w-full px-4 py-2 gap-1 max-h-64 overflow-y-auto')
            steps_container.set_visibility(False)

        # Helper to add a step to the log
        def add_step(icon: str, text: str, color: str = 'text-gray-600 dark:text-gray-400'):
            with steps_container:
                with ui.row().classes(f'w-full items-start gap-2 {color}'):
                    ui.icon(icon).classes('text-sm mt-0.5 flex-shrink-0')
                    ui.label(text).classes('text-xs font-mono break-all')

        def update_status(text: str, turn: int):
            status_label.set_text(text)
            turn_badge.set_text(str(turn))

        try:
            temperature = app.storage.user.get('model_temperature', 0.7)
            max_tokens = int(app.storage.user.get('model_max_tokens', 8192))
            max_agent_turns = int(app.storage.user.get('agent_max_turns', 25))

            for turn in range(max_agent_turns):
                turn_num = turn + 1
                update_status(f'🧠 Turn {turn_num}/{max_agent_turns} — Generating response...', turn_num)
                add_step('psychology', f'[Turn {turn_num}] Sending {len(loop_messages)} messages to LLM...')

                response = await self.llm_service.generate(
                    messages=loop_messages,
                    tools=get_tool_definitions(),
                    max_tokens=max_tokens,
                    temperature=temperature
                )
                content = response["content"]
                tool_call = response.get("tool_call")

                usage = response.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                self.total_tokens_used = usage.get("total_tokens", prompt_tokens + completion_tokens)
                self._update_context_usage()

                add_step('token', f'Tokens: prompt={prompt_tokens}, completion={completion_tokens}')

                if not tool_call:
                    # Check if the LLM tried to make a tool call but parsing failed
                    if content and '"tool"' in content and '"params"' in content:
                        logger.warning(f"Unparseable tool call detected (turn {turn_num}), asking LLM to retry. Content length: {len(content)}")
                        add_step('warning', f'⚠️ Tool call parse failed (len={len(content)}). Asking LLM to retry with shorter command.', 'text-amber-600 dark:text-amber-400')
                        update_status(f'⚠️ Turn {turn_num}/{max_agent_turns} — Retrying (parse error)...', turn_num)
                        loop_messages.append({"role": "assistant", "content": content})
                        loop_messages.append({"role": "user", "content": "ERROR: Your tool call could not be parsed. Your command was too long or malformed. Break it into SMALLER steps. Use multiple short `echo 'line' >> file` commands instead of one giant heredoc. Try again with a simpler, shorter command."})
                        continue

                    # Normal text response — agent is done
                    add_step('check_circle', f'✅ Agent finished with text response.', 'text-green-600 dark:text-green-400')
                    update_status(f'✅ Done ({turn_num} turns)', turn_num)
                    pinned_chat_messages.append({"role": "assistant", "content": content})
                    self.data_manager.save_chat_message(pinned_session_id, 'assistant', content)
                    if self.active_session_id == pinned_session_id:
                        now_str = datetime.now().strftime('%H:%M:%S')
                        with pinned_chat_container:
                            self._render_assistant_message(content, now_str)
                    else:
                        self.data_manager.mark_session_unread(pinned_session_id)
                        self.session_list_refresh_callback()
                    break

                # --- Tool call detected ---
                tool_name = tool_call["tool"]
                tool_args = tool_call.get("params", {})
                agent_id = tool_args.get("agent_id", "?")
                cmd_preview = tool_args.get("command", tool_args.get("path", ""))
                if len(cmd_preview) > 80:
                    cmd_preview = cmd_preview[:77] + "..."

                update_status(f'🔧 Turn {turn_num}/{max_agent_turns} — Executing `{tool_name}`...', turn_num)
                add_step('build', f'🔧 Calling: {tool_name}({agent_id}) → {cmd_preview}', 'text-blue-600 dark:text-blue-400')

                loop_messages.append({"role": "assistant", "content": json.dumps(tool_call)})
                tool_result = await self.tool_executor.execute(tool_name, tool_args)

                if isinstance(tool_result, dict) and tool_result.get("status") == "paused":
                    add_step('shield', f'🛡️ HITL: Approval required for {tool_name}', 'text-amber-600 dark:text-amber-400')
                    update_status(f'🛡️ Paused — waiting for approval', turn_num)
                    await self._handle_hitl_pause(pinned_session_id, pinned_chat_container, tool_name, tool_args)
                    break

                # Summarize result for the step log
                result_preview = json.dumps(tool_result)
                if len(result_preview) > 120:
                    result_preview = result_preview[:117] + "..."
                
                success = tool_result.get("success", False) if isinstance(tool_result, dict) else False
                result_icon = 'check' if success else 'error_outline'
                result_color = 'text-green-600 dark:text-green-400' if success else 'text-red-500'
                add_step(result_icon, f'Result: {result_preview}', result_color)

                loop_messages.append({"role": "user", "content": f"Observation: {json.dumps(tool_result)}"})
            else:
                # Max turns exhausted
                add_step('error', f'❌ Max turns ({max_agent_turns}) exhausted!', 'text-red-500')
                update_status(f'❌ Max turns reached ({max_agent_turns})', max_agent_turns)
                # Auto-expand steps so user can see full trace
                steps_container.set_visibility(True)
                # Save a summary to chat
                summary = f"⚠️ **Max turns reached ({max_agent_turns}).** The agent could not complete the task within the turn limit. Expand the status panel above to see the full execution trace."
                pinned_chat_messages.append({"role": "assistant", "content": summary})
                self.data_manager.save_chat_message(pinned_session_id, 'assistant', summary)
                if self.active_session_id == pinned_session_id:
                    now_str = datetime.now().strftime('%H:%M:%S')
                    with pinned_chat_container:
                        self._render_assistant_message(summary, now_str)

        except asyncio.CancelledError:
            logger.info("Agent loop cancelled by user.")
            add_step('cancel', '🚫 Aborted by user.', 'text-orange-500')
            update_status('🚫 Aborted', turn_num if 'turn_num' in dir() else 0)
        except Exception as e:
            logger.error(f"Generation error: {e}")
            add_step('error', f'💥 Error: {str(e)}', 'text-red-500')
            update_status(f'💥 Error', 0)
            steps_container.set_visibility(True)
            if self.active_session_id == pinned_session_id:
                with pinned_chat_container:
                    with ui.row().classes('w-full justify-start'):
                        with ui.avatar(color='red', text_color='white'): ui.icon('error')
                        with ui.card().classes('bg-red-100 dark:bg-red-900 p-3'): ui.markdown(f'❌ **Error:** {str(e)}')
        finally:
            # Replace spinner with final icon
            try:
                status_spinner.set_visibility(False)
                status_icon.set_visibility(True)
                abort_btn.set_visibility(False)
            except:
                pass

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

    def _render_user_message(self, content: str, timestamp: str = None):
        with ui.row().classes('w-full justify-end'):
            with ui.column().classes('items-end gap-0'):
                with ui.card().classes('bg-blue-600 text-white p-3 rounded-tl-xl rounded-bl-xl rounded-br-xl'): ui.markdown(content)
                if timestamp:
                    ui.label(timestamp).classes('text-[10px] text-gray-400 mt-1 mr-1')
            with ui.avatar(color='gray-300'): ui.icon('person')

    def _render_assistant_message(self, content: str, timestamp: str = None):
        with ui.row().classes('w-full justify-start'):
            with ui.avatar(color='primary', text_color='white'): ui.icon('smart_toy')
            with ui.column().classes('items-start gap-0'):
                with ui.card().classes('bg-gray-100 dark:bg-gray-700 p-3 rounded-tr-xl rounded-br-xl rounded-bl-xl'): ui.markdown(content)
                if timestamp:
                    ui.label(timestamp).classes('text-[10px] text-gray-400 mt-1 ml-1')

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
                    from datetime import datetime
                    now_str = datetime.now().strftime('%H:%M:%S')
                    with self.chat_container: self._render_assistant_message(result_msg, now_str)
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
                from datetime import datetime
                now_str = datetime.now().strftime('%H:%M:%S')
                with self.chat_container: self._render_assistant_message(deny_msg, now_str)
        db.close()
        self.session_list_refresh_callback()
