/**
 * 作业表单默认值与 Job → 表单值的转换。从 JobFormModal 拆出，逻辑原样搬移。
 */
import dayjs from "dayjs";
import type { Dayjs } from "dayjs";
import type { Job } from "../../services/tasks";
import { DEFAULT_IMAGE_SPLIT_PROMPT, normalizeImageSplitPrompt } from "../../services/promptTemplates";
import { TIME_BASE, parseTime } from "./timeUtils";
import type { JobFormValues } from "./types";

export const defaultStart = dayjs(`${TIME_BASE} 09:00`);
export const defaultEnd = dayjs(`${TIME_BASE} 18:00`);

export const defaultFormValues: JobFormValues = {
  name: "",
  start_time: defaultStart,
  end_time: defaultEnd,
  execution_time: defaultEnd,
  date_baseline: "current_day",
  schedule_type: "daily",
  cron_expression: undefined,
  weekdays: [],
  offset_minutes: 0,
  interval_enabled: false,
  interval_minutes: 120,
  window_start: dayjs(`${TIME_BASE} 00:00`),
  window_end: dayjs(`${TIME_BASE} 00:00`).add(1, "day"),
  disk_alert_enabled: false,
  disk_alert_threshold_mb: 100,
  max_retry: 1,
  retry_interval_sec: 300,
  is_enabled: true,
  description: "",
  custom_range: undefined,
  active_range: undefined,
  github_deploy_enabled: false,
  github_config_id: undefined,
  github_filename_template: "",
  html_backup_enabled: false,
  html_backup_path: "",
  html_backup_filename_template: "",
  html_backup_filename_date_offset_days: 0,
  days_offset: 0,
  message_stats_enabled: false,
  message_stats_formats: ["md"],
  message_stats_path: "",
  message_stats_filename_template: "每日群成员发言数量统计_{YYYY-MM-DD}",
  message_stats_filename_date_offset_days: -1,
  message_stats_github_enabled: false,
  message_stats_github_config_id: undefined,
  message_stats_github_filename_template: "每日群成员发言数量统计_{YYYY-MM-DD}",
  message_stats_github_filename_date_offset_days: 0,
  message_stats_github_root: "xinjian",
  chatlog_backup_enabled: false,
  chatlog_backup_formats: ["txt"],
  chatlog_backup_path: "",
  chatlog_backup_filename_template: "聊天记录_{week_start}_{week_end}",
  chatlog_backup_filename_date_offset_days: 0,
  model_output_backup_enabled: false,
  model_output_path: "",
  model_output_formats: ["md"],
  model_output_filename_template: "模型输出_{YYYY-MM-DD}",
  model_output_filename_date_offset_days: -1,
  topic_text_layout: "per_topic",
  topic_text_merge_threshold: 3,
  topic_image_enabled: false,
  topic_image_layout: "single",
  topic_image_merge_threshold: 3,
  topic_image_backup_enabled: false,
  topic_image_backup_path: "",
  image_prompt_template_id: undefined,
  image_split_enabled: true,
  image_split_prompt: DEFAULT_IMAGE_SPLIT_PROMPT,
  image_aspect_ratio: "auto",
  image_resolution: "auto",
  max_image_count: 12,
  card_renderer: "ai",
  card_font_theme: "A",
  ima_sync_enabled: false,
  ima_use_default_account: true,
  ima_account_id: undefined,
  ima_use_default_target: true,
  ima_target_type: "knowledge_base",
  ima_note_folder_id: undefined,
  ima_knowledge_base_id: undefined,
  ima_knowledge_folder_id: "root",
  weekly_period: "previous_week",
  weekly_start_day: 0,
  weekly_start_time_picker: parseTime("00:00"),
  weekly_end_day: 6,
  weekly_end_time_picker: parseTime("24:00"),
  weekly_report_weekday: 0
};

export const parseDescription = (description?: string | null) => {
  if (!description) {
    return { note: "", range: undefined, activeRange: undefined };
  }
  try {
    const data = JSON.parse(description);
    if (typeof data === "object" && data !== null) {
      const note = typeof data.note === "string" ? data.note : "";
      let range: [Dayjs, Dayjs] | undefined;
      let activeRange: [Dayjs, Dayjs] | undefined;
      if (typeof data.time_range === "string" && data.time_range.includes("~")) {
        const [startRaw, endRaw] = data.time_range.split("~").map((item: string) => item.trim());
        const start = dayjs(startRaw, ["YYYY-MM-DD HH:mm", "YYYY-MM-DD"]);
        const end = dayjs(endRaw, ["YYYY-MM-DD HH:mm", "YYYY-MM-DD"]);
        if (start.isValid() && end.isValid()) {
          range = [start, end];
        }
      }
      if (typeof data.active_range === "string" && data.active_range.includes("~")) {
        const [startRaw, endRaw] = data.active_range.split("~").map((item: string) => item.trim());
        const start = dayjs(startRaw, ["YYYY-MM-DD"]);
        const end = dayjs(endRaw, ["YYYY-MM-DD"]);
        if (start.isValid() && end.isValid()) {
          activeRange = [start, end];
        }
      }
      return { note, range, activeRange };
    }
  } catch (error) {
    // ignore JSON errors
  }
  return { note: description, range: undefined, activeRange: undefined };
};

