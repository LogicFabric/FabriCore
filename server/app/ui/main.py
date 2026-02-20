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
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.core.config import settings
from app.ui.components.settings import SettingsDialog
from app.ui.components.scheduler import SchedulerDialog
from app.ui.components.hitl import HITLDialog
from app.ui.components.chat import ChatInterface

logger = logging.getLogger(__name__)

# Singletons
data_manager = DataManager()
scheduler_service = SchedulerService()

def init_ui():
    # PWA Mounting
    app.mount("/static/pwa", StaticFiles(directory="app/static/pwa"), name="pwa")
    
    @app.get("/sw.js")
    async def get_sw():
        return FileResponse("app/static/pwa/sw.js")


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

        ui.add_head_html('<link rel="manifest" href="/static/pwa/manifest.json">')
        ui.add_head_html('<meta name="theme-color" content="#121212">')
        ui.add_head_html('<link rel="apple-touch-icon" href="/static/pwa/icon-192.png">')
        ui.add_head_html("""
            <style>
                @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');
                body { font-family: 'Inter', system-ui, sans-serif !important; transition: background-color 0.3s, color 0.3s; }
                .body--dark { background-color: #0a0a0a !important; color: #e0e0e0 !important; }
                .body--light { background-color: #f8f9fa !important; color: #1a1a1a !important; }
                
                .nicegui-content { padding: 0 !important; }
                
                .body--dark .q-layout, .body--dark .q-page-container { background-color: #0a0a0a !important; }
                .body--light .q-layout, .body--light .q-page-container { background-color: #f8f9fa !important; }
                
                .body--dark .q-header { background-color: rgba(18, 18, 18, 0.8) !important; backdrop-filter: blur(10px); border-bottom: 1px solid rgba(255, 255, 255, 0.1); }
                .body--light .q-header { background-color: rgba(255, 255, 255, 0.8) !important; backdrop-filter: blur(10px); border-bottom: 1px solid rgba(0, 0, 0, 0.1); }
                
                .body--dark .q-drawer { background-color: #121212 !important; border-right: 1px solid rgba(255, 255, 255, 0.05) !important; }
                .body--light .q-drawer { background-color: #ffffff !important; border-right: 1px solid rgba(0, 0, 0, 0.05) !important; }
                
                .body--dark .q-card { background-color: #1a1a1a !important; border: 1px solid rgba(255, 255, 255, 0.1) !important; border-radius: 12px !important; }
                .body--light .q-card { background-color: #ffffff !important; border: 1px solid rgba(0, 0, 0, 0.1) !important; border-radius: 12px !important; }
                
                .q-btn { border-radius: 8px !important; text-transform: none !important; font-weight: 500 !important; }
                
                /* Selection colors */
                ::selection { background: rgba(33, 150, 243, 0.3); }

                /* Prevent drawer horizontal scrolling */
                .q-drawer__content { overflow-x: hidden !important; }
            </style>
        """)

        # --- Services ---
        llm_service = get_llm_service()
        model_manager = get_model_manager()
        tool_executor = ToolExecutor(data_manager)

        # --- UI Components / State ---
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
                        ui.notify('Model released.', type='positive')
                        loaded_model_label.set_text('🧠 No model loaded')
                        release_btn.set_visibility(False)
                    else: ui.notify('Failed to release model', type='negative')

                release_btn = ui.button(icon='power_settings_new', on_click=release_m).props('flat round color=negative sm').tooltip('Unload model')
                release_btn.set_visibility(bool(llm_service.model_name))

            # Initialize components
            settings_dlg = SettingsDialog(data_manager, loaded_model_label, release_btn)
            hitl_dlg = HITLDialog(data_manager)
            sched_dlg = SchedulerDialog(data_manager, scheduler_service)

            ui.button(icon='shield', on_click=hitl_dlg.open).props('flat round').classes('text-gray-800 dark:text-white').tooltip('HITL Security')
            ui.button(icon='schedule', on_click=sched_dlg.open).props('flat round').classes('text-gray-800 dark:text-white').tooltip('Schedules')
            ui.button(icon='settings', on_click=settings_dlg.open).props('flat round').classes('text-gray-800 dark:text-white').tooltip('Settings')

        # --- Left Drawer (Chat History) ---
        with ui.left_drawer(value=True, fixed=True).classes('bg-gray-50 dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700').props('bordered') as drawer:
            ui.label('CHAT HISTORY').classes('text-gray-500 dark:text-gray-400 text-xs font-bold p-4 tracking-tighter')
            session_list_container = ui.column().classes('w-full px-2 gap-1')
            ui.separator().classes('my-4')
            
            def refresh_sessions():
                session_list_container.clear()
                sessions = data_manager.get_chat_sessions()
                with session_list_container:
                    for s in sessions:
                        is_active = (s.id == chat_ui.active_session_id)
                        with ui.element('div').classes('w-full flex items-center group rounded-lg px-1 transition-colors overflow-hidden ' + ('bg-blue-100 dark:bg-blue-900 border-l-4 border-blue-600 ' if is_active else 'hover:bg-gray-200 dark:hover:bg-gray-700 ')):
                            if getattr(s, 'has_unread', False) and not is_active:
                                ui.icon('circle', size='xs').classes('text-blue-500 mr-1').style('font-size: 8px;')
                            ui.button(s.title[:25] + ('...' if len(s.title) > 25 else ''), on_click=lambda s_id=s.id: chat_ui.load_chat(s_id)).props('flat no-caps').classes('flex-grow text-gray-700 dark:text-gray-300 justify-start px-2 text-left truncate').style('text-transform: none; overflow: hidden;')
                            
                            async def delete_session(s_id=s.id):
                                data_manager.delete_chat_session(s_id)
                                if s_id == chat_ui.active_session_id: start_new_chat()
                                else: refresh_sessions()
                            ui.button(icon='delete', on_click=delete_session).props('flat round size=sm').classes('opacity-0 group-hover:opacity-100 transition-opacity text-gray-400 hover:text-red-500').tooltip('Delete chat')

            def start_new_chat():
                chat_ui.active_session_id = None
                app.storage.user['current_session_id'] = None
                chat_ui.chat_messages = []
                chat_ui.total_tokens_used = 0
                chat_ui._update_context_usage()
                chat_ui.chat_container.clear()
                with chat_ui.chat_container:
                    chat_ui._render_assistant_message('**New Chat Started.** Ask me anything!')
                refresh_sessions()

            ui.button('+ New Chat', icon='add', on_click=start_new_chat).props('flat outline color=primary').classes('w-full mx-2')

        # --- Main Chat Area ---
        with ui.column().classes('w-full items-center p-0'):
            with ui.row().classes('w-full max-w-4xl items-center gap-2 px-4 py-1 bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700'):
                with ui.column().classes('flex-grow gap-0'):
                    with ui.row().classes('w-full justify-between items-center'):
                        ui.label('Context Usage').classes('text-xs text-gray-500 dark:text-gray-400')
                        context_label = ui.label('0 / 0').classes('text-xs font-mono text-gray-500 dark:text-gray-400')
                    context_bar = ui.linear_progress(value=0.0, show_value=False).props('color=primary size=4px rounded')

            chat_container = ui.column().classes('w-full max-w-4xl flex-grow p-4 gap-4')
            
            # --- Status Bar ---
            with ui.row().classes('w-full max-w-4xl items-center gap-2 px-4 py-1 bg-gray-50 dark:bg-gray-800'):
                status_spinner = ui.spinner('dots', size='sm').classes('text-primary')
                status_spinner.set_visibility(False)
                ui.label('').classes('text-xs text-primary font-medium italic animate-pulse').bind_visibility_from(status_spinner, 'visible')

            # --- Input Area (Sticky or Bottom) ---
            with ui.row().classes('w-full max-w-4xl items-center gap-2 pb-4 px-4 mt-auto'):
                text_input = ui.input(placeholder='Message FabriCore...').props('rounded outlined input-class=mx-3').classes('flex-grow')
                send_btn = ui.button(icon='send', on_click=lambda: chat_ui.send_message(text_input)).props('round flat color=primary')
            text_input.on('keydown.enter', lambda: chat_ui.send_message(text_input))

        # Initialize Chat Interface
        chat_ui = ChatInterface(data_manager, llm_service, tool_executor, context_label, context_bar, refresh_sessions)
        chat_ui.set_container(chat_container)

        # --- Theme Persistence ---
        if app.storage.user.get('dark_mode', False):
            ui.dark_mode().enable()
        else:
            ui.dark_mode().disable()

        # Startup
        refresh_sessions()
        if chat_ui.active_session_id:
            await chat_ui.load_chat(chat_ui.active_session_id)
        else:
            with chat_container:
                chat_ui._render_assistant_message('**Hello!** I am FabriCore. Load a model in Settings → Models, then ask me to help manage your systems.')