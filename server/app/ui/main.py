# server/app/ui/main.py
from nicegui import ui, app
from app.services.data_manager import DataManager
from app.services.model_manager import get_model_manager, AVAILABLE_GGUF_MODELS, MODELS_DIR
from app.services.llm_service import get_llm_service
from app.services.tools import ToolExecutor, get_tool_definitions
from datetime import datetime
from pathlib import Path
import asyncio
import logging
import uuid

logger = logging.getLogger(__name__)

# Singletons
data_manager = DataManager()


def init_ui():
    @ui.page('/', title='FabriCore')
    async def main_page():
        # Dark mode
        dark = ui.dark_mode()
        is_dark = app.storage.user.get('dark_mode', False)
        if is_dark:
            dark.enable()
        else:
            dark.disable()
        
        # Get services
        model_manager = get_model_manager()
        llm_service = get_llm_service()
        
        # Communication manager placeholder (will be properly injected)
        from app.services.communication_manager import CommunicationManager
        comm_manager = CommunicationManager()
        tool_executor = ToolExecutor(data_manager, comm_manager)
        
        # Chat history state
        chat_messages = []
        app.storage.user.setdefault('current_session_id', None)
        active_session_id = app.storage.user['current_session_id']
        
        # --- Settings Dialog ---
        settings_dialog = ui.dialog().props('maximized')
        
        def open_settings():
            settings_dialog.open()
        
        with settings_dialog:
            with ui.card().classes('w-full max-w-4xl mx-auto').style('max-height: 90vh; overflow-y: auto'):
                with ui.row().classes('w-full items-center justify-between mb-4'):
                    ui.label('Settings & System Status').classes('text-2xl font-bold')
                    ui.button(icon='close', on_click=settings_dialog.close).props('flat round')
                
                with ui.tabs().classes('w-full') as tabs:
                    agent_tab = ui.tab('Agents', icon='computer')
                    models_tab = ui.tab('Models', icon='psychology')
                    model_settings_tab = ui.tab('Model Settings', icon='tune')
                    config_tab = ui.tab('Configuration', icon='settings')
                
                with ui.tab_panels(tabs, value=agent_tab).classes('w-full').style('min-height: 400px'):
                    # Agents Tab
                    with ui.tab_panel(agent_tab):
                        ui.label('Connected Agents').classes('text-lg font-bold mb-2')
                        agents_table = ui.table(columns=[
                            {'name': 'id', 'label': 'ID', 'field': 'id'},
                            {'name': 'hostname', 'label': 'Hostname', 'field': 'hostname'},
                            {'name': 'status', 'label': 'Status', 'field': 'status'},
                            {'name': 'last_seen', 'label': 'Last Seen', 'field': 'last_seen'},
                        ], rows=[], row_key='id').classes('w-full')
                        
                        def refresh_agents():
                            db = data_manager.get_db()
                            try:
                                from app.models.db import Agent
                                agents = db.query(Agent).all()
                                rows = [{
                                    'id': a.id, 
                                    'hostname': a.hostname, 
                                    'status': a.status, 
                                    'last_seen': a.last_seen.isoformat() if a.last_seen else 'Never'
                                } for a in agents]
                                agents_table.rows = rows
                                agents_table.update()
                            finally:
                                db.close()
                        
                        ui.button('Refresh', icon='refresh', on_click=refresh_agents).props('flat')
                        refresh_agents()

                    # Models Tab
                    with ui.tab_panel(models_tab):
                        ui.label('Available GGUF Models').classes('text-lg font-bold mb-2')
                        
                        # Download progress area
                        with ui.row().classes('w-full items-center gap-2 mb-4') as download_progress_row:
                            download_progress_row.set_visibility(False)
                            download_spinner = ui.spinner('dots', size='lg')
                            download_progress_label = ui.label('Downloading...').classes('text-sm')
                        
                        # Model rows with status
                        model_rows = []
                        for m in AVAILABLE_GGUF_MODELS:
                            installed = model_manager.is_model_installed(m['id'], m['recommended'])
                            model_rows.append({
                                'id': m['id'],
                                'name': m['name'],
                                'size': m['size'],
                                'file': m['recommended'],
                                'installed': '✅' if installed else '❌'
                            })
                        
                        models_table = ui.table(
                            columns=[
                                {'name': 'name', 'label': 'Model Name', 'field': 'name', 'align': 'left'},
                                {'name': 'size', 'label': 'Size', 'field': 'size'},
                                {'name': 'installed', 'label': 'Installed', 'field': 'installed'},
                            ],
                            rows=model_rows,
                            row_key='id',
                            selection='single'
                        ).classes('w-full')
                        
                        async def download_selected():
                            selected = models_table.selected
                            if not selected:
                                ui.notify('Please select a model first', type='warning')
                                return
                            
                            model = selected[0]
                            repo_id = model['id']
                            filename = model['file']
                            
                            hf_token = app.storage.user.get('hf_token', '')
                            if hf_token:
                                model_manager.set_token(hf_token)
                            
                            # Show progress
                            download_progress_row.set_visibility(True)
                            download_progress_label.set_text(f'⏳ Downloading {model["name"]}...')
                            ui.notify(f'Starting download: {model["name"]}', type='info')
                            
                            try:
                                await model_manager.download_model(repo_id, filename)
                                download_progress_label.set_text(f'✅ {model["name"]} downloaded!')
                                ui.notify(f'Download complete: {model["name"]}', type='positive')
                                
                                for row in models_table.rows:
                                    if row['id'] == repo_id:
                                        row['installed'] = '✅'
                                models_table.update()
                                
                            except Exception as e:
                                download_progress_label.set_text(f'❌ Failed: {str(e)[:50]}')
                                ui.notify(f'Download failed: {str(e)}', type='negative')
                            
                            await asyncio.sleep(3)
                            download_progress_row.set_visibility(False)
                        
                        async def load_selected():
                            selected = models_table.selected
                            if not selected:
                                ui.notify('Please select a model first', type='warning')
                                return
                            
                            model = selected[0]
                            filename = model['file']
                            model_path = MODELS_DIR / filename
                            
                            if not model_path.exists():
                                ui.notify('Model not downloaded yet. Please download first.', type='warning')
                                return
                            
                            ui.notify(f'Loading {model["name"]}... This may take a minute.', type='info')
                            
                            try:
                                # Get settings from storage
                                n_ctx = app.storage.user.get('model_context_size', 4096)
                                n_gpu = -1 if app.storage.user.get('model_use_gpu', True) else 0
                                
                                await llm_service.load_model(str(model_path), n_ctx=n_ctx, n_gpu_layers=n_gpu)
                                ui.notify(f'Model loaded: {model["name"]}', type='positive')
                                loaded_model_label.set_text(f'🧠 {llm_service.model_name}')
                            except Exception as e:
                                ui.notify(f'Failed to load model: {str(e)}', type='negative')
                        
                        with ui.row().classes('gap-2 mt-4'):
                            ui.button('Download Selected', icon='download', on_click=download_selected).props('color=primary')
                            ui.button('Load Selected', icon='play_arrow', on_click=load_selected).props('color=positive')
                        
                        # Local models section
                        ui.separator().classes('my-4')
                        ui.label('Installed Models').classes('text-lg font-bold mb-2')
                        
                        local_models = model_manager.get_local_models()
                        if local_models:
                            for m in local_models:
                                with ui.row().classes('items-center gap-2'):
                                    ui.icon('check_circle', color='green')
                                    ui.label(f"{m['name']} ({m['size']})")
                        else:
                            ui.label('No models installed yet.').classes('text-gray-500')

                    # Model Settings Tab (NEW)
                    with ui.tab_panel(model_settings_tab):
                        ui.label('Model Configuration').classes('text-lg font-bold mb-4')
                        ui.label('These settings apply when loading a model.').classes('text-sm text-gray-500 mb-4')
                        
                        # System Prompt
                        ui.label('System Prompt').classes('font-semibold mt-2')
                        system_prompt_input = ui.textarea(
                            value=app.storage.user.get('system_prompt', 'You are FabriCore, an AI assistant that helps manage computer systems through connected agents. Be concise and helpful. When you need to perform actions, use the available tools.'),
                            placeholder='Enter system prompt...'
                        ).classes('w-full').props('rows=4')
                        
                        def save_system_prompt():
                            app.storage.user['system_prompt'] = system_prompt_input.value
                            ui.notify('System prompt saved!', type='positive')
                        
                        ui.button('Save System Prompt', on_click=save_system_prompt, icon='save').props('flat color=primary').classes('mb-4')
                        
                        ui.separator().classes('my-4')
                        
                        # Context Size
                        ui.label('Context Size (tokens)').classes('font-semibold')
                        context_size_input = ui.select(
                            options=[1024, 2048, 4096, 8192, 16384, 32768],
                            value=app.storage.user.get('model_context_size', 4096)
                        ).classes('w-48')
                        ui.label('Larger = more memory, longer conversations. Requires model reload.').classes('text-xs text-gray-500 mb-4')
                        
                        def save_context_size():
                            app.storage.user['model_context_size'] = context_size_input.value
                            ui.notify(f'Context size set to {context_size_input.value}. Reload model to apply.', type='info')
                        
                        context_size_input.on('update:model-value', lambda e: save_context_size())
                        
                        ui.separator().classes('my-4')
                        
                        # GPU/CPU Toggle
                        ui.label('Hardware Acceleration').classes('font-semibold')
                        
                        def toggle_gpu(e):
                            app.storage.user['model_use_gpu'] = e.value
                            if e.value:
                                ui.notify('GPU enabled. Reload model to apply.', type='info')
                            else:
                                ui.notify('CPU mode enabled. Reload model to apply.', type='info')
                        
                        gpu_switch = ui.switch(
                            'Use GPU (CUDA/Metal)',
                            value=app.storage.user.get('model_use_gpu', True),
                            on_change=toggle_gpu
                        )
                        ui.label('Disable for CPU-only inference. Slower but works without GPU.').classes('text-xs text-gray-500 mb-4')
                        
                        ui.separator().classes('my-4')
                        
                        # Temperature
                        ui.label('Generation Settings').classes('font-semibold')
                        
                        with ui.row().classes('items-center gap-4 mb-2'):
                            ui.label('Temperature:').classes('w-24')
                            temp_slider = ui.slider(
                                min=0.0, max=2.0, step=0.1,
                                value=app.storage.user.get('model_temperature', 0.7)
                            ).classes('w-48')
                            temp_label = ui.label(f"{app.storage.user.get('model_temperature', 0.7):.1f}")
                            temp_slider.on('update:model-value', lambda e: (
                                app.storage.user.update({'model_temperature': e.args}),
                                temp_label.set_text(f"{e.args:.1f}")
                            ))
                        ui.label('Lower = more focused, Higher = more creative').classes('text-xs text-gray-500')
                        
                        with ui.row().classes('items-center gap-4 mb-2 mt-2'):
                            ui.label('Max Tokens:').classes('w-24')
                            max_tokens_input = ui.number(
                                value=app.storage.user.get('model_max_tokens', 1024),
                                min=64, max=8192, step=64
                            ).classes('w-32')
                            max_tokens_input.on('update:model-value', lambda e: app.storage.user.update({'model_max_tokens': int(e.args)}))
                        
                        with ui.row().classes('items-center gap-4 mb-2 mt-2'):
                            ui.label('Top P:').classes('w-24')
                            top_p_slider = ui.slider(
                                min=0.0, max=1.0, step=0.05,
                                value=app.storage.user.get('model_top_p', 0.95)
                            ).classes('w-48')
                            top_p_label = ui.label(f"{app.storage.user.get('model_top_p', 0.95):.2f}")
                            top_p_slider.on('update:model-value', lambda e: (
                                app.storage.user.update({'model_top_p': e.args}),
                                top_p_label.set_text(f"{e.args:.2f}")
                            ))
                        
                        ui.separator().classes('my-4')
                        
                        # Advanced Settings
                        with ui.expansion('Advanced Settings', icon='settings').classes('w-full'):
                            with ui.column().classes('gap-2 p-2'):
                                with ui.row().classes('items-center gap-4'):
                                    ui.label('Repeat Penalty:').classes('w-32')
                                    repeat_penalty = ui.number(
                                        value=app.storage.user.get('model_repeat_penalty', 1.1),
                                        min=1.0, max=2.0, step=0.05, format='%.2f'
                                    ).classes('w-24')
                                    repeat_penalty.on('update:model-value', lambda e: app.storage.user.update({'model_repeat_penalty': e.args}))
                                
                                with ui.row().classes('items-center gap-4'):
                                    ui.label('Top K:').classes('w-32')
                                    top_k_input = ui.number(
                                        value=app.storage.user.get('model_top_k', 40),
                                        min=1, max=100, step=1
                                    ).classes('w-24')
                                    top_k_input.on('update:model-value', lambda e: app.storage.user.update({'model_top_k': int(e.args)}))
                                
                                with ui.row().classes('items-center gap-4'):
                                    ui.label('Threads:').classes('w-32')
                                    threads_input = ui.number(
                                        value=app.storage.user.get('model_threads', 4),
                                        min=1, max=32, step=1
                                    ).classes('w-24')
                                    threads_input.on('update:model-value', lambda e: app.storage.user.update({'model_threads': int(e.args)}))
                                    ui.label('CPU threads for inference').classes('text-xs text-gray-500')
                                
                                with ui.row().classes('items-center gap-4'):
                                    ui.label('Batch Size:').classes('w-32')
                                    batch_input = ui.number(
                                        value=app.storage.user.get('model_batch_size', 512),
                                        min=32, max=2048, step=32
                                    ).classes('w-24')
                                    batch_input.on('update:model-value', lambda e: app.storage.user.update({'model_batch_size': int(e.args)}))

                    # Config Tab
                    with ui.tab_panel(config_tab):
                        ui.label('API Keys & Settings').classes('text-lg font-bold mb-4')
                        
                        hf_token_input = ui.input(
                            'Hugging Face Token',
                            password=True,
                            value=app.storage.user.get('hf_token', '')
                        ).classes('w-full mb-2')
                        
                        def save_hf_token():
                            app.storage.user['hf_token'] = hf_token_input.value
                            model_manager.set_token(hf_token_input.value)
                            ui.notify('Hugging Face token saved!', type='positive')
                        
                        ui.button('Save HF Token', on_click=save_hf_token).props('flat color=primary').classes('mb-4')
                        ui.label('Required for gated models. Get token at huggingface.co/settings/tokens').classes('text-xs text-gray-500 mb-4')
                        
                        ui.separator().classes('my-4')
                        
                        def toggle_dark_mode(e):
                            app.storage.user['dark_mode'] = e.value
                            if e.value:
                                dark.enable()
                            else:
                                dark.disable()
                        
                        ui.switch('Enable Dark Mode', value=app.storage.user.get('dark_mode', False), on_change=toggle_dark_mode)

        # --- UI Helper Functions ---
        
        async def load_chat(session_id: str):
            """Load messages from a session into the UI."""
            nonlocal chat_messages, active_session_id
            active_session_id = session_id
            app.storage.user['current_session_id'] = session_id
            
            # Clear UI and local state
            chat_container.clear()
            chat_messages = []
            
            # Get messages from DB
            messages = data_manager.get_chat_messages(session_id)
            for msg in messages:
                chat_messages.append({"role": msg.role, "content": msg.content})
                with chat_container:
                    if msg.role == 'user':
                        with ui.row().classes('w-full justify-end'):
                            with ui.card().classes('bg-blue-600 text-white p-3 rounded-tl-xl rounded-bl-xl rounded-br-xl'):
                                ui.markdown(msg.content)
                            with ui.avatar(color='gray-300'):
                                ui.icon('person')
                    else:
                        with ui.row().classes('w-full justify-start'):
                            with ui.avatar(color='primary', text_color='white'):
                                ui.icon('smart_toy')
                            with ui.card().classes('bg-gray-100 dark:bg-gray-700 p-3 rounded-tr-xl rounded-br-xl rounded-bl-xl'):
                                ui.markdown(msg.content)
            
            refresh_sessions()

        def start_new_chat():
            """Start a new clean chat session."""
            nonlocal chat_messages, active_session_id
            chat_messages = []
            active_session_id = None
            app.storage.user['current_session_id'] = None
            chat_container.clear()
            with chat_container:
                with ui.row().classes('w-full justify-start'):
                    with ui.avatar(color='primary', text_color='white'):
                        ui.icon('smart_toy')
                    with ui.card().classes('bg-gray-100 dark:bg-gray-700 p-3 rounded-tr-xl rounded-br-xl rounded-bl-xl'):
                        ui.markdown('**New Chat Started.** Ask me anything!')
            refresh_sessions()

        def refresh_sessions():
            """Re-render the session list in the drawer."""
            session_list_container.clear()
            sessions = data_manager.get_chat_sessions()
            with session_list_container:
                for s in sessions:
                    is_active = (s.id == active_session_id)
                    btn_classes = 'w-full text-gray-700 dark:text-gray-300 justify-start px-2'
                    if is_active:
                        btn_classes += ' bg-blue-100 dark:bg-blue-900 border-l-4 border-blue-600'
                    else:
                        btn_classes += ' hover:bg-gray-200 dark:hover:bg-gray-700'
                        
                    with ui.row().classes('w-full items-center no-wrap'):
                        ui.button(s.title[:25] + ('...' if len(s.title) > 25 else ''), 
                                 on_click=lambda s_id=s.id: load_chat(s_id)).props('flat no-caps').classes(btn_classes)

        # --- UI Layout ---
        
        # Left Drawer
        with ui.left_drawer(value=True, fixed=True).classes('bg-gray-50 dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700').props('bordered') as drawer:
            ui.label('CHAT HISTORY').classes('text-gray-500 dark:text-gray-400 text-xs font-bold p-4 tracking-tighter')
            
            session_list_container = ui.column().classes('w-full px-2 gap-1')
            
            ui.separator().classes('my-4')
            ui.button('+ New Chat', icon='add', on_click=start_new_chat).props('flat outline color=primary').classes('w-full mx-2')

        # Header - FIXED DARK MODE STYLING (Forceful)
        with ui.header().classes('!bg-white dark:!bg-gray-900 text-gray-800 dark:text-white border-b border-gray-200 dark:border-gray-700 shadow-sm'):
            ui.button(on_click=lambda: drawer.toggle(), icon='menu').props('flat').classes('text-gray-800 dark:text-white')
            ui.label('FabriCore').classes('text-xl font-bold ml-2 text-gray-800 dark:text-white')
            ui.space()
            
            # Loaded model indicator
            loaded_model_label = ui.label('🧠 No model loaded').classes('text-sm text-gray-500 dark:text-white mr-4')
            if llm_service.model_name:
                loaded_model_label.set_text(f'🧠 {llm_service.model_name}')
            
            ui.button(icon='settings', on_click=open_settings).props('flat round').classes('text-gray-800 dark:text-white').tooltip('Settings')

        # Main Chat Area
        with ui.column().classes('w-full h-screen p-4 items-center justify-between q-pa-md'):
            chat_container = ui.column().classes('w-full max-w-4xl flex-grow overflow-y-auto p-4 gap-4')
            
            with chat_container:
                with ui.row().classes('w-full justify-start'):
                    with ui.avatar(color='primary', text_color='white'):
                        ui.icon('smart_toy')
                    with ui.card().classes('bg-gray-100 dark:bg-gray-700 p-3 rounded-tr-xl rounded-br-xl rounded-bl-xl'):
                        ui.markdown('**Hello!** I am FabriCore. Load a model in Settings → Models, then ask me to help manage your systems.')
            
            # Input Area
            with ui.row().classes('w-full max-w-4xl items-center gap-2 pb-4'):
                text_input = ui.input(placeholder='Message FabriCore...').props('rounded outlined input-class=mx-3').classes('flex-grow')
                
                async def send_message():
                    msg = text_input.value
                    if not msg:
                        return
                    
                    text_input.set_value('')
                    
                    # Add user message to UI and history
                    chat_messages.append({"role": "user", "content": msg})
                    with chat_container:
                        with ui.row().classes('w-full justify-end'):
                            with ui.card().classes('bg-blue-600 text-white p-3 rounded-tl-xl rounded-bl-xl rounded-br-xl'):
                                ui.markdown(msg)
                            with ui.avatar(color='gray-300'):
                                ui.icon('person')
                    
                    # Check if model is loaded
                    if not llm_service.model:
                        with chat_container:
                            with ui.row().classes('w-full justify-start'):
                                with ui.avatar(color='primary', text_color='white'):
                                    ui.icon('smart_toy')
                                with ui.card().classes('bg-gray-100 dark:bg-gray-700 p-3 rounded-tr-xl rounded-br-xl rounded-bl-xl'):
                                    ui.markdown('⚠️ **No model loaded.** Please go to Settings → Models to download and load a model first.')
                        return
                    
                    # Persistence: Create session if needed
                    nonlocal active_session_id
                    if not active_session_id:
                        session_title = msg[:30] + ('...' if len(msg) > 30 else '')
                        session = data_manager.create_chat_session(title=session_title)
                        active_session_id = session.id
                        app.storage.user['current_session_id'] = active_session_id
                        refresh_sessions()
                    
                    # Save user message
                    data_manager.save_chat_message(active_session_id, 'user', msg)
                    
                    # Show thinking indicator
                    with chat_container:
                        thinking_row = ui.row().classes('w-full justify-start')
                        with thinking_row:
                            with ui.avatar(color='primary', text_color='white'):
                                ui.icon('smart_toy')
                            thinking_spinner = ui.spinner('dots', size='2em')
                    
                    try:
                        # Get generation settings from storage
                        system_prompt = app.storage.user.get('system_prompt', 'You are FabriCore, an AI assistant that helps manage computer systems through connected agents. Be concise and helpful. When you need to perform actions, use the available tools.')
                        temperature = app.storage.user.get('model_temperature', 0.7)
                        max_tokens = int(app.storage.user.get('model_max_tokens', 1024))
                        
                        # Build messages with custom system prompt
                        messages = [
                            {"role": "system", "content": system_prompt}
                        ] + chat_messages[-10:]  # Last 10 messages for context
                        
                        # Generate response with tools
                        response = await llm_service.generate(
                            messages=messages,
                            tools=get_tool_definitions(),
                            max_tokens=max_tokens,
                            temperature=temperature
                        )
                        
                        content = response["content"]
                        tool_call = response.get("tool_call")
                        
                        # Handle tool call if present
                        if tool_call:
                            tool_result = await tool_executor.execute(
                                tool_call["tool"],
                                tool_call.get("params", {})
                            )
                            
                            # Add tool result to context and regenerate
                            chat_messages.append({"role": "assistant", "content": content})
                            chat_messages.append({"role": "user", "content": f"Tool result: {tool_result}"})
                            
                            # Save tool interaction to history
                            data_manager.save_chat_message(active_session_id, 'assistant', content)
                            data_manager.save_chat_message(active_session_id, 'user', f"Tool result: {tool_result}")
                            
                            # Generate final response
                            messages = [
                                {"role": "system", "content": "You are FabriCore. Summarize the tool result for the user in a helpful way."}
                            ] + chat_messages[-10:]
                            
                            final_response = await llm_service.generate(
                                messages=messages,
                                max_tokens=max_tokens,
                                temperature=temperature
                            )
                            content = final_response["content"]
                        
                        # Save final assistant message
                        data_manager.save_chat_message(active_session_id, 'assistant', content)
                        
                        # Remove thinking indicator
                        thinking_row.delete()
                        
                        # Add AI response
                        chat_messages.append({"role": "assistant", "content": content})
                        with chat_container:
                            with ui.row().classes('w-full justify-start'):
                                with ui.avatar(color='primary', text_color='white'):
                                    ui.icon('smart_toy')
                                with ui.card().classes('bg-gray-100 dark:bg-gray-700 p-3 rounded-tr-xl rounded-br-xl rounded-bl-xl'):
                                    ui.markdown(content)
                    
                    except Exception as e:
                        if 'thinking_row' in locals():
                            thinking_row.delete()
                        logger.error(f"Generation error: {e}")
                        with chat_container:
                            with ui.row().classes('w-full justify-start'):
                                with ui.avatar(color='red', text_color='white'):
                                    ui.icon('error')
                                with ui.card().classes('bg-red-100 dark:bg-red-900 p-3 rounded-tr-xl rounded-br-xl rounded-bl-xl'):
                                    ui.markdown(f'❌ **Error:** {str(e)}')
                
                text_input.on('keydown.enter', send_message)
                ui.button(icon='send', on_click=send_message).props('round flat color=primary')
            
            # --- Startup Initialization ---
            refresh_sessions()
            if active_session_id:
                await load_chat(active_session_id)