export const toJobFormValues = (job: Job): JobFormValues => {
  const baseValues: JobFormValues = {
    name: job.name,
    start_time: parseTime(job.start_time),
    end_time: parseTime(job.end_time),
    execution_time: parseTime(job.execution_time || job.start_time),
    date_baseline: (job.date_baseline as "current_day" | "previous_day") ?? "current_day",
    schedule_type: job.schedule_type,
    cron_expression: job.cron_expression ?? undefined,
    weekdays: job.weekdays ?? [],
    offset_minutes: job.offset_minutes,
    interval_enabled: job.interval_enabled,
    interval_minutes: job.interval_minutes ?? 120,
    window_start: parseTime(job.window_start ?? "00:00"),
    window_end: parseTime(job.window_end ?? "24:00"),
    disk_alert_enabled: job.disk_alert_enabled ?? false,
    disk_alert_threshold_mb: Math.max(1, Math.round((job.disk_alert_threshold_bytes ?? 100 * 1024 * 1024) / 1024 / 1024)),
    max_retry: job.max_retry,
    retry_interval_sec: job.retry_interval_sec,
    is_enabled: job.is_enabled,
    description: "",
    custom_range: undefined,
    active_range: undefined,
    github_deploy_enabled: job.github_deploy_enabled ?? false,
    github_config_id: job.github_config_id ?? undefined,
    github_filename_template: job.github_filename_template ?? "",
    html_backup_enabled: job.html_backup_enabled ?? false,
    html_backup_path: job.html_backup_path ?? "",
    html_backup_filename_template: job.html_backup_filename_template ?? "",
    html_backup_filename_date_offset_days: job.html_backup_filename_date_offset_days ?? -1,
    days_offset: job.days_offset ?? 0,
    message_stats_enabled: job.message_stats_enabled ?? false,
    message_stats_formats: job.message_stats_formats ?? ["md"],
    message_stats_path: job.message_stats_path ?? "",
    message_stats_filename_template: job.message_stats_filename_template ?? "每日群成员发言数量统计_{YYYY-MM-DD}",
    message_stats_filename_date_offset_days: job.message_stats_filename_date_offset_days ?? -1,
    message_stats_github_enabled: job.message_stats_github_enabled ?? false,
    message_stats_github_config_id: job.message_stats_github_config_id ?? undefined,
    message_stats_github_filename_template:
      job.message_stats_github_filename_template ?? "每日群成员发言数量统计_{YYYY-MM-DD}",
    message_stats_github_filename_date_offset_days: job.message_stats_github_filename_date_offset_days ?? 0,
    message_stats_github_root: job.message_stats_github_root ?? "xinjian",
    chatlog_backup_enabled: job.chatlog_backup_enabled ?? false,
    chatlog_backup_formats: (job.chatlog_backup_formats as ("md" | "txt")[]) ?? ["txt"],
    chatlog_backup_path: job.chatlog_backup_path ?? "",
    chatlog_backup_filename_template: job.chatlog_backup_filename_template ?? "聊天记录_{week_start}_{week_end}",
    chatlog_backup_filename_date_offset_days: job.chatlog_backup_filename_date_offset_days ?? 0,
    model_output_backup_enabled: job.model_output_backup_enabled ?? false,
    model_output_path: job.model_output_path ?? "",
    model_output_formats: (job.model_output_formats as ("md" | "txt")[]) ?? ["md"],
    model_output_filename_template: job.model_output_filename_template ?? "模型输出_{YYYY-MM-DD}",
    model_output_filename_date_offset_days: job.model_output_filename_date_offset_days ?? -1,
    topic_text_layout: job.topic_text_layout ?? "per_topic",
    topic_text_merge_threshold: job.topic_text_merge_threshold ?? 3,
    topic_image_enabled: job.topic_image_enabled ?? false,
    topic_image_layout: job.topic_image_layout ?? "single",
    topic_image_merge_threshold: job.topic_image_merge_threshold ?? 3,
    topic_image_backup_enabled: job.topic_image_backup_enabled ?? false,
    topic_image_backup_path: job.topic_image_backup_path ?? "",
    image_prompt_template_id: job.image_prompt_template_id ?? undefined,
    image_split_enabled: job.image_split_enabled ?? true,
    image_split_prompt: normalizeImageSplitPrompt(job.image_split_prompt),
    image_aspect_ratio: job.image_aspect_ratio ?? "auto",
    image_resolution: job.image_resolution ?? "auto",
    max_image_count: job.max_image_count ?? 12,
    card_renderer: (job.card_renderer as "ai" | "local") ?? "ai",
    card_font_theme: (job.card_font_theme as "A" | "B" | "C") ?? "A",
    ima_sync_enabled: job.ima_sync_enabled ?? false,
    ima_use_default_account: job.ima_use_default_account ?? true,
    ima_account_id: job.ima_account_id ?? undefined,
    ima_use_default_target: job.ima_use_default_target ?? true,
    ima_target_type: (job.ima_target_type as "note" | "knowledge_base") ?? "knowledge_base",
    ima_note_folder_id: job.ima_note_folder_id ?? undefined,
    ima_knowledge_base_id: job.ima_knowledge_base_id ?? undefined,
    ima_knowledge_folder_id: job.ima_knowledge_folder_id ?? "root",
    weekly_period: (job.weekly_period as "previous_week" | "current_week") ?? "previous_week",
    weekly_start_day: job.weekly_start_day ?? 0,
    weekly_start_time_picker: parseTime(job.weekly_start_time ?? "00:00"),
    weekly_end_day: job.weekly_end_day ?? 6,
    weekly_end_time_picker: parseTime(job.weekly_end_time ?? "24:00"),
    weekly_report_weekday: job.weekdays && job.weekdays.length ? job.weekdays[0] : 0
  };
  const parsed = parseDescription(job.description);
  baseValues.description = parsed.note;
  baseValues.custom_range = parsed.range;
  baseValues.active_range = parsed.activeRange;
  return baseValues;
};
