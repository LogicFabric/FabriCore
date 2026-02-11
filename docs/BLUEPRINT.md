---
config:
  layout: dagre
---
classDiagram
direction TB
	namespace Client_Agent {
        class Main {
	        -config: AgentConfig
	        -interrupt_chan: chan os.Signal
	        -server_url: string
	        -auth_token: string
	        -retry_count: int
	        +main()
	        +loadConfig()
	        +setupSignalHandler()
	        +initializeComponents()
	        +waitForShutdown()
        }

        class SecurityManager {
	        -security_policies: PolicyMap
	        -hitl_enabled: bool
	        -whitelisted_commands: []string
	        -admin_users: []string
	        -audit_log_buffer: []LogEntry
	        +loadSecurityRoles()
	        +validateAction(actionType, command) bool
	        +requireHITLApproval(toolName) bool
	        +logSecurityViolation(event)
	        +updatePolicy(newPolicy)
	        +isCommandWhitelisted(cmd) bool
        }

        class WebSocketClient {
	        -conn: *websocket.Conn
	        -server_url: string
	        -token: string
	        -retry_backoff: time.Duration
	        -is_connected: bool
	        -mu: sync.Mutex
	        -message_queue: chan []byte
	        +connect(url, token) error
	        +listenLoop()
	        +send(message) error
	        +sendHeartbeat()
	        +reconnect()
	        +close()
	        +isConnected() bool
        }

        class Syscall {
	        -os_platform: string
	        -arch: string
	        -host_uptime: time.Duration
	        +execCommand(cmd, args)(output, error)
	        +getSystemResources()(CPU, RAM, Disk)
	        +manageService(action, serviceName) error
	        +getProcessList() []Process
	        +killProcess(pid) error
	        +readFile(path)(content, error)
	        +writeFile(path, content) error
	        +getDiskUsage(path) DiskInfo
        }

        class MCPManager {
	        -registered_servers: map[string]MCPServer
	        -json_rpc_version: string
	        -request_timeout: time.Duration
	        +decodeMessage(payload)(Request, error)
	        +encodeResponse(id, result, error) []byte
	        +validateSchema(json) bool
	        +routeRequest(tool_name, args)(Result, error)
	        +initializeInternalServers()
	        +listCapabilities() []Capability
        }

        class ThirdPartyMCP {
	        -discovered_servers: []MCPEndpoint
	        -active_transports: map[string]Transport
	        -scan_interval: time.Duration
	        +registerTool(name, function)
	        +executeTool(name, args) Result
	        +listTools() []ToolDefinition
	        +scanLocalServers()
	        +connectToStdioServer(cmd)
	        +connectToSSEServer(url)
	        +healthCheckServers()
        }

        class Orchestrator_2["Orchestrator"] {
	        -state: AgentState
	        -pending_requests: map[string]Request
	        -active_tasks: int
	        +HandleServerMessage(json_msg)
	        +RegisterCapabilities()
	        +Shutdown()
	        +dispatchToSyscall(cmd)
	        +dispatchToMCP(req)
	        +reportTaskStatus(taskId, status)
        }

        class Logger_2["Logger"] {
	        -log_file: *os.File
	        -log_level: int
	        -format: string
	        +Info(msg)
	        +Error(msg)
	        +Debug(msg)
	        +rotateLogs()
	        +sync()
        }

	}
	namespace Docker_Compose {
        class Main_2["Main"] {
	        -app: FastAPI
	        -server_config: Config
	        -startup_time: datetime
	        +start_server()
	        +initialize_db()
	        +mount_static_files()
	        +setup_middleware()
	        +startup_event()
	        +shutdown_event()
        }

        class ModelManager {
	        -current_model: string
	        -strategy: StrategyEnum
	        -temperature: float
	        -max_tokens: int
	        -active_context: Dict
	        +process_user_intent(prompt) Plan
	        +select_model(strategy) Model
	        +parse_llm_output_to_json(text) Dict
	        +optimize_context_window(history)
	        +validate_tool_call(tool_name, args)
	        +switch_model_strategy(new_strategy)
        }

        class WebSocketServer {
	        -active_connections: Dict[str, WebSocket]
	        -agent_metadata: Dict[str, AgentInfo]
	        -ping_interval: int
	        +accept_connection(socket)
	        +register_agent(agent_id, metadata)
	        +remove_agent(agent_id)
	        +send_command(agent_id, json_rpc)
	        +broadcast_event(event_type, payload)
	        +get_active_agents() List
	        +ping_agent(agent_id)
        }

        class Orchestrator {
	        -execution_queue: Queue
	        -active_plans: Dict[str, Plan]
	        -task_history: List[Task]
	        +process_user_input(text)
	        +dispatch_agent_command(agent_id, tool, args)
	        +handle_agent_result(id, result)
	        +synthesize_final_response(history)
	        +check_permissions(user, agent)
	        +abort_task(task_id)
        }

        class Logger {
	        -file_path: string
	        -format: string
	        -rotation_policy: Policy
	        +log(level, message, metadata)
	        +log_audit(user, action)
	        +get_recent_logs(limit)
	        +archive_old_logs()
        }

        class Frontend {
	        -ui_state: State
	        -theme: ThemeConfig
	        -refresh_rate: int
	        -active_users: int
	        -dark_mode_enabled: bool
	        +serve_react_app()
	        +handle_api_request(route)
	        +websocket_endpoint(client_id)
	        +render_dashboard()
	        +render_agent_detail(agent_id)
	        +render_settings_page()
	        +render_models_page()
	        +render_login_page()
	        +push_notification(msg)
	        +update_agent_status_ui(agent_id, status)
	        +toggle_dark_mode(enable)
        }

        class PostgreSQL {
	        -connection_pool_size: int
	        -host: string
	        -port: int
	        -user: string
	        -password: string
	        +Tables: Agents
	        +Tables: AuditLogs
	        +Tables: Users
	        +Tables: Settings
	        +Tables: ChatHistory
        }

        class SettingsWindow {
	        -api_key: string
	        -backend_address: string
	        -HITL_enabled: bool
	        -permissions: Dict
	        -restrictions: Dict
	        -mcp_tools: List
	        +get_global_settings() Dict
	        +update_model_path(path)
	        +toggle_security_mode(bool)
	        +add_allowed_tool(tool_def)
	        +rotate_api_keys()
	        +backup_configuration()
	        +render_ui_elements()
        }

        class ChatWindow {
	        -history: List[Message]
	        -configs: ChatConfig
	        -sessions: map[id]Session
	        -current_session_id: str
	        +create_session(user_id)
	        +add_message(role, content)
	        +get_chat_history(session_id)
	        +clear_history()
	        +search_history(query)
	        +render_message_bubble(msg)
        }

        class Scheduler {
	        -jobs: List[Job]
	        -scheduler_engine: AsyncIOScheduler
	        -timezone: str
	        +add_job(cron_expression, task_func)
	        +remove_job(job_id)
	        +start_scheduler()
	        +trigger_maintenance_window()
	        +schedule_llm_task(prompt, interval)
	        +get_pending_jobs()
        }

        class LocalStorage {
	        -mount_point: Path
	        -quota_bytes: int
	        -used_bytes: int
	        +DockerVolume: "fabricore_data"
	        +check_integrity()
	        +prune_temp_files()
        }

        class OnlineModels {
	        -claude_api_key: string
	        -gemini_api_key: string
	        -chatgpt_api_key: string
	        -timeout: int
	        -retry_policy: Policy
	        +set_API_key(provider, key)
	        +get_History()
	        +call_external_api(messages)
	        +calculate_cost(tokens)
	        +handle_rate_limit()
	        +stream_response(messages)
        }

        class LocalModels {
	        -model_path: string
	        -context_window: int
	        -n_gpu_layers: int
	        -llama_instance: Llama
	        -is_loaded: bool
	        -available_models: List[ModelInfo]
	        +load_model(path)
	        +get_models(directory) List
	        +get_available_downloads() List[ModelInfo]
	        +download_model(model_id)
	        +generate_completion(prompt, constraints)
	        +unload_model()
	        +tokenize(text)
	        +get_vram_usage()
        }

        class ModelManager {
	        -models_dir: Path
	        -hf_token: string
	        -api: HfApi
	        -download_status: Dict
	        +set_token(token)
	        +get_available_models() List[ModelInfo]
	        +get_local_models() List[ModelInfo]
	        +is_model_installed(repo_id, filename) bool
	        +download_model(repo_id, filename) async
	        +download_model_sync(repo_id, filename)
	        +get_download_status(repo_id) Dict
	        +delete_model(filename) bool
        }

        class CommunicationManager {
	        -ws_server: WebSocketServer
	        -notification_service: NotificationService
	        -alert_thresholds: Dict
	        +route_ingress_traffic(packet)
	        +dispatch_egress(target, message)
	        +handle_ws_disconnect(agent_id)
	        +broadcast_system_alert(level, msg)
	        +check_connection_health()
        }

        class NotificationService {
	        -smtp_config: SMTPConfig
	        -telegram_bot_token: string
	        -sms_gateway_key: string
	        -recipient_list: List[str]
	        +send_email(subject, body)
	        +send_telegram(message)
	        +send_sms(number, message)
	        +test_connection(provider)
        }

        class DataManager {
	        -engine: Engine
	        -session_factory: sessionmaker
	        -db_url: string
	        -local_storage_path: Path
	        +get_db_session() Session
	        +db_load_config(key) string
	        +db_save_config(key, value)
	        +db_log_audit_event(agent_id, command, result)
	        +db_get_agent_history(agent_id)
	        +db_get_user_by_username(username) User
	        +db_cleanup_old_logs(days)
	        +fs_save_file(filename, bytes)
	        +fs_get_file(filename) Bytes
	        +fs_list_files(directory)
        }

        class Authenticator {
	        -jwt_secret: string
	        -algorithm: string
	        -access_token_expire: int
	        +login_user(username, password) Token
	        +verify_token(token) UserID
	        +create_access_token(data) string
	        +get_current_user(token) User
	        +hash_password(password) string
	        +verify_password(plain, hashed) bool
	        +check_permissions(user, resource) bool
        }

	}

	<<Go>> Main
	<<Go>> SecurityManager
	<<Go>> WebSocketClient
	<<Go>> Syscall
	<<Go>> MCPManager
	<<Go>> ThirdPartyMCP
	<<Go>> Orchestrator_2
	<<Go>> Logger_2
	<<Python>> Main_2
	<<Python>> ModelManager
	<<Python>> WebSocketServer
	<<Python>> Orchestrator
	<<Python>> Logger
	<<Python>> Frontend
	<<DockerImage>> PostgreSQL
	<<Python>> SettingsWindow
	<<Python>> ChatWindow
	<<Python>> Scheduler
	<<Python>> LocalStorage
	<<Python>> OnlineModels
	<<Python>> LocalModels
	<<Python>> CommunicationManager
	<<Python>> NotificationService
	<<Python>> DataManager
	<<Python>> Authenticator

    SecurityManager -- Syscall
    WebSocketServer .. WebSocketClient
    MCPManager -- WebSocketClient
    Main -- Orchestrator_2
    Main -- Logger_2
    Orchestrator_2 -- MCPManager
    Orchestrator_2 -- SecurityManager
    MCPManager -- ThirdPartyMCP
    Main_2 -- Orchestrator
    Main_2 -- Logger
    Main_2 -- Scheduler
    Orchestrator -- DataManager
    Orchestrator -- ModelManager
    Orchestrator -- Frontend
    Orchestrator -- CommunicationManager
    DataManager -- PostgreSQL
    DataManager -- LocalStorage
    ModelManager -- LocalModels
    ModelManager -- OnlineModels
    CommunicationManager -- WebSocketServer
    CommunicationManager -- NotificationService
    Frontend -- ChatWindow
    Frontend -- SettingsWindow
    DataManager -- Authenticator