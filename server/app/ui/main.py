# server/app/ui/main.py
from nicegui import ui, app
from app.services.data_manager import DataManager
from app.services.model_manager import get_model_manager, MODELS_DIR
from app.services.llm_service import get_llm_service
from app.services.tools import ToolExecutor, get_tool_definitions
from datetime import datetime
from pathlib import Path
import asyncio
import logging
import uuid
import json

logger = logging.getLogger(__name__)

# Singletons
data_manager = DataManager()


def init_ui():
    @ui.page('/', title='FabriCore')
    async def main_page():
        # --- Sanity check for session storage (prevents crashes from corrupt state) ---
        for key in ['model_kv_cache_type', 'model_context_size', 'model_parallel_slots']:
            val = app.storage.user.get(key)
            if isinstance(val, dict):
                # If we accidentally stored a Quasar event dict, reset to default
                defaults = {'model_kv_cache_type': 'fp16', 'model_context_size': 4096, 'model_parallel_slots': 1}
                app.storage.user[key] = defaults.get(key)
                logger.warning(f"Sanitized corrupted UI state for {key}: reset to {app.storage.user[key]}")

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
        
        # Communication manager and tool executor
        tool_executor = ToolExecutor(data_manager)
        
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
                    guide_tab = ui.tab('Performance Guide', icon='auto_awesome')
                    config_tab = ui.tab('Configuration', icon='settings')
                
                with ui.tab_panels(tabs, value=agent_tab).classes('w-full').style('min-height: 400px'):
                    # Performance Guide Tab (NEW)
                    with ui.tab_panel(guide_tab):
                        ui.label('Hardware Optimization Guide').classes('text-lg font-bold mb-4')
                        
                        with ui.expansion('🐧 Linux Tuning (AMD/Nvidia)', icon='settings_suggest').classes('w-full border rounded-lg mb-2'):
                            with ui.column().classes('p-4 gap-2'):
                                ui.markdown('**AMD GPU (Vulkan/ROCm)**')
                                ui.markdown('1. **Increase GTT Size**: Allows more VRAM allocation for integrated/shared memory.')
                                ui.code('sudo nano /etc/modprobe.d/amdgpu.conf\n# Add: options amdgpu gttsize=51200\nsudo update-initramfs -u')
                                ui.markdown('2. **Enable GPL**: Helps with shader compilation and performance.')
                                ui.code('RADV_PERFTEST=gpl')
                                ui.separator().classes('my-2')
                                ui.markdown('**Nvidia GPU**')
                                ui.markdown('1. **Persistence Mode**: Keeps the driver loaded and prevents startup lag.')
                                ui.code('sudo nvidia-smi -pm 1')
                        
                        with ui.expansion('🪟 Windows Tuning', icon='desktop_windows').classes('w-full border rounded-lg mb-2'):
                            with ui.column().classes('p-4 gap-2'):
                                ui.markdown('1. **HAGS**: Enable "Hardware-accelerated GPU scheduling" in Graphics Settings.')
                                ui.markdown('2. **Pagefile**: Ensure you have a large pagefile (16GB+) on an SSD if using Large Context.')
                                ui.markdown('3. **Graphics Performance**: Set Python/Docker to "High Performance" in Windows Graphics settings.')

                        with ui.expansion('🍎 macOS Tuning (Apple Silicon)', icon='laptop_mac').classes('w-full border rounded-lg mb-2'):
                            with ui.column().classes('p-4 gap-2'):
                                ui.markdown('1. **Unified Memory**: Apple Silicon automatically shares memory. Close other apps to give LLM more RAM.')
                                ui.markdown('2. **Metal**: FabriCore uses Vulkan/Metal backends. Ensure you are on the latest macOS version for optimal driver performance.')

                        ui.label('Pro Tip: Use Flash Attention and Q8/Q4 KV Cache in "Model Settings" to save up to 40% VRAM!').classes('text-sm italic text-primary mt-4')

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
                        ui.label('GGUF Model Management').classes('text-lg font-bold mb-2')
                        
                        # 1. UI Structure components (references needed by functions)
                        with ui.row().classes('w-full items-center gap-2 mb-4'):
                            search_input = ui.input(placeholder='Search HF...').classes('flex-grow')
                            search_btn = ui.button(icon='search').props('flat round').tooltip('Search HuggingFace')
                            ui.separator().props('vertical')
                            filter_input = ui.input(placeholder='Filter results...').classes('w-48')
                        
                        with ui.row().classes('w-full items-center gap-2 mb-4') as download_progress_row:
                            download_progress_row.set_visibility(False)
                            ui.spinner('dots', size='lg')
                            download_progress_label = ui.label('Downloading...').classes('text-sm')
                        
                        models_table = ui.table(
                            columns=[
                                {'name': 'name', 'label': 'Name', 'field': 'name', 'align': 'left', 'sortable': True},
                                {'name': 'downloads', 'label': 'Downloads', 'field': 'downloads', 'sortable': True},
                                {'name': 'likes', 'label': 'Likes', 'field': 'likes', 'sortable': True},
                                {'name': 'id', 'label': 'ID', 'field': 'id', 'align': 'left'},
                            ],
                            rows=[],
                            row_key='id',
                            selection='single'
                        ).classes('w-full').bind_filter_from(filter_input, 'value')
                        
                        file_select_row = ui.row().classes('w-full items-center gap-2 mt-2')
                        file_select_row.set_visibility(False)
                        file_selector = ui.select(options=[], label='Select GGUF File').classes('flex-grow')
                        download_btn = ui.button('Download Selected File', icon='download').props('color=primary')
                        download_btn.bind_visibility_from(file_select_row, 'visible')

                        ui.separator().classes('my-6')
                        ui.label('Installed Models').classes('text-lg font-bold mb-2')
                        local_m_container = ui.column().classes('w-full gap-2')

                        # 2. Helper Functions
                        async def refresh_models():
                            query = search_input.value
                            ui.notify(f'Searching for "{query}"...', type='info')
                            results = await model_manager.search_hf_models(query)
                            models_table.rows = results
                            models_table.update()
                            file_select_row.set_visibility(False)

                        async def on_model_select(e):
                            selected = models_table.selected
                            if not selected:
                                file_select_row.set_visibility(False)
                                return
                            
                            repo_id = selected[0]['id']
                            ui.notify(f'Fetching files for {repo_id}...', type='info', duration=1)
                            files = await model_manager.get_model_files(repo_id)
                            if files:
                                file_selector.options = files
                                # Try to find Q4_K_M quantization as suggested (Goldilocks standard)
                                target = next((f for f in files if "q4_k_m" in f.lower()), files[0])
                                file_selector.value = target
                                file_select_row.set_visibility(True)
                            else:
                                ui.notify('No GGUF files found in this repo', type='warning')
                                file_select_row.set_visibility(False)

                        async def download_selected():
                            selected = models_table.selected
                            if not selected or not file_selector.value:
                                ui.notify('Please select a model and file first', type='warning')
                                return
                            
                            repo_id = selected[0]['id']
                            filename = file_selector.value
                            
                            hf_token = app.storage.user.get('hf_token', '')
                            if hf_token:
                                model_manager.set_token(hf_token)
                            
                            download_progress_row.set_visibility(True)
                            download_progress_label.set_text(f'⏳ Downloading {filename} from {repo_id}...')
                            
                            try:
                                await model_manager.download_model(repo_id, filename)
                                ui.notify(f'Download complete: {filename}', type='positive')
                                refresh_local_models()
                            except Exception as e:
                                ui.notify(f'Download failed: {str(e)}', type='negative')
                            
                            download_progress_row.set_visibility(False)

                        def refresh_local_models():
                            local_m_container.clear()
                            local_models = model_manager.get_local_models()
                            if not local_models:
                                with local_m_container:
                                    ui.label('No models installed yet.').classes('text-gray-500 italic')
                                return
                            
                            for m in local_models:
                                with local_m_container:
                                    with ui.row().classes('w-full items-center justify-between p-2 border border-gray-100 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors'):
                                        with ui.row().classes('items-center gap-3'):
                                            ui.icon('description', color='primary')
                                            with ui.column().classes('gap-0'):
                                                ui.label(m['name']).classes('font-medium')
                                                ui.label(f"{m['size']}").classes('text-xs text-gray-500')
                                        
                                        with ui.row().classes('gap-2'):
                                            async def load_m(name=m['name']):
                                                ui.notify(f'Loading {name}...', type='info')
                                                try:
                                                    n_ctx = app.storage.user.get('model_context_size', 4096)
                                                    n_parallel = app.storage.user.get('model_parallel_slots', 1)
                                                    kv_cache_type = app.storage.user.get('model_kv_cache_type', 'fp16')
                                                    gpu_percent = app.storage.user.get('model_gpu_offload_percent', 100)
                                                    
                                                    await model_manager.load_model(
                                                        name, 
                                                        n_ctx=n_ctx,
                                                        n_parallel=n_parallel,
                                                        kv_cache_type=kv_cache_type,
                                                        gpu_offload_percent=gpu_percent
                                                    )
                                                    ui.notify(f'Model loaded: {name}', type='positive')
                                                    loaded_model_label.set_text(f'🧠 {llm_service.model_name or "No model loaded"}')
                                                    release_btn.set_visibility(True)
                                                except Exception as e:
                                                    ui.notify(f'Load failed: {str(e)}', type='negative')

                                            def delete_m(filename=m['name']):
                                                if model_manager.delete_model(filename):
                                                    ui.notify(f'Deleted {filename}', type='positive')
                                                    refresh_local_models()
                                                else:
                                                    ui.notify(f'Failed to delete {filename}', type='negative')

                                            ui.button(icon='play_arrow', on_click=load_m).props('flat round color=positive').tooltip('Load Model')
                                            ui.button(icon='delete', on_click=delete_m).props('flat round color=negative').tooltip('Delete Model')

                        # 3. Attach Callbacks
                        search_input.on('keydown.enter', refresh_models)
                        search_btn.on('click', refresh_models)
                        models_table.on('selection', on_model_select)
                        download_btn.on('click', download_selected)

                        # 4. Initialize
                        refresh_local_models()
                        # Safe timer to prevent "Parent slot deleted" crash
                        ui.timer(0.1, lambda: refresh_models() if search_input.value is not None else None, once=True)

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
                        def save_context_size(e):
                            val = e.value if not isinstance(e.value, dict) else 4096
                            app.storage.user['model_context_size'] = val
                            ui.notify(f'Context size set to {val}. Reload model to apply.', type='info')

                        context_size_input = ui.select(
                            options=[1024, 2048, 4096, 8192, 16384, 32768, 65536, 131072, 262144],
                            value=app.storage.user.get('model_context_size', 4096),
                            on_change=save_context_size
                        ).classes('w-48')
                        ui.label('Larger = more memory, longer conversations. Requires model reload.').classes('text-xs text-gray-500 mb-4')
                        
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
                            'Use GPU (all layers)',
                            value=app.storage.user.get('model_use_gpu', True),
                            on_change=toggle_gpu
                        )
                        ui.label('Forcing all layers to GPU for maximum performance.').classes('text-xs text-gray-500 mb-4')
                        
                        ui.separator().classes('my-4')
                        
                        # --- NEW: Inference Optimization Settings ---
                        ui.label('Advanced Optimization').classes('font-semibold mb-2')
                        
                        with ui.row().classes('w-full items-center gap-4 mb-2'):
                            # Parallel Slots
                            with ui.column().classes('gap-1'):
                                ui.label('Parallel Slots (-np)').classes('text-sm font-medium')
                                parallel_slots = ui.number(
                                    value=app.storage.user.get('model_parallel_slots', 1),
                                    min=1, max=16, step=1,
                                    on_change=lambda e: app.storage.user.update({'model_parallel_slots': int(e.value) if not isinstance(e.value, dict) else 1})
                                ).classes('w-32')
                                ui.label('1 = Max VRAM for single chat').classes('text-xs text-gray-500')
                            
                            # GPU Offload Slider
                            with ui.column().classes('gap-1 flex-grow'):
                                ui.label('GPU Offload').classes('text-sm font-medium')
                                
                                def update_gpu_percent(e):
                                    val = int(e.value)
                                    app.storage.user['model_gpu_offload_percent'] = val
                                    pct_label.set_text(f'{val}%')

                                # Get initial value (Default 100%)
                                stored_pct = app.storage.user.get('model_gpu_offload_percent', 100)

                                with ui.row().classes('w-full items-center gap-2'):
                                    ui.slider(min=0, max=100, step=5, value=stored_pct, on_change=update_gpu_percent).classes('flex-grow')
                                    pct_label = ui.label(f'{stored_pct}%').classes('w-12 text-center font-bold')
                                
                                ui.label('Adjust to split model between GPU and CPU (prevents crashes).').classes('text-xs text-gray-500')
                            
                            # KV Cache compression
                            with ui.column().classes('gap-1'):
                                ui.label('KV Cache Quant').classes('text-sm font-medium')
                                kv_cache_select = ui.select(
                                    options=['fp16', 'q8_0', 'q4_0'],
                                    value=app.storage.user.get('model_kv_cache_type', 'fp16'),
                                    on_change=lambda e: app.storage.user.update({'model_kv_cache_type': e.value if not isinstance(e.value, dict) else 'fp16'})
                                ).classes('w-32')
                                ui.label('Lower precision = more context').classes('text-xs text-gray-500')
                        
                        ui.separator().classes('my-4')
                        
                        # Temperature
                        ui.label('Generation Settings').classes('font-semibold')
                        
                        with ui.row().classes('items-center gap-4 mb-2'):
                            ui.label('Temperature:').classes('w-24')
                            temp_label = ui.label(f"{app.storage.user.get('model_temperature', 0.7):.1f}")
                            
                            def update_temp(e):
                                val = e.value if not isinstance(e.value, dict) else 0.7
                                app.storage.user['model_temperature'] = val
                                temp_label.set_text(f"{val:.1f}")
                            
                            temp_slider = ui.slider(
                                min=0.0, max=2.0, step=0.1,
                                value=app.storage.user.get('model_temperature', 0.7),
                                on_change=update_temp
                            ).classes('w-48')
                        ui.label('Lower = more focused, Higher = more creative').classes('text-xs text-gray-500')
                        
                        with ui.row().classes('items-center gap-4 mb-2 mt-2'):
                            ui.label('Max Tokens:').classes('w-24')
                            max_tokens_input = ui.number(
                                value=app.storage.user.get('model_max_tokens', 1024),
                                min=64, max=16384, step=64
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
            with ui.row().classes('items-center mr-4'):
                loaded_model_label = ui.label('🧠 No model loaded').classes('text-sm text-gray-500 dark:text-white mr-2')
                if llm_service.model_name:
                    loaded_model_label.set_text(f'🧠 {llm_service.model_name}')
                
                async def release_m():
                    if await model_manager.release_model():
                        ui.notify('Model released. GPU memory freed.', type='positive')
                        loaded_model_label.set_text('🧠 No model loaded')
                        release_btn.set_visibility(False)
                    else:
                        ui.notify('Failed to release model', type='negative')
                
                release_btn = ui.button(icon='power_settings_new', on_click=release_m).props('flat round color=negative sm').tooltip('Unload model and free GPU VRAM')
                release_btn.set_visibility(True if llm_service.model_name else False)
                
                # We need to make sure the release button disappears when we load a new model
                # This is handled in the load_m function by refreshing the header or label state
            
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
                            # UI Feedback for tool call
                            tool_name = tool_call["tool"]
                            with chat_container:
                                ui.markdown(f"🔧 *Calling tool: {tool_name}...*").classes('text-xs text-gray-400 italic')
                            
                            # Execute tool
                            tool_result = await tool_executor.execute(
                                tool_name,
                                tool_call.get("params", {})
                            )
                            
                            # Add tool result to context and regenerate
                            # We keep it simple: tell the LLM what happened
                            chat_messages.append({"role": "assistant", "content": content})
                            chat_messages.append({"role": "user", "content": f"Tool result for {tool_name}: {json.dumps(tool_result)}"})
                            
                            # Save tool interaction to history
                            data_manager.save_chat_message(active_session_id, 'assistant', content)
                            data_manager.save_chat_message(active_session_id, 'user', f"Tool result for {tool_name}: {json.dumps(tool_result)}")
                            
                            # Update system prompt or message sequence to emphasize summary
                            messages = [
                                {"role": "system", "content": "You are FabriCore. A tool has been executed. Now explain the result to the user naturally."}
                            ] + chat_messages[-10:]
                            
                            final_response = await llm_service.generate(
                                messages=messages,
                                max_tokens=max_tokens,
                                temperature=temperature
                            )
                            content = final_response["content"]
                        
                        # Remove thinking indicator (ensure it happens before final display)
                        if 'thinking_row' in locals():
                            thinking_row.delete()
                        
                        # Save final assistant message
                        data_manager.save_chat_message(active_session_id, 'assistant', content)
                        
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
