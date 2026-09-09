import apiClient from "./apiClient";
import type { ApiResponse } from "./apiClient";

export type Job = {
  id: number;
  created_at: string;
  updated_at: string;
  task_id: number;
  name: string;
  start_time: string;
  end_time: string;
  execution_time?: string | null;
  date_baseline: string;
  schedule_type: string;
  cron_expression?: string | null;
  weekdays?: number[] | null;
  offset_minutes: number;
  interval_enabled: boolean;
  interval_minutes?: number | null;
  window_start: string;
  window_end: string;
  disk_alert_enabled: boolean;
  disk_alert_threshold_bytes: number;
  max_retry: number;
  retry_interval_sec: number;
  is_enabled: boolean;
  description?: string | null;
  last_run_at?: string | null;
  next_run_at?: string | null;
  github_deploy_enabled: boolean;
  github_config_id?: number | null;
  github_config?: { id: number; name: string } | null;
  html_backup_enabled: boolean;
  html_backup_path?: string | null;
  html_backup_filename_template?: string | null;
  html_backup_filename_date_offset_days: number;
  github_filename_template?: string | null;
  days_offset: number;
  display_order: number;
  message_stats_enabled: boolean;
  message_stats_formats?: string[] | null;
  message_stats_path?: string | null;
  message_stats_filename_template?: string | null;
  message_stats_filename_date_offset_days: number;
  message_stats_github_enabled: boolean;
  message_stats_github_config_id?: number | null;
  message_stats_github_config?: { id: number; name: string } | null;
  message_stats_github_filename_template?: string | null;
  message_stats_github_filename_date_offset_days: number;
  message_stats_github_root?: string | null;
  chatlog_backup_enabled?: boolean | null;
  chatlog_backup_formats?: ("md" | "txt")[] | null;
  chatlog_backup_path?: string | null;
  chatlog_backup_filename_template?: string | null;
  chatlog_backup_filename_date_offset_days?: number;
  model_output_backup_enabled: boolean;
  model_output_path?: string | null;
  model_output_formats?: string[] | null;
  model_output_filename_template?: string | null;
  model_output_filename_date_offset_days: number;
  ima_sync_enabled?: boolean | null;
  ima_use_default_account?: boolean | null;
  ima_account_id?: number | null;
  ima_account_name?: string | null;
  ima_use_default_target?: boolean | null;
  ima_target_type?: "note" | "knowledge_base" | null;
  ima_note_folder_id?: string | null;
  ima_note_folder_name?: string | null;
  ima_knowledge_base_id?: string | null;
  ima_knowledge_base_name?: string | null;
  ima_knowledge_folder_id?: string | null;
  ima_knowledge_folder_name?: string | null;
  weekly_period?: "current_week" | "previous_week" | null;
  weekly_start_day?: number | null;
  weekly_start_time?: string | null;
  weekly_end_day?: number | null;
  weekly_end_time?: string | null;
  topic_text_layout: "per_topic" | "merged" | "auto";
  topic_text_merge_threshold: number;
  topic_image_enabled: boolean;
  topic_image_layout: "single" | "collection" | "auto";
  topic_image_merge_threshold: number;
  topic_image_backup_enabled: boolean;
  topic_image_backup_path?: string;
  image_prompt_template_id?: number | null;
  image_prompt?: string | null;
  image_split_enabled: boolean;
  image_split_prompt?: string | null;
  image_aspect_ratio: "auto" | "1:1" | "3:2" | "2:3" | "9:16" | "1:3";
  image_resolution: "auto" | "1k" | "2k" | "4k";
  max_image_count: number;
  card_renderer?: "ai" | "local";
  card_font_theme?: "A" | "B" | "C";
};

export type TopicTypeKey = "industry_business" | "work_methods" | "career_growth" | "mind_wellbeing";
export type TopicStyleKey = "style_a" | "style_b" | "style_c" | "style_d";
export type TopicThemeKey = "amber" | "blue" | "green" | "neutral";
export type TopicStyleConfig = Record<TopicTypeKey, { style_key: TopicStyleKey; theme: TopicThemeKey }>;

export type Task = {
  id: number;
  created_at: string;
  updated_at: string;
  name: string;
  task_type: "report" | "export" | "topic_card" | "image_card";
  prompt: string;
  model_id?: number | null;
  image_model_id?: number | null;
  upstream_task_id?: number | null;
  card_input_source?: "chatlog" | "report";
  model_sequence?: TaskModelConfig[];
  image_model_sequence?: TaskModelConfig[];
  prompt_template_id?: number | null;
  talkers: string[];
  talker_names: string[];
  push_webhook_ids: number[];
  alert_webhook_ids?: number[] | null;
  is_active: boolean;
  store_chatlog?: boolean;
  system_prompt_custom_enabled: boolean;
  system_prompt_template?: string | null;
  system_prompt_include_message_count: boolean;
  topic_style_config: TopicStyleConfig;
  jobs: Job[];
};

export type TaskModelConfig = {
  model_id: number;
  max_attempts: number;
};

export type TaskPayload = {
  name: string;
  task_type: "report" | "export" | "topic_card" | "image_card";
  prompt: string;
  model_id?: number | null;
  image_model_id?: number | null;
  upstream_task_id?: number | null;
  card_input_source?: "chatlog" | "report";
  model_sequence?: TaskModelConfig[] | null;
  image_model_sequence?: TaskModelConfig[] | null;
  prompt_template_id?: number | null;
  talkers: string[];
  talker_names?: string[];
  push_webhook_ids: number[];
  alert_webhook_ids?: number[] | null;
  is_active: boolean;
  system_prompt_custom_enabled: boolean;
  system_prompt_template?: string | null;
  system_prompt_include_message_count: boolean;
  topic_style_config?: TopicStyleConfig;
};

