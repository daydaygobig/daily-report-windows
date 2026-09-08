import axios from "axios";

export type PromptContext = {
  task_name?: string;
  chatlog_range?: string;
  talkers?: string[];
  task_prompt?: string;
  chunked?: boolean;
  chunk_count?: number;
  chunk_limit?: number;
  raw?: string;
  chatlog_label?: string;
  system_instruction?: string;
  system_prompt?: string;
};

export type PromptUsage = {
  chars?: Record<string, number>;
  tokens?: Record<string, number>;
};

export type TopicCardMeta = {
  文字布局?: string;
  图片推送?: string;
  图片布局?: string;
  话题数量?: number;
  话题列表?: {
    标题?: string;
    话题类型?: string;
    版式?: string;
    主题色?: string;
    短标签?: string[];
    讨论时段?: string;
  }[];
  推送记录?: {
    推送渠道?: string;
    状态?: string;
    错误信息?: string | null;
    图片列表?: {
      渲染引擎?: string;
      图片布局?: string;
      图片尺寸?: string;
      文件大小?: string;
      图片标识?: string;
    }[];
  }[];
};

export type ImageCardMeta = {
  图片模型?: string;
  内容块数量?: number;
  请求比例?: string;
  分辨率档位?: string;
  请求尺寸?: string;
  请求参数?: Record<string, string | number>;
  生成状态?: string;
  生成成功数?: number;
  推送状态?: string;
  推送成功数?: number;
  推送总数?: number;
  图片列表?: {
    序号?: number;
    生成状态?: string;
    请求尺寸?: string;
    实际尺寸?: string;
    文件大小?: string;
    错误信息?: string | null;
    推送记录?: {
      推送渠道?: string;
      状态?: string;
      图片标识?: string | null;
      错误信息?: string | null;
    }[];
  }[];
  内容块列表?: {
    序号?: number;
    摘要?: string;
  }[];
};

export type Execution = {
  id: number;
  job_id: number | null;
  task_id: number | null;
  job_name?: string | null;
  task_name?: string | null;
  job_execution_time?: string | null;
  job_created_at?: string | null;
  status: string;
  summary_md?: string | null;
  error_msg?: string | null;
  summary_path?: string | null;
  chatlog_path?: string | null;
  html_backup_path?: string | null;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  prompt_chars?: number | null;
  llm_model_name?: string | null;
  duration_ms?: number | null;
  scheduled_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  created_at: string;
  prompt_context?: PromptContext | null;
  is_manual: boolean;
  prompt_usage?: PromptUsage | null;
  deploy_status?: string | null;
  deploy_url?: string | null;
  deploy_error?: string | null;
  deploy_record_id?: number | null;
  deploy_repo_path?: string | null;
  deploy_repo_full_name?: string | null;
  deploy_branch?: string | null;
  deploy_github_file_url?: string | null;
  github_deployments?: {
    id: number;
    artifact_type?: string | null;
    artifact_label?: string | null;
    status?: string | null;
    error_msg?: string | null;
    pages_url?: string | null;
    repo_full_name?: string | null;
    branch?: string | null;
    repo_path?: string | null;
    github_file_url?: string | null;
  }[] | null;
  github_config_id?: number | null;
  github_config_name?: string | null;
  ima_sync_status?: string | null;
  ima_sync_error?: string | null;
  ima_sync_batch_id?: string | null;
  exported_files?: {
    type?: string;
    label?: string;
    path?: string;
    url?: string;
    repo?: string;
    branch?: string;
    repo_path?: string;
    github_file_url?: string;
    deployment_record_id?: number | null;
    deployment_status?: string | null;
  }[] | null;
  disk_io?: {
    id: number;
    provider: string;
    backend_read_bytes?: number | null;
    backend_write_bytes?: number | null;
    weflow_read_bytes?: number | null;
    weflow_write_bytes?: number | null;
    weflow_captured: boolean;
    exported_file_bytes: number;
    chatlog_decrypt_write_bytes: number;
    chatlog_decrypt_status?: string | null;
    chatlog_work_dir?: string | null;
    disk_write_bytes: number;
    total_read_bytes: number;
    total_write_bytes: number;
    media_enabled: boolean;
    is_warning: boolean;
    warning_reason?: string | null;
    job_alert_threshold_bytes: number;
    job_alert_triggered: boolean;
    job_alert_sent: boolean;
    job_alert_error?: string | null;
  } | null;
  topic_card_meta?: TopicCardMeta | null;
  image_card_meta?: ImageCardMeta | null;
};

export type ExecutionQuery = {
  page: number;
  page_size: number;
  execution_id?: number;
  task_id?: number;
  job_id?: number;
  status?: string;
  start_time?: string;
  end_time?: string;
};

export type ExecutionPage = {
  items: Execution[];
  total: number;
  page: number;
  page_size: number;
};

export async function fetchExecutions(params: ExecutionQuery): Promise<ExecutionPage> {
  const response = await axios.get(`/api/executions/`, { params });
  return response.data.data as ExecutionPage;
}

export async function fetchExecutionDetail(executionId: number): Promise<Execution> {
  const response = await axios.get(`/api/executions/${executionId}`);
  return response.data.data as Execution;
}
