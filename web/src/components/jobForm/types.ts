import type { Dayjs } from "dayjs";
import type { Job, JobPayload, Task } from "../../services/tasks";

export type JobFormValues = {
  name: string;
  start_time: Dayjs;
  end_time: Dayjs;
  execution_time: Dayjs;
  date_baseline: "current_day" | "previous_day";
  schedule_type: string;
  cron_expression?: string;
  weekdays?: number[];
  offset_minutes: number;
  interval_enabled: boolean;
  interval_minutes?: number;
  window_start: Dayjs;
  window_end: Dayjs;
  disk_alert_enabled: boolean;
  disk_alert_threshold_mb: number;
  max_retry: number;
  retry_interval_sec: number;
  is_enabled: boolean;
  description?: string;
  custom_range?: [Dayjs, Dayjs];
  active_range?: [Dayjs, Dayjs];
  github_deploy_enabled: boolean;
  github_config_id?: number;
  github_filename_template?: string;
  html_backup_enabled: boolean;
  html_backup_path?: string;
  html_backup_filename_template?: string;
  html_backup_filename_date_offset_days: number;
  days_offset: number;
  message_stats_enabled: boolean;
  message_stats_formats: string[];
  message_stats_path?: string;
  message_stats_filename_template?: string;
  message_stats_filename_date_offset_days: number;
  message_stats_github_enabled: boolean;
  message_stats_github_config_id?: number;
  message_stats_github_filename_template?: string;
  message_stats_github_filename_date_offset_days: number;
  message_stats_github_root?: string;
  chatlog_backup_enabled: boolean;
  chatlog_backup_formats: ("md" | "txt")[];
  chatlog_backup_path?: string;
  chatlog_backup_filename_template?: string;
  chatlog_backup_filename_date_offset_days: number;
  model_output_backup_enabled: boolean;
  model_output_path?: string;
  model_output_formats: ("md" | "txt")[];
  model_output_filename_template?: string;
  model_output_filename_date_offset_days: number;
  topic_text_layout: "per_topic" | "merged" | "auto";
  topic_text_merge_threshold: number;
  topic_image_enabled: boolean;
  topic_image_layout: "single" | "collection" | "auto";
  topic_image_merge_threshold: number;
  topic_image_backup_enabled: boolean;
  topic_image_backup_path?: string;
  image_prompt_template_id?: number;
  image_split_enabled: boolean;
  image_split_prompt?: string | null;
  image_aspect_ratio: "auto" | "1:1" | "3:2" | "2:3" | "9:16" | "1:3";
  image_resolution: "auto" | "1k" | "2k" | "4k";
  max_image_count: number;
  ima_sync_enabled: boolean;
  ima_use_default_account: boolean;
  ima_account_id?: number;
  ima_use_default_target: boolean;
  ima_target_type: "note" | "knowledge_base";
  ima_note_folder_id?: string;
  ima_knowledge_base_id?: string;
  ima_knowledge_folder_id?: string;
  weekly_period: "previous_week" | "current_week";
  weekly_start_day: number;
  weekly_start_time_picker: Dayjs;
  weekly_end_day: number;
  weekly_end_time_picker: Dayjs;
  weekly_report_weekday?: number;
};

export type JobFormModalProps = {
  open: boolean;
  initialValues?: Job | null;
  taskType?: Task["task_type"];
  confirmLoading?: boolean;
  onCancel: () => void;
  onSubmit: (values: JobPayload) => void | Promise<void>;
};

export type ViewMode = "classic" | "split";

export type SectionKey =
  | "basic"
  | "topic_card"
  | "image_card"
  | "chatlog"
  | "message_stats"
  | "message_stats_github"
  | "model_output"
  | "github_deploy"
  | "html_backup"
  | "advanced";
