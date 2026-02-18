# server/app/ui/main.py
from nicegui import ui, app
from app.services.data_manager import DataManager
from app.services.model_manager import get_model_manager, MODELS_DIR
from app.services.llm_service import get_llm_service
from app.services.tools import ToolExecutor, get_tool_definitions
from app.services.scheduler import SchedulerService
from datetime import datetime
from pathlib import Path
import asyncio
import logging
import uuid
import json

logger = logging.getLogger(__name__)

# Singletons
data_manager = DataManager()
scheduler_service = SchedulerService()

def init_ui():

    # Start Scheduler on App Startup
    app.on_startup(scheduler_service.start)

    @ui.page('/', title='FabriCore')
    async def main_page():
        # --- Sanity check for session storage ---
        for key in ['model_kv_cache_type', 'model_context_size', 'model_parallel_slots']:
            val = app.storage.user.get(key)
            if isinstance(val, dict):
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

        # Chat state
        chat_messages = []
        app.storage.user.setdefault('current_session_id', None)
        active_session_id = app.storage.user['current_session_id']

        # Context tracking state
        total_tokens_used = 0
        context_label = None
        context_bar = None

        # =====================================================================
        # SETTINGS DIALOG
        # =====================================================================
        settings_dialog = ui.dialog().props('maximized')

        def open_settings():
            settings_dialog.open()

        with settings_dialog:
            with ui.card().classes('w-full max-w-4xl mx-auto').style('max-height: 90vh; overflow-y: auto'):
                with ui.row().classes('w-full items-center justify-between mb-4'):
                    ui.label('Settings & System Status').classes('text-2xl font-bold')
                    ui.button(icon='close', on_click=settings_dialog.close).props('flat round')

                with ui.tabs().classes('w-full') as settings_tabs:
                    agent_tab = ui.tab('Agents', icon='computer')
                    models_tab = ui.tab('Models', icon='psychology')
                    model_settings_tab = ui.tab('Model Settings', icon='tune')
                    guide_tab = ui.tab('Performance Guide', icon='auto_awesome')
                    config_tab = ui.tab('Configuration', icon='settings')

                with ui.tab_panels(settings_tabs, value=agent_tab).classes('w-full').style('min-height: 400px'):
                    # --- Performance Guide Tab ---
                    with ui.tab_panel(guide_tab):
                        ui.label('Hardware Optimization Guide').classes('text-lg font-bold mb-4')

                        with ui.expansion('🐧 Linux Tuning (AMD/Nvidia)', icon='settings_suggest').classes('w-full border rounded-lg mb-2'):
                            with ui.column().classes('p-4 gap-2'):
                                ui.markdown('**AMD GPU (Vulkan/ROCm)**')
                                ui.markdown('1. **Increase VRAM Limit**: Modern way to allow more allocation for shared memory.')
                                ui.code('sudo nano /etc/modprobe.d/amdgpu.conf\n# Add: options ttm pages_limit=xxxx\nsudo update-initramfs -u')
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

                    # --- Agents Tab (Status + Security Policy) ---
                    with ui.tab_panel(agent_tab):
                        ui.label('Connected Agents & Security').classes('text-lg font-bold mb-2')
                        agents_container = ui.column().classes('w-full gap-4')

                        def refresh_agents_panel():
                            agents_container.clear()
                            from app.models.db import Agent

                            db = data_manager.get_db()
                            try:
                                agents = db.query(Agent).all()
                                if not agents:
                                    with agents_container:
                                        ui.label("No agents registered.").classes('italic text-gray-500')
                                    return

                                for agent in agents:
                                    with agents_container:
                                        with ui.card().classes('w-full p-4 border-l-4').classes(
                                            'border-green-500' if agent.status == 'online' else 'border-gray-400'
                                        ):
                                            with ui.row().classes('w-full items-center justify-between'):
                                                with ui.column().classes('gap-0'):
                                                    ui.label(f"{agent.hostname} ({agent.id[:8]}...)").classes('text-lg font-bold')
                                                    ui.label(f"{agent.platform} | {agent.arch} | {agent.status.upper()}").classes('text-sm text-gray-500')

                                                def open_policy_dialog(a=agent):
                                                    current_policy = data_manager.get_agent_policy(a.id)

                                                    with ui.dialog() as p_dialog, ui.card().classes('w-full max-w-2xl'):
                                                        ui.label(f'Security Policy: {a.hostname}').classes('text-xl font-bold mb-2')

                                                        hitl_switch = ui.switch('Enable Human-in-the-Loop (HITL)', value=current_policy.get('hitl_enabled', False))

                                                        ui.label('Blocked Commands (comma separated)').classes('font-bold mt-2')
                                                        blocked_input = ui.textarea(value=",".join(current_policy.get('blocked_commands', []))).classes('w-full')

                                                        ui.label('Require Approval For (tools, comma separated)').classes('font-bold mt-2')
                                                        approval_input = ui.textarea(value=",".join(current_policy.get('requires_approval_for', []))).classes('w-full')

                                                        async def save_policy():
                                                            new_policy = {
                                                                "hitl_enabled": hitl_switch.value,
                                                                "blocked_commands": [x.strip() for x in blocked_input.value.split(',') if x.strip()],
                                                                "requires_approval_for": [x.strip() for x in approval_input.value.split(',') if x.strip()]
                                                            }
                                                            if data_manager.update_agent_policy(a.id, new_policy):
                                                                from app.core.dependencies import get_agent_manager
                                                                am = get_agent_manager()
                                                                await am.sync_policy(a.id, new_policy)
                                                                ui.notify(f"Policy synced to {a.hostname}", type='positive')
                                                                p_dialog.close()
                                                            else:
                                                                ui.notify("Failed to update policy", type='negative')

                                                        with ui.row().classes('w-full justify-end mt-4'):
                                                            ui.button('Cancel', on_click=p_dialog.close).props('flat')
                                                            ui.button('Save Policy', on_click=save_policy).props('color=primary')

                                                    p_dialog.open()

                                                ui.button('Configure Security', icon='security', on_click=open_policy_dialog).props('outline color=primary')
                            finally:
                                db.close()

                        ui.button('Refresh Agents', icon='refresh', on_click=refresh_agents_panel).props('flat')
                        refresh_agents_panel()

                    # --- Models Tab ---
                    with ui.tab_panel(models_tab):
                        ui.label('GGUF Model Management').classes('text-lg font-bold mb-2')

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

                        search_input.on('keydown.enter', refresh_models)
                        search_btn.on('click', refresh_models)
                        models_table.on('selection', on_model_select)
                        download_btn.on('click', download_selected)
                        refresh_local_models()
                        ui.timer(0.1, lambda: refresh_models() if search_input.value is not None else None, once=True)

                    # --- Model Settings Tab ---
                    with ui.tab_panel(model_settings_tab):
                        ui.label('Model Configuration').classes('text-lg font-bold mb-4')
                        ui.label('These settings apply when loading a model.').classes('text-sm text-gray-500 mb-4')

                        # System Prompt
                        ui.label('System Prompt').classes('font-semibold mt-2')
                        system_prompt_input = ui.textarea(
                            value=app.storage.user.get('system_prompt', 'You are FabriCore, an autonomous AI agent. You execute commands on remote systems. precise, technical, and do not chat unnecessarily. Use the provided tools to fulfill requests.'),
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

                        ui.select(
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
                            ui.notify('GPU enabled. Reload model to apply.' if e.value else 'CPU mode enabled. Reload model to apply.', type='info')

                        ui.switch(
                            'Use GPU (all layers)',
                            value=app.storage.user.get('model_use_gpu', True),
                            on_change=toggle_gpu
                        )
                        ui.label('Forcing all layers to GPU for maximum performance.').classes('text-xs text-gray-500 mb-4')

                        ui.separator().classes('my-4')

                        # Optimization Settings
                        ui.label('Advanced Optimization').classes('font-semibold mb-2')

                        with ui.row().classes('w-full items-center gap-4 mb-2'):
                            with ui.column().classes('gap-1'):
                                ui.label('Parallel Slots (-np)').classes('text-sm font-medium')
                                ui.number(
                                    value=app.storage.user.get('model_parallel_slots', 1),
                                    min=1, max=16, step=1,
                                    on_change=lambda e: app.storage.user.update({'model_parallel_slots': int(e.value) if not isinstance(e.value, dict) else 1})
                                ).classes('w-32')
                                ui.label('1 = Max VRAM for single chat').classes('text-xs text-gray-500')

                            with ui.column().classes('gap-1 flex-grow'):
                                ui.label('GPU Offload').classes('text-sm font-medium')
                                def update_gpu_percent(e):
                                    val = int(e.value)
                                    app.storage.user['model_gpu_offload_percent'] = val
                                    pct_label.set_text(f'{val}%')

                                stored_pct = app.storage.user.get('model_gpu_offload_percent', 100)
                                with ui.row().classes('w-full items-center gap-2'):
                                    ui.slider(min=0, max=100, step=5, value=stored_pct, on_change=update_gpu_percent).classes('flex-grow')
                                    pct_label = ui.label(f'{stored_pct}%').classes('w-12 text-center font-bold')
                                ui.label('Adjust to split model between GPU and CPU (prevents crashes).').classes('text-xs text-gray-500')

                            with ui.column().classes('gap-1'):
                                ui.label('KV Cache Quant').classes('text-sm font-medium')
                                ui.select(
                                    options=['fp16', 'q8_0', 'q4_0'],
                                    value=app.storage.user.get('model_kv_cache_type', 'fp16'),
                                    on_change=lambda e: app.storage.user.update({'model_kv_cache_type': e.value if not isinstance(e.value, dict) else 'fp16'})
                                ).classes('w-32')
                                ui.label('Lower precision = more context').classes('text-xs text-gray-500')

                        ui.separator().classes('my-4')

                        # Generation Settings
                        ui.label('Generation Settings').classes('font-semibold')

                        with ui.row().classes('items-center gap-4 mb-2'):
                            ui.label('Temperature:').classes('w-24')
                            temp_label = ui.label(f"{app.storage.user.get('model_temperature', 0.7):.1f}")
                            def update_temp(e):
                                val = e.value if not isinstance(e.value, dict) else 0.7
                                app.storage.user['model_temperature'] = val
                                temp_label.set_text(f"{val:.1f}")
                            ui.slider(
                                min=0.0, max=2.0, step=0.1,
                                value=app.storage.user.get('model_temperature', 0.7),
                                on_change=update_temp
                            ).classes('w-48')

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

                        with ui.row().classes('items-center gap-4 mb-2 mt-2'):
                            ui.label('Agent Turns:').classes('w-24')
                            turns_input = ui.number(
                                value=app.storage.user.get('agent_max_turns', 15),
                                min=1, max=50, step=1
                            ).classes('w-32')
                            turns_input.on('update:model-value', lambda e: app.storage.user.update({'agent_max_turns': int(e.args)}))
                            ui.label('Max steps per request').classes('text-xs text-gray-500')

                        ui.separator().classes('my-4')

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

                                with ui.row().classes('items-center gap-4'):
                                    ui.label('Batch Size:').classes('w-32')
                                    batch_input = ui.number(
                                        value=app.storage.user.get('model_batch_size', 512),
                                        min=32, max=2048, step=32
                                    ).classes('w-24')
                                    batch_input.on('update:model-value', lambda e: app.storage.user.update({'model_batch_size': int(e.args)}))

                    # --- Config Tab ---
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

                        ui.separator().classes('my-4')

                        def toggle_dark_mode(e):
                            app.storage.user['dark_mode'] = e.value
                            if e.value:
                                dark.enable()
                            else:
                                dark.disable()

                        ui.switch('Enable Dark Mode', value=app.storage.user.get('dark_mode', False), on_change=toggle_dark_mode)

        # =====================================================================
        # SCHEDULER DIALOG
        # =====================================================================
        scheduler_dialog = ui.dialog().props('maximized')

        def open_scheduler():
            refresh_schedules_dialog()
            scheduler_dialog.open()

        with scheduler_dialog:
            with ui.card().classes('w-full max-w-4xl mx-auto').style('max-height: 90vh; overflow-y: auto'):
                with ui.row().classes('w-full items-center justify-between mb-4'):
                    ui.label('⏰ Autonomous Schedules').classes('text-2xl font-bold')
                    ui.button(icon='close', on_click=scheduler_dialog.close).props('flat round')

                # --- Add New Schedule Form ---
                with ui.card().classes('w-full p-4 mb-4 border border-gray-200 dark:border-gray-700'):
                    ui.label("Add New Schedule").classes('text-lg font-bold mb-2')

                    # Build agent dropdown options from DB
                    from app.models.db import Agent
                    _sched_db = data_manager.get_db()
                    try:
                        _agents = _sched_db.query(Agent).all()
                        _agent_options = {a.id: f"{a.hostname} ({a.id[:12]}...)" for a in _agents}
                    finally:
                        _sched_db.close()

                    with ui.grid(columns=2).classes('w-full gap-4'):
                        sched_cron_input = ui.input("Cron Expression", placeholder="*/30 * * * *")
                        sched_agent_input = ui.select(
                            options=_agent_options,
                            label="Agent",
                            with_input=True
                        ).tooltip('Select the target agent')
                        sched_task_input = ui.textarea("Task Instruction", placeholder="Check disk space...").classes('col-span-2')
                        sched_model_input = ui.input("Required Model (Optional)", placeholder="model-name.gguf").classes('col-span-2')

                    with ui.row().classes('w-full items-center gap-4 mt-2'):
                        sched_persistent_switch = ui.switch('Use Persistent Chat', value=False).tooltip(
                            'ON: Reuse the same chat session for every run. OFF: Create a new chat each time.'
                        )

                    async def add_schedule_handler():
                        if not sched_cron_input.value or not sched_task_input.value:
                            ui.notify("Cron and Task are required", type="warning")
                            return

                        from app.models.db import Schedule
                        from app.core.dependencies import get_db as dep_get_db

                        try:
                            db = next(dep_get_db())
                            sch_id = str(uuid.uuid4())
                            cron_val = sched_cron_input.value
                            task_val = sched_task_input.value
                            model_val = sched_model_input.value or None
                            agent_val = sched_agent_input.value or None
                            persistent_val = sched_persistent_switch.value

                            sch = Schedule(
                                id=sch_id,
                                cron_expression=cron_val,
                                task_instruction=task_val,
                                required_model=model_val,
                                agent_id=agent_val,
                                use_persistent_chat=persistent_val
                            )
                            db.add(sch)
                            db.commit()
                            db.close()

                            # Register with scheduler (use local vars, not detached ORM object)
                            scheduler_service.add_job(
                                sch_id, cron_val, task_val,
                                model_val, agent_val
                            )

                            ui.notify("Schedule added successfully", type="positive")
                            sched_cron_input.value = ""
                            sched_task_input.value = ""
                            sched_model_input.value = ""
                            sched_agent_input.value = ""
                            sched_persistent_switch.value = False
                            refresh_schedules_dialog()
                        except Exception as e:
                            ui.notify(f"Error adding schedule: {e}", type="negative")

                    ui.button("Add Schedule", on_click=add_schedule_handler, icon="add").props('color=primary').classes('mt-2')

                ui.separator().classes('my-4')
                ui.label("Active Schedules").classes('text-lg font-bold mb-2')
                schedules_list_container = ui.column().classes('w-full gap-2')

        def refresh_schedules_dialog():
            schedules_list_container.clear()
            from app.models.db import Schedule
            from app.core.dependencies import get_db as dep_get_db

            try:
                db = next(dep_get_db())
                schedules = db.query(Schedule).all()

                with schedules_list_container:
                    if not schedules:
                        ui.label("No active schedules.").classes('text-gray-500 italic')
                    else:
                        for s in schedules:
                            next_run = scheduler_service.get_next_run_time(s.id)
                            with ui.card().classes('w-full p-3 border border-gray-200 dark:border-gray-700'):
                                with ui.row().classes('w-full items-center justify-between'):
                                    with ui.column().classes('gap-0 flex-grow'):
                                        ui.label(f"⏱ {s.cron_expression}").classes('font-bold font-mono')
                                        ui.label(f"{s.task_instruction}").classes('text-sm')
                                        with ui.row().classes('gap-4'):
                                            if s.agent_id:
                                                ui.label(f"Agent: {s.agent_id[:12]}...").classes('text-xs text-gray-500')
                                            if s.required_model:
                                                ui.label(f"Model: {s.required_model}").classes('text-xs text-gray-500')
                                            ui.label(f"{'🔄 Persistent' if s.use_persistent_chat else '🆕 New chat each run'}").classes('text-xs text-blue-500')
                                            if next_run:
                                                ui.label(f"Next: {next_run}").classes('text-xs text-green-500')

                                    with ui.row().classes('gap-1'):
                                        def toggle_active(s_id=s.id, currently_active=s.is_active):
                                            try:
                                                d_db = next(dep_get_db())
                                                sched = d_db.query(Schedule).get(s_id)
                                                if sched:
                                                    sched.is_active = not currently_active
                                                    d_db.commit()
                                                    if not sched.is_active:
                                                        scheduler_service.remove_job(s_id)
                                                    else:
                                                        scheduler_service.add_job(
                                                            s_id, sched.cron_expression,
                                                            sched.task_instruction,
                                                            sched.required_model, sched.agent_id
                                                        )
                                                d_db.close()
                                                refresh_schedules_dialog()
                                            except Exception as ex:
                                                ui.notify(f"Error: {ex}", type="negative")

                                        def delete_schedule(s_id=s.id):
                                            try:
                                                d_db = next(dep_get_db())
                                                d_db.query(Schedule).filter(Schedule.id == s_id).delete()
                                                d_db.commit()
                                                d_db.close()
                                                scheduler_service.remove_job(s_id)
                                                ui.notify("Schedule deleted", type="info")
                                                refresh_schedules_dialog()
                                            except Exception as ex:
                                                ui.notify(f"Error deleting: {ex}", type="negative")

                                        icon = 'pause' if s.is_active else 'play_arrow'
                                        ui.button(icon=icon, on_click=toggle_active).props('flat round').tooltip('Pause/Resume')
                                        ui.button(icon='delete', on_click=delete_schedule).props('flat round color=negative').tooltip('Delete')
                db.close()
            except Exception as e:
                ui.notify(f"Error loading schedules: {e}", type="negative")

        # =====================================================================
        # HITL SECURITY DIALOG (Shield Icon)
        # =====================================================================
        hitl_dialog = ui.dialog().props('maximized')

        def open_hitl_dialog():
            refresh_hitl_dialog()
            hitl_dialog.open()

        with hitl_dialog:
            with ui.card().classes('w-full max-w-4xl mx-auto').style('max-height: 90vh; overflow-y: auto'):
                with ui.row().classes('w-full items-center justify-between mb-4'):
                    ui.label('🛡️ Human-in-the-Loop Security').classes('text-2xl font-bold')
                    ui.button(icon='close', on_click=hitl_dialog.close).props('flat round')

                ui.markdown(
                    '**Configure which tools require human approval before execution, and which commands are blocked entirely.**\n\n'
                    'Each agent can have its own security policy. Changes are synced to the agent immediately.'
                ).classes('text-sm text-gray-600 dark:text-gray-400 mb-4')

                hitl_agents_container = ui.column().classes('w-full gap-4')

        def refresh_hitl_dialog():
            hitl_agents_container.clear()
            from app.models.db import Agent

            db = data_manager.get_db()
            try:
                agents = db.query(Agent).all()
                with hitl_agents_container:
                    if not agents:
                        ui.label("No agents registered. Connect an agent first.").classes('italic text-gray-500')
                        return

                    for agent in agents:
                        current_policy = data_manager.get_agent_policy(agent.id)
                        is_online = agent.status == 'online'

                        with ui.card().classes('w-full p-4 border-l-4').classes(
                            'border-green-500' if is_online else 'border-gray-400'
                        ):
                            with ui.row().classes('w-full items-center justify-between mb-3'):
                                with ui.column().classes('gap-0'):
                                    ui.label(f"{agent.hostname} ({agent.id[:8]}...)").classes('text-lg font-bold')
                                    ui.label(f"{agent.platform} | {agent.status.upper()}").classes('text-sm text-gray-500')

                                # Status badge
                                hitl_enabled = current_policy.get('hitl_enabled', False)
                                if hitl_enabled:
                                    ui.badge('HITL ACTIVE', color='orange').props('outline')
                                else:
                                    ui.badge('HITL OFF', color='gray').props('outline')

                            # HITL Toggle
                            hitl_switch = ui.switch(
                                'Enable Human-in-the-Loop',
                                value=hitl_enabled
                            ).classes('mb-2')

                            # Blocked Commands
                            ui.label('Blocked Commands').classes('font-semibold text-sm mt-2')
                            ui.label('Commands that will be refused outright (comma separated)').classes('text-xs text-gray-500')
                            blocked_input = ui.textarea(
                                value=", ".join(current_policy.get('blocked_commands', [])),
                                placeholder='rm -rf /, shutdown, reboot...'
                            ).classes('w-full').props('rows=2')

                            # Approval-Required Tools
                            ui.label('Require Approval For').classes('font-semibold text-sm mt-2')
                            ui.label('Tool names that need admin approval before execution (comma separated)').classes('text-xs text-gray-500')
                            approval_input = ui.textarea(
                                value=", ".join(current_policy.get('requires_approval_for', [])),
                                placeholder='run_command, write_file...'
                            ).classes('w-full').props('rows=2')

                            async def save_hitl_policy(
                                a_id=agent.id,
                                a_hostname=agent.hostname,
                                switch=hitl_switch,
                                blocked=blocked_input,
                                approval=approval_input
                            ):
                                new_policy = {
                                    "hitl_enabled": switch.value,
                                    "blocked_commands": [x.strip() for x in blocked.value.split(',') if x.strip()],
                                    "requires_approval_for": [x.strip() for x in approval.value.split(',') if x.strip()]
                                }
                                if data_manager.update_agent_policy(a_id, new_policy):
                                    from app.core.dependencies import get_agent_manager
                                    am = get_agent_manager()
                                    await am.sync_policy(a_id, new_policy)
                                    ui.notify(f"✅ Policy synced to {a_hostname}", type='positive')
                                    refresh_hitl_dialog()
                                else:
                                    ui.notify("Failed to update policy", type='negative')

                            ui.button(
                                'Save Policy', icon='save',
                                on_click=save_hitl_policy
                            ).props('color=primary outline').classes('mt-3')

                    # Pending approvals summary
                    from app.models.db import PendingApproval
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

        # =====================================================================
        # HELPER FUNCTIONS
        # =====================================================================

        async def load_chat(session_id: str):
            """Load messages from a session into the UI."""
            nonlocal chat_messages, active_session_id, total_tokens_used, context_label, context_bar
            active_session_id = session_id
            app.storage.user['current_session_id'] = session_id

            # Mark as read
            data_manager.mark_session_read(session_id)

            # Clear UI and local state
            chat_container.clear()
            chat_messages = []
            total_tokens_used = 0

            # Update context counter
            context_label.set_text(f'{total_tokens_used} / {llm_service.context_size}')
            context_bar.set_value(0.0)

            # Get messages from DB
            messages = data_manager.get_chat_messages(session_id)
            for msg in messages:
                chat_messages.append({"role": msg.role, "content": msg.content})

                content_len = len(msg.content)
                estimated_tokens = max(1, content_len // 4)
                total_tokens_used += estimated_tokens

                metadata = msg.metadata_json or {}

                with chat_container:
                    if metadata.get('type') == 'approval_request':
                        # Render inline approval card
                        _render_approval_card(
                            metadata.get('approval_id'),
                            msg.content,
                            metadata.get('status', 'pending')
                        )
                    elif msg.role == 'user':
                        _render_user_message(msg.content)
                    else:
                        _render_assistant_message(msg.content)

            # Update context counter
            context_label.set_text(f'{total_tokens_used} / {llm_service.context_size}')
            context_bar.set_value(total_tokens_used / llm_service.context_size if llm_service.context_size > 0 else 0.0)

            refresh_sessions()

        async def _run_agent_loop(pinned_session_id, pinned_chat_container, pinned_chat_messages, loop_messages):
            """Core ReAct loop that can be started/resumed."""
            nonlocal total_tokens_used, context_label, context_bar, active_session_id

            # Show thinking indicator
            with pinned_chat_container:
                thinking_row = ui.row().classes('w-full justify-start')
                with thinking_row:
                    with ui.avatar(color='primary', text_color='white'):
                        ui.icon('smart_toy')
                    thinking_spinner = ui.spinner('dots', size='2em')

            try:
                temperature = app.storage.user.get('model_temperature', 0.7)
                max_tokens = int(app.storage.user.get('model_max_tokens', 1024))
                max_agent_turns = int(app.storage.user.get('agent_max_turns', 15))

                # Helper: check if user is still viewing the originating chat
                def _user_still_here():
                    return active_session_id == pinned_session_id

                # --- AGENT LOOP ---
                for turn in range(max_agent_turns):
                    response = await llm_service.generate(
                        messages=loop_messages,
                        tools=get_tool_definitions(),
                        max_tokens=max_tokens,
                        temperature=temperature
                    )

                    content = response["content"]
                    tool_call = response.get("tool_call")

                    # Track token usage
                    usage = response.get("usage", {})
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    completion_tokens = usage.get("completion_tokens", 0)
                    total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
                    total_tokens_used += total_tokens

                    try:
                        context_label.set_text(f'{total_tokens_used} / {llm_service.context_size}')
                        context_bar.set_value(total_tokens_used / llm_service.context_size if llm_service.context_size > 0 else 0)
                    except Exception:
                        pass  # UI elements may be gone if user navigated away

                    if not tool_call:
                        # Final answer — save to DB always, render only if user is still here
                        pinned_chat_messages.append({"role": "assistant", "content": content})
                        data_manager.save_chat_message(pinned_session_id, 'assistant', content)

                        if _user_still_here():
                            with pinned_chat_container:
                                _render_assistant_message(content)
                        else:
                            data_manager.mark_session_unread(pinned_session_id)
                            refresh_sessions()
                        break

                    # Tool call
                    tool_msg_content = json.dumps(tool_call)
                    loop_messages.append({"role": "assistant", "content": tool_msg_content})

                    tool_name = tool_call["tool"]
                    tool_args = tool_call.get("params", {})

                    tool_result = await tool_executor.execute(tool_name, tool_args)

                    # Check for HITL pause
                    if isinstance(tool_result, dict) and tool_result.get("status") == "paused":
                        # Generate IDs BEFORE creating ORM object to avoid detached-instance errors
                        approval_id = str(uuid.uuid4())
                        execution_id = str(uuid.uuid4())

                        from app.models.db import PendingApproval as PA
                        approval_entry = PA(
                            id=approval_id,
                            execution_id=execution_id,
                            agent_id=tool_args.get("agent_id", "unknown"),
                            tool_name=tool_name,
                            arguments=tool_args,
                            status="pending",
                            session_id=pinned_session_id
                        )
                        from app.core.dependencies import get_db as dep_get_db
                        db = next(dep_get_db())
                        db.add(approval_entry)
                        db.commit()
                        db.close()

                        # Use local approval_id (not approval_entry.id) to avoid detached-instance error
                        approval_content = f"🛡️ **Approval Required**\n\nTool: `{tool_name}`\nArgs: `{json.dumps(tool_args)}`"
                        data_manager.save_chat_message(
                            pinned_session_id, 'assistant', approval_content,
                            metadata={"type": "approval_request", "approval_id": approval_id, "status": "pending"}
                        )

                        if _user_still_here():
                            with pinned_chat_container:
                                _render_approval_card(approval_id, approval_content, 'pending')
                        else:
                            data_manager.mark_session_unread(pinned_session_id)
                            refresh_sessions()
                        break

                    obs_content = f"Observation: {json.dumps(tool_result)}"
                    loop_messages.append({"role": "system", "content": obs_content})

                else:
                    # Loop exhausted
                    if _user_still_here():
                        with pinned_chat_container:
                            ui.label("⚠️ Agent stopped after max turns.").classes('text-red-500 text-xs')

                # Remove thinking indicator safely
                try:
                    if 'thinking_row' in locals() and thinking_row:
                        thinking_row.delete()
                except (ValueError, RuntimeError, Exception):
                    pass  # Already removed from parent or parent slot deleted

            except Exception as e:
                try:
                    if 'thinking_row' in locals() and thinking_row:
                        thinking_row.delete()
                except (ValueError, RuntimeError, Exception):
                    pass  # Already removed from parent or parent slot deleted
                logger.error(f"Generation error: {e}")
                if _user_still_here():
                    with pinned_chat_container:
                        with ui.row().classes('w-full justify-start'):
                            with ui.avatar(color='red', text_color='white'):
                                ui.icon('error')
                            with ui.card().classes('bg-red-100 dark:bg-red-900 p-3 rounded-tr-xl rounded-br-xl rounded-bl-xl'):
                                ui.markdown(f'❌ **Error:** {str(e)}')

        def _render_user_message(content: str):
            """Render a user message bubble."""
            with ui.row().classes('w-full justify-end'):
                with ui.card().classes('bg-blue-600 text-white p-3 rounded-tl-xl rounded-bl-xl rounded-br-xl'):
                    ui.markdown(content)
                with ui.avatar(color='gray-300'):
                    ui.icon('person')

        def _render_assistant_message(content: str):
            """Render an assistant message bubble."""
            with ui.row().classes('w-full justify-start'):
                with ui.avatar(color='primary', text_color='white'):
                    ui.icon('smart_toy')
                with ui.card().classes('bg-gray-100 dark:bg-gray-700 p-3 rounded-tr-xl rounded-br-xl rounded-bl-xl'):
                    ui.markdown(content)

        def _render_approval_card(approval_id: str, content: str, status: str = 'pending'):
            """Render an inline HITL approval card in the chat."""
            with ui.row().classes('w-full justify-start'):
                with ui.avatar(color='orange', text_color='white'):
                    ui.icon('shield')
                with ui.card().classes('bg-amber-50 dark:bg-amber-900/30 border border-amber-300 dark:border-amber-700 p-4 rounded-tr-xl rounded-br-xl rounded-bl-xl w-full max-w-2xl'):
                    ui.markdown(content)

                    if status == 'pending' and approval_id:
                        with ui.row().classes('gap-2 mt-3'):
                            async def handle_approve(a_id=approval_id):
                                from app.models.db import PendingApproval
                                from app.core.dependencies import get_db as dep_get_db
                                try:
                                    db = next(dep_get_db())
                                    item = db.query(PendingApproval).get(a_id)
                                    if item:
                                        # Pin session ID locally for resumption
                                        pinned_session_id = item.session_id
                                        pinned_chat_container = chat_container # Reference to latest container
                                        
                                        item.status = "approved"
                                        db.commit()
                                        ui.notify(f"Approved {item.tool_name}. Executing...", type='positive')

                                        # Execute the tool
                                        try:
                                            res = await tool_executor.execute(
                                                item.tool_name, item.arguments, approved_by="admin"
                                            )
                                            # Save result to chat
                                            result_msg = f"✅ **Approved & Executed**: `{item.tool_name}`\n\nResult: ```\n{json.dumps(res, indent=2)}\n```"
                                            data_manager.save_chat_message(
                                                pinned_session_id, 'assistant', result_msg,
                                                metadata={"type": "approval_result", "approval_id": a_id, "raw_result": res}
                                            )
                                            
                                            # Update local chat_messages if user is still on this session
                                            if active_session_id == pinned_session_id:
                                                chat_messages.append({"role": "assistant", "content": result_msg})
                                                with chat_container:
                                                    _render_assistant_message(result_msg)
                                            
                                            # RESUME AGENT LOOP
                                            # 1. Re-construct message history from DB for this session
                                            history = data_manager.get_chat_messages(pinned_session_id)
                                            loop_messages = []
                                            
                                            # Add system prompt
                                            system_prompt = app.storage.user.get('system_prompt', 
                                                'You are FabriCore, an AI assistant that helps manage computer systems through connected agents. Be concise and helpful. When you need to perform actions, use the available tools.')
                                            loop_messages.append({"role": "system", "content": system_prompt})
                                            
                                            # Build turns for LLM
                                            for msg in history[-12:]: # Last few messages
                                                role = msg.role
                                                content = msg.content
                                                metadata = getattr(msg, 'metadata_json', {}) or {}
                                                
                                                # Re-format ReAct turns
                                                if metadata.get('type') == 'approval_result':
                                                    role = 'system'
                                                    raw_res = metadata.get('raw_result')
                                                    content = f"Observation: {json.dumps(raw_res if raw_res is not None else res)}"
                                                elif role == 'assistant' and '{"tool":' in content:
                                                    # It's a tool call assistant message
                                                    pass # Keep as is
                                                
                                                loop_messages.append({"role": role, "content": content})

                                            # Start loop
                                            current_msg_list = chat_messages if active_session_id == pinned_session_id else []
                                            
                                            await _run_agent_loop(
                                                pinned_session_id, 
                                                pinned_chat_container, 
                                                current_msg_list, 
                                                loop_messages
                                            )

                                        except Exception as e:
                                            ui.notify(f"Execution Failed: {e}", type='negative')
                                    db.close()
                                except Exception as ex:
                                    ui.notify(f"Error: {ex}", type='negative')

                            async def handle_deny(a_id=approval_id):
                                from app.models.db import PendingApproval
                                from app.core.dependencies import get_db as dep_get_db
                                try:
                                    db = next(dep_get_db())
                                    item = db.query(PendingApproval).get(a_id)
                                    if item:
                                        item.status = "rejected"
                                        db.commit()

                                        deny_msg = f"❌ **Denied**: `{item.tool_name}` — Action was rejected by admin."
                                        data_manager.save_chat_message(
                                            item.session_id, 'assistant', deny_msg,
                                            metadata={"type": "approval_result", "approval_id": a_id}
                                        )
                                        if active_session_id == item.session_id:
                                            chat_messages.append({"role": "assistant", "content": deny_msg})
                                            with chat_container:
                                                _render_assistant_message(deny_msg)
                                    db.close()
                                    ui.notify("Request denied", type='info')
                                except Exception as ex:
                                    ui.notify(f"Error: {ex}", type='negative')

                            ui.button("✅ Approve", on_click=handle_approve).props('color=positive outline')
                            ui.button("❌ Deny", on_click=handle_deny).props('color=negative outline')
                    elif status == 'approved':
                        ui.label('✅ Approved').classes('text-green-600 text-sm font-bold mt-2')
                    elif status == 'rejected':
                        ui.label('❌ Denied').classes('text-red-600 text-sm font-bold mt-2')

        def start_new_chat():
            """Start a new clean chat session."""
            nonlocal chat_messages, active_session_id, total_tokens_used, context_label, context_bar
            chat_messages = []
            active_session_id = None
            app.storage.user['current_session_id'] = None
            total_tokens_used = 0

            context_label.set_text(f'{total_tokens_used} / {llm_service.context_size}')
            context_bar.set_value(0.0)
            chat_container.clear()
            with chat_container:
                _render_assistant_message('**New Chat Started.** Ask me anything!')
            refresh_sessions()

        def refresh_sessions():
            """Re-render the session list in the drawer with delete buttons and unread indicators."""
            session_list_container.clear()
            sessions = data_manager.get_chat_sessions()
            with session_list_container:
                for s in sessions:
                    is_active = (s.id == active_session_id)
                    has_unread = getattr(s, 'has_unread', False)

                    # Session row with hover-reveal delete button
                    with ui.element('div').classes(
                        'w-full flex items-center group rounded-lg px-1 transition-colors '
                        + ('bg-blue-100 dark:bg-blue-900 border-l-4 border-blue-600 ' if is_active
                           else 'hover:bg-gray-200 dark:hover:bg-gray-700 ')
                    ):
                        # Unread indicator
                        if has_unread and not is_active:
                            ui.icon('circle', size='xs').classes('text-blue-500 mr-1').style('font-size: 8px;')

                        # Session title button
                        ui.button(
                            s.title[:25] + ('...' if len(s.title) > 25 else ''),
                            on_click=lambda s_id=s.id: load_chat(s_id)
                        ).props('flat no-caps').classes(
                            'flex-grow text-gray-700 dark:text-gray-300 justify-start px-2 text-left'
                        ).style('text-transform: none;')

                        # Delete button - only visible on hover (CSS group-hover)
                        async def delete_session(s_id=s.id):
                            nonlocal active_session_id
                            data_manager.delete_chat_session(s_id)
                            if s_id == active_session_id:
                                start_new_chat()
                            else:
                                refresh_sessions()

                        ui.button(
                            icon='delete', on_click=delete_session
                        ).props('flat round size=sm').classes(
                            'opacity-0 group-hover:opacity-100 transition-opacity text-gray-400 hover:text-red-500'
                        ).tooltip('Delete chat')

        # =====================================================================
        # UI LAYOUT
        # =====================================================================

        # --- Left Drawer (Chat History) ---
        with ui.left_drawer(value=True, fixed=True).classes(
            'bg-gray-50 dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700'
        ).props('bordered') as drawer:
            ui.label('CHAT HISTORY').classes('text-gray-500 dark:text-gray-400 text-xs font-bold p-4 tracking-tighter')
            session_list_container = ui.column().classes('w-full px-2 gap-1')
            ui.separator().classes('my-4')
            ui.button('+ New Chat', icon='add', on_click=start_new_chat).props('flat outline color=primary').classes('w-full mx-2')

        # --- Header ---
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

            # HITL Security button (shield icon)
            ui.button(icon='shield', on_click=open_hitl_dialog).props('flat round').classes('text-gray-800 dark:text-white').tooltip('HITL Security')

            # Scheduler button (clock icon)
            ui.button(icon='schedule', on_click=open_scheduler).props('flat round').classes('text-gray-800 dark:text-white').tooltip('Schedules')

            # Settings button
            ui.button(icon='settings', on_click=open_settings).props('flat round').classes('text-gray-800 dark:text-white').tooltip('Settings')

        # =====================================================================
        # MAIN CHAT AREA (Full viewport, no tabs)
        # =====================================================================
        with ui.column().classes('w-full h-screen items-center p-0'):

            # Context Usage Meter
            with ui.row().classes('w-full max-w-4xl items-center gap-2 px-4 py-1 bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700'):
                with ui.column().classes('flex-grow gap-0'):
                    with ui.row().classes('w-full justify-between items-center'):
                        ui.label('Context Usage').classes('text-xs text-gray-500 dark:text-gray-400')
                        context_label = ui.label('0 / 0').classes('text-xs font-mono text-gray-500 dark:text-gray-400')
                    context_bar = ui.linear_progress(value=0.0, show_value=False).props('color=primary size=4px rounded')

            # Chat Messages Container
            chat_container = ui.column().classes('w-full max-w-4xl flex-grow overflow-y-auto p-4 gap-4')

            with chat_container:
                _render_assistant_message(
                    '**Hello!** I am FabriCore. Load a model in Settings → Models, then ask me to help manage your systems.'
                )

            # Status Bar
            with ui.row().classes('w-full max-w-4xl items-center gap-2 px-4 py-1 bg-gray-50 dark:bg-gray-800'):
                status_spinner = ui.spinner('dots', size='sm').classes('text-primary')
                status_spinner.set_visibility(False)
                status_label = ui.label('').classes('text-xs text-primary font-medium italic animate-pulse')

            # Input Area
            with ui.row().classes('w-full max-w-4xl items-center gap-2 pb-4 px-4'):
                text_input = ui.input(placeholder='Message FabriCore...').props('rounded outlined input-class=mx-3').classes('flex-grow')
                send_btn = ui.button(icon='send', on_click=lambda: send_message()).props('round flat color=primary')

            # =====================================================================
            # SEND MESSAGE HANDLER
            # =====================================================================
            async def send_message():
                nonlocal chat_messages, active_session_id, total_tokens_used, context_label, context_bar
                msg = text_input.value
                if not msg:
                    return

                text_input.set_value('')

                # Add user message to UI and history
                chat_messages.append({"role": "user", "content": msg})
                with chat_container:
                    _render_user_message(msg)

                # Check if model is loaded
                if not llm_service.model:
                    with chat_container:
                        _render_assistant_message('⚠️ **No model loaded.** Please go to Settings → Models to download and load a model first.')
                    return

                # Session: Create if needed
                if not active_session_id:
                    session_title = msg[:30] + ('...' if len(msg) > 30 else '')
                    session = data_manager.create_chat_session(title=session_title)
                    active_session_id = session.id
                    app.storage.user['current_session_id'] = active_session_id
                    refresh_sessions()

                # === PIN ALL SHARED STATE ===
                # Prevents cross-chat contamination when user navigates away during async processing
                pinned_session_id = active_session_id
                pinned_chat_container = chat_container
                pinned_chat_messages = chat_messages  # reference to current list

                # Save user message
                data_manager.save_chat_message(pinned_session_id, 'user', msg)

                # Prepare initial history for agent
                system_prompt = app.storage.user.get('system_prompt',
                    'You are FabriCore, an AI assistant that helps manage computer systems through connected agents. Be concise and helpful. When you need to perform actions, use the available tools.')
                
                messages = [
                    {"role": "system", "content": system_prompt}
                ] + list(pinned_chat_messages[-10:])  # snapshot copy

                # START AGENT LOOP
                await _run_agent_loop(
                    pinned_session_id,
                    pinned_chat_container,
                    pinned_chat_messages,
                    messages.copy()
                )

            text_input.on('keydown.enter', send_message)

            # --- Startup Initialization ---
            refresh_sessions()
            if active_session_id:
                await load_chat(active_session_id)