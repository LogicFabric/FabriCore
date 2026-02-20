from nicegui import ui, app
import logging
from app.services.model_manager import get_model_manager
from app.services.llm_service import get_llm_service
from app.core.config import settings

logger = logging.getLogger(__name__)

class SettingsDialog:
    def __init__(self, data_manager, loaded_model_label, release_btn):
        self.data_manager = data_manager
        self.model_manager = get_model_manager()
        self.llm_service = get_llm_service()
        self.loaded_model_label = loaded_model_label
        self.release_btn = release_btn
        self.dialog = ui.dialog().props('maximized')
        self._build_dialog()

    def open(self):
        self.dialog.open()

    def close(self):
        self.dialog.close()

    def _build_dialog(self):
        with self.dialog:
            with ui.card().classes('w-full max-w-4xl mx-auto').style('max-height: 90vh; overflow-y: auto'):
                with ui.row().classes('w-full items-center justify-between mb-4'):
                    ui.label('Settings & System Status').classes('text-2xl font-bold')
                    ui.button(icon='close', on_click=self.dialog.close).props('flat round')

                with ui.tabs().classes('w-full') as settings_tabs:
                    agent_tab = ui.tab('Agents', icon='computer')
                    models_tab = ui.tab('Models', icon='psychology')
                    model_settings_tab = ui.tab('Model Settings', icon='tune')
                    guide_tab = ui.tab('Performance Guide', icon='auto_awesome')
                    config_tab = ui.tab('Configuration', icon='settings')

                with ui.tab_panels(settings_tabs, value=agent_tab).classes('w-full').style('min-height: 400px'):
                    # --- Agents Tab (Status + Security Policy) ---
                    with ui.tab_panel(agent_tab):
                        self._render_agents_tab()

                    # --- Models Tab ---
                    with ui.tab_panel(models_tab):
                        self._render_models_tab()

                    # --- Model Settings Tab ---
                    with ui.tab_panel(model_settings_tab):
                        self._render_model_settings_tab()

                    # --- Performance Guide Tab ---
                    with ui.tab_panel(guide_tab):
                        self._render_guide_tab()

                    # --- Config Tab ---
                    with ui.tab_panel(config_tab):
                        self._render_config_tab()

    def _render_guide_tab(self):
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

    def _render_agents_tab(self):
        ui.label('Connected Agents & Security').classes('text-lg font-bold mb-2')
        agents_container = ui.column().classes('w-full gap-4')

        async def refresh_agents_panel():
            agents_container.clear()
            from app.models.db import Agent
            db = self.data_manager.get_db()
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

                                async def delete_agent(a_id=agent.id):
                                    if self.data_manager.delete_agent(a_id):
                                        ui.notify(f"Agent deleted successfully", type='positive')
                                        await refresh_agents_panel()
                                    else:
                                        ui.notify("Failed to delete agent", type='negative')

                                ui.button(icon='delete', on_click=delete_agent).props('flat round color=negative').tooltip('Delete Agent')
            finally:
                db.close()

        ui.button('Refresh Agents', icon='refresh', on_click=refresh_agents_panel).props('flat')
        ui.timer(0.1, refresh_agents_panel, once=True)

    def _render_models_tab(self):
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
            if not query: return
            ui.notify(f'Searching for "{query}"...', type='info')
            results = await self.model_manager.search_hf_models(query)
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
            files = await self.model_manager.get_model_files(repo_id)
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
                self.model_manager.set_token(hf_token)
            download_progress_row.set_visibility(True)
            download_progress_label.set_text(f'⏳ Downloading {filename} from {repo_id}...')
            try:
                await self.model_manager.download_model(repo_id, filename)
                ui.notify(f'Download complete: {filename}', type='positive')
                refresh_local_models()
            except Exception as e:
                ui.notify(f'Download failed: {str(e)}', type='negative')
            download_progress_row.set_visibility(False)

        def refresh_local_models():
            local_m_container.clear()
            local_models = self.model_manager.get_local_models()
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
                                    await self.model_manager.load_model(
                                        name,
                                        n_ctx=n_ctx,
                                        n_parallel=n_parallel,
                                        kv_cache_type=kv_cache_type,
                                        gpu_offload_percent=gpu_percent
                                    )
                                    ui.notify(f'Model loaded: {name}', type='positive')
                                    self.loaded_model_label.set_text(f'🧠 {self.llm_service.model_name or "No model loaded"}')
                                    self.release_btn.set_visibility(True)
                                except Exception as e:
                                    ui.notify(f'Load failed: {str(e)}', type='negative')

                            def delete_m(filename=m['name']):
                                if self.model_manager.delete_model(filename):
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

    def _render_model_settings_tab(self):
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

    def _render_config_tab(self):
        ui.label('API Keys & Settings').classes('text-lg font-bold mb-4')
        hf_token_input = ui.input('Hugging Face Token', password=True, value=app.storage.user.get('hf_token', '')).classes('w-full mb-2')
        def save_hf_token():
            app.storage.user['hf_token'] = hf_token_input.value
            self.model_manager.set_token(hf_token_input.value)
            ui.notify('Hugging Face token saved!', type='positive')

        ui.button('Save HF Token', on_click=save_hf_token).props('flat color=primary').classes('mb-4')
        ui.separator().classes('my-4')

        def toggle_dark_mode(e):
            app.storage.user['dark_mode'] = e.value
            if e.value: ui.dark_mode().enable()
            else: ui.dark_mode().disable()

        ui.switch('Enable Dark Mode', value=app.storage.user.get('dark_mode', False), on_change=toggle_dark_mode)
        ui.separator().classes('my-4')
        ui.label('Mobile Notifications').classes('text-lg font-bold mb-2')

        async def request_push():
            vapid_key = settings.VAPID_PUBLIC_KEY
            js_code = f"""
            const VAPID_PUBLIC_KEY = '{settings.VAPID_PUBLIC_KEY}';
            function urlB64ToUint8Array(base64String) {{
                const padding = '='.repeat((4 - base64String.length % 4) % 4);
                const base64 = (base64String + padding).replace(/\-/g, '+').replace(/_/g, '/');
                const rawData = window.atob(base64);
                const outputArray = new Uint8Array(rawData.length);
                for (let i = 0; i < rawData.length; ++i) {{ outputArray[i] = rawData.charCodeAt(i); }}
                return outputArray;
            }}
            if ('serviceWorker' in navigator) {{
                navigator.serviceWorker.register('/sw.js').then(function(registration) {{
                    return registration.pushManager.getSubscription().then(async function(subscription) {{
                        if (subscription) return subscription;
                        const permission = await Notification.requestPermission();
                        if (permission !== 'granted') throw new Error('Permission not granted');
                        return registration.pushManager.subscribe({{ userVisibleOnly: true, applicationServerKey: urlB64ToUint8Array(VAPID_PUBLIC_KEY) }});
                    }});
                }}).then(function(pushSubscription) {{
                    return fetch('/api/v1/webpush/subscribe', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: JSON.stringify(pushSubscription) }});
                }}).then(function(response) {{
                    if (response.ok) console.log('Subscribed!');
                    else console.error('Failed to save subscription.');
                }}).catch(function(error) {{ console.error('Error: ' + error.message); }});
            }} else {{ console.error('Service Workers not supported.'); }}
            """
            await ui.run_javascript(js_code, timeout=5.0)
            ui.notify('Notification request sent. Check browser permissions.', type='info')

        ui.button('Enable Notifications', icon='notifications_active', on_click=request_push).props('color=primary outline').classes('w-full')
        
        async def trigger_test():
            await ui.run_javascript("fetch('/api/v1/webpush/test', {method: 'POST'})")
            ui.notify('Test notification requested...', color='info')

        ui.button('Send Test Notification', icon='send', on_click=trigger_test).props('color=secondary outline').classes('w-full mt-2')