export type TaskUpdatePayload = Partial<Omit<TaskPayload, "talkers" | "push_webhook_ids">> & {
  talkers?: string[];
  talker_names?: string[];
  push_webhook_ids?: number[];
};

export type JobPayload = {
  name: string;
  start_time: string;
  end_time: string;
  execution_time?: string | null;
  date_baseline?: string;
  schedule_type: string;
  cron_expression?: string | null;
  weekdays?: number[] | null;
  offset_minutes: number;
  interval_enabled: boolean;
  interval_minutes?: number | null;
  window_start: string;
  window_end: string;
  disk_alert_enabled: boolean;
  disk_alert_threshold_bytes: number;
  max_retry: number;
  retry_interval_sec: number;
  is_enabled: boolean;
  description?: string | null;
  github_deploy_enabled: boolean;
  github_config_id?: number | null;
  html_backup_enabled: boolean;
  html_backup_path?: string;
  html_backup_filename_template?: string;
  // 功能关闭时该字段不出现在提交里（undefined 会被 JSON 序列化丢弃），故为可选
  html_backup_filename_date_offset_days?: number;
  github_filename_template?: string;
  days_offset: number;
  message_stats_enabled: boolean;
  message_stats_formats?: string[];
  message_stats_path?: string;
  message_stats_filename_template?: string;
  message_stats_filename_date_offset_days?: number;
  message_stats_github_enabled: boolean;
  message_stats_github_config_id?: number | null;
  message_stats_github_filename_template?: string;
  message_stats_github_filename_date_offset_days?: number;
  message_stats_github_root?: string;
  chatlog_backup_enabled?: boolean;
  chatlog_backup_formats?: ("md" | "txt")[];
  chatlog_backup_path?: string;
  chatlog_backup_filename_template?: string;
  chatlog_backup_filename_date_offset_days?: number;
  model_output_backup_enabled: boolean;
  model_output_path?: string;
  model_output_formats?: ("md" | "txt")[];
  model_output_filename_template?: string;
  model_output_filename_date_offset_days?: number;
  ima_sync_enabled?: boolean;
  ima_use_default_account?: boolean;
  ima_account_id?: number | null;
  ima_use_default_target?: boolean;
  ima_target_type?: "note" | "knowledge_base";
  ima_note_folder_id?: string | null;
  ima_note_folder_name?: string;
  ima_knowledge_base_id?: string | null;
  ima_knowledge_base_name?: string;
  ima_knowledge_folder_id?: string | null;
  ima_knowledge_folder_name?: string;
  weekly_period?: "current_week" | "previous_week";
  weekly_start_day?: number;
  weekly_start_time?: string;
  weekly_end_day?: number;
  weekly_end_time?: string;
  topic_text_layout: "per_topic" | "merged" | "auto";
  topic_text_merge_threshold: number;
  topic_image_enabled: boolean;
  topic_image_layout: "single" | "collection" | "auto";
  topic_image_merge_threshold: number;
  topic_image_backup_enabled: boolean;
  topic_image_backup_path?: string;
  image_prompt_template_id?: number | null;
  image_split_enabled: boolean;
  image_split_prompt?: string | null;
  image_aspect_ratio: "auto" | "1:1" | "3:2" | "2:3" | "9:16" | "1:3";
  image_resolution: "auto" | "1k" | "2k" | "4k";
  max_image_count: number;
};

export type JobUpdatePayload = Partial<JobPayload>;

export async function fetchTasks(): Promise<Task[]> {
  const response = await apiClient.get<ApiResponse<Task[]>>("/api/tasks/");
  return response.data.data;
}

export async function createTask(payload: TaskPayload): Promise<Task> {
  const response = await apiClient.post<ApiResponse<Task>>("/api/tasks/", payload);
  return response.data.data;
}

export async function updateTask(taskId: number, payload: TaskUpdatePayload): Promise<Task> {
  const response = await apiClient.put<ApiResponse<Task>>(`/api/tasks/${taskId}`, payload);
  return response.data.data;
}

export async function deleteTask(taskId: number): Promise<void> {
  await apiClient.delete<ApiResponse<null>>(`/api/tasks/${taskId}`);
}

export async function createJob(taskId: number, payload: JobPayload): Promise<Job> {
  const response = await apiClient.post<ApiResponse<Job>>(`/api/tasks/${taskId}/jobs`, payload);
  return response.data.data;
}

export async function updateJob(jobId: number, payload: JobUpdatePayload): Promise<Job> {
  const response = await apiClient.put<ApiResponse<Job>>(`/api/tasks/jobs/${jobId}`, payload);
  return response.data.data;
}

export async function deleteJob(jobId: number): Promise<void> {
  await apiClient.delete<ApiResponse<null>>(`/api/tasks/jobs/${jobId}`);
}

export async function runJob(jobId: number, selectedTopic?: string): Promise<void> {
  await apiClient.post<ApiResponse<unknown>>(`/api/tasks/jobs/${jobId}/run`, {
    selected_topic: selectedTopic || undefined
  });
}

export async function reorderJobs(taskId: number, jobIds: number[]): Promise<Job[]> {
  const response = await apiClient.post<ApiResponse<Job[]>>(`/api/tasks/${taskId}/jobs/reorder`, { job_ids: jobIds });
  return response.data.data;
}
