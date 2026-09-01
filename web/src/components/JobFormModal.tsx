import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AutoComplete,
  Button,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Menu,
  Modal,
  Popover,
  Radio,
  Select,
  Space,
  Switch,
  Tooltip,
  Typography,
  message
} from "antd";
import type { MenuProps } from "antd";
import dayjs from "dayjs";
import type { Dayjs } from "dayjs";
import type { Job, JobPayload, Task } from "../services/tasks";
import type { PromptTemplate } from "../services/promptTemplates";
import {
  DEFAULT_IMAGE_SPLIT_PROMPT,
  fetchPromptTemplates,
  normalizeImageSplitPrompt
} from "../services/promptTemplates";
import type { GithubConfig, GithubConfigPayload } from "../services/githubConfigs";
import { fetchGithubConfigs, createGithubConfig } from "../services/githubConfigs";
import {
  fetchImaAccounts,
  fetchImaKnowledgeBases,
  fetchImaKnowledgeFolders,
  fetchImaNoteFolders,
  type ImaAccount,
  type ImaOption
} from "../services/ima";
import GithubConfigFormModal from "./GithubConfigFormModal";
import { CheckCircleFilled, QuestionCircleOutlined, ReloadOutlined, SwapOutlined } from "@ant-design/icons";

type JobFormValues = {
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
  image_aspect_ratio: "auto" | "1:1" | "3:2" | "2:3" | "9:16";
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

type JobFormModalProps = {
  open: boolean;
  initialValues?: Job | null;
  taskType?: Task["task_type"];
  confirmLoading?: boolean;
  onCancel: () => void;
  onSubmit: (values: JobPayload) => void | Promise<void>;
};

const TIME_BASE = "2020-01-01";
const defaultStart = dayjs(`${TIME_BASE} 09:00`);
const defaultEnd = dayjs(`${TIME_BASE} 18:00`);
const VIEW_STORAGE_KEY = "job_form_view_mode";

type ViewMode = "classic" | "split";
type SectionKey =
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

type TimeSelectInputProps = {
  value?: Dayjs;
  onChange?: (value: Dayjs) => void;
  minuteStep?: number;
  placeholder?: string;
  style?: React.CSSProperties;
};

const parseTime = (value: string) => {
  if (value === "24:00") {
    return dayjs(`${TIME_BASE} 00:00`).add(1, "day");
  }
  return dayjs(`${TIME_BASE} ${value}`);
};

const formatTime = (value: Dayjs) => {
  if (!value) {
    return "00:00";
  }
  const base = dayjs(TIME_BASE);
  const isTwentyFour =
    value.format("HH:mm") === "00:00" && value.isSame(base.add(1, "day"), "day");
  if (isTwentyFour) {
    return "24:00";
  }
  return value.format("HH:mm");
};

const formatTimeValue = (value?: Dayjs) => (value ? formatTime(value) : "");

const buildTimeOptions = (minuteStep: number) => {
  const options: { value: string }[] = [];
  for (let minutes = 0; minutes < 24 * 60; minutes += minuteStep) {
    const hour = Math.floor(minutes / 60);
    const minute = minutes % 60;
    options.push({
      value: `${hour.toString().padStart(2, "0")}:${minute.toString().padStart(2, "0")}`
    });
  }
  options.push({ value: "24:00" });
  return options;
};

const normalizeTimeText = (value: string) => {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const match = /^(\d{1,2}):(\d{1,2})$/.exec(trimmed);
  if (!match) {
    return null;
  }
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (hour === 24 && minute === 0) {
    return parseTime("24:00");
  }
  if (hour >= 0 && hour < 24 && minute >= 0 && minute < 60) {
    const normalized = `${hour.toString().padStart(2, "0")}:${minute.toString().padStart(2, "0")}`;
    return parseTime(normalized);
  }
  return null;
};

const TimeSelectInput = ({ value, onChange, minuteStep = 5, placeholder, style }: TimeSelectInputProps) => {
  const [draft, setDraft] = useState(() => formatTimeValue(value));
  const [open, setOpen] = useState(false);
  const options = useMemo(() => buildTimeOptions(minuteStep), [minuteStep]);

  useEffect(() => {
    setDraft(formatTimeValue(value));
  }, [value]);

  const commitValue = (next: string) => {
    const parsed = normalizeTimeText(next);
    if (parsed) {
      onChange?.(parsed);
    }
    return parsed;
  };

  return (
    <AutoComplete
      open={open}
      value={draft}
      options={options}
      placeholder={placeholder}
      style={style}
      filterOption={(input, option) => (option?.value ?? "").includes(input)}
      onFocus={() => setOpen(true)}
      onChange={(next) => {
        setDraft(next);
        setOpen(true);
        commitValue(next);
      }}
      onSelect={(next) => {
        const parsed = commitValue(next);
        if (parsed) {
          setDraft(formatTime(parsed));
        }
        setOpen(false);
      }}
      onBlur={() => {
        const parsed = normalizeTimeText(draft);
        if (parsed) {
          onChange?.(parsed);
          setDraft(formatTime(parsed));
        } else {
          setDraft(formatTimeValue(value));
        }
        setOpen(false);
      }}
    />
  );
};

const { Text } = Typography;

const getTemplateTooltip = () => (
  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
    <div>
      1. 执行完成时间参数：<code>{`{YYYY-MM-DD}`}</code>（执行完成日） <code>{`{YYYY-MM-DD HH:MM}`}</code>{" "}
      <code>{`{YYYYMMDD}`}</code> <code>{`{YYYYMMDD_HHmmss}`}</code>
    </div>
    <div>
      2. 仅周报模式参数：<code>{`{week_start}`}</code>/<code>{`{week_end}`}</code>（聊天记录窗口起止日期，北京时间）；
      <br />
      周报模式下群消息统计文件名会自动使用 <code>{`{week_start}_{week_end}`}</code>，无需额外设置日期偏移
    </div>
    <div>
      3. 任务/作业参数：<code>{`{task_name}`}</code> <code>{`{job_name}`}</code> <code>{`{task_id}`}</code>{" "}
      <code>{`{job_id}`}</code> <code>{`{execution_id}`}</code>
    </div>
  </div>
);

const getMessageStatsGithubTooltip = () => (
  <div style={{ display: "flex", flexDirection: "column", gap: 4, maxWidth: 360 }}>
    <div>开启后会将群消息统计同步到指定 GitHub 仓库，并按年月自动归档。</div>
    <div>
      归档路径：<code>{`{根目录}/{YYYY}年/{YY}年{M}月消息统计/{文件名}.md`}</code>
    </div>
    <div>
      文件名来自“GitHub_消息统计文件名模板”，系统会用执行完成时间（+日期偏移）替换{" "}
      <code>{`{YYYY-MM-DD}`}</code> 等占位符。
    </div>
    <div>目录不存在会自动创建（提交到 GitHub 时自动生成）。</div>
    <div>
      示例：根目录 <code>xinjian</code>，模板 <code>每日群成员发言数量统计_{`{YYYY-MM-DD}`}</code>，日期 2027-01-27 →
      <br />
      <code>xinjian/2027年/27年1月消息统计/每日群成员发言数量统计_2027-01-27.md</code>
    </div>
    <div>
      注意：不会解析已有文件名中的日期，若需日期请在模板中保留 <code>{`{YYYY-MM-DD}`}</code>。
    </div>
  </div>
);

const renderTemplateExample = (example: string) => (
  <Space direction="vertical" size={2}>
    <Text type="secondary">{example}</Text>
  </Space>
);

const defaultFormValues: JobFormValues = {
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
  max_image_count: 6,
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

const ROOT_IMA_KNOWLEDGE_FOLDER_OPTION: ImaOption = { label: "根目录", value: "root" };

const buildDisplayImaKnowledgeFolderOption = (
  folderId?: string | null,
  folderName?: string | null
): ImaOption | null => {
  const normalizedId = (folderId ?? "").trim();
  if (!normalizedId || normalizedId === ROOT_IMA_KNOWLEDGE_FOLDER_OPTION.value) {
    return null;
  }
  const normalizedLabel = (folderName ?? "").trim();
  return {
    value: normalizedId,
    label: normalizedLabel || normalizedId
  };
};

const mergeImaKnowledgeFolderOptions = (list: ImaOption[], fallbackOption?: ImaOption | null): ImaOption[] => {
  const order: string[] = [];
  const optionMap = new Map<string, ImaOption>();
  const pushOption = (option?: ImaOption | null) => {
    if (!option?.value) {
      return;
    }
    if (!optionMap.has(option.value)) {
      order.push(option.value);
    }
    optionMap.set(option.value, option);
  };
  pushOption(ROOT_IMA_KNOWLEDGE_FOLDER_OPTION);
  pushOption(fallbackOption);
  list.forEach((item) => pushOption(item));
  return order.map((value) => optionMap.get(value)!);
};

const scheduleOptions = [
  { label: "每日执行", value: "daily" },
  { label: "工作日执行", value: "weekday" },
  { label: "周末执行", value: "weekend" },
  { label: "自定义周几", value: "weekly" },
  { label: "手动执行", value: "manual" },
  { label: "周报模式", value: "weekly_report" },
  { label: "自定义 Cron", value: "custom_cron" }
];

const weekdayOptions = [
  { label: "周一", value: 0 },
  { label: "周二", value: 1 },
  { label: "周三", value: 2 },
  { label: "周四", value: 3 },
  { label: "周五", value: 4 },
  { label: "周六", value: 5 },
  { label: "周日", value: 6 }
];

const parseDescription = (description?: string | null) => {
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

const toJobFormValues = (job: Job): JobFormValues => {
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
    max_image_count: job.max_image_count ?? 6,
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

function JobFormModal({ open, initialValues, taskType, confirmLoading, onCancel, onSubmit }: JobFormModalProps) {
  const [form] = Form.useForm<JobFormValues>();
  const title = useMemo(() => (initialValues ? "编辑作业" : "新增作业"), [initialValues]);
  const [viewMode, setViewMode] = useState<ViewMode>(() => {
    if (typeof window === "undefined") {
      return "classic";
    }
    const stored = window.localStorage.getItem(VIEW_STORAGE_KEY);
    return stored === "split" ? "split" : "classic";
  });
  const [activeSection, setActiveSection] = useState<SectionKey>("basic");
  const intervalEnabled = Form.useWatch("interval_enabled", form);
  const scheduleTypeValue = Form.useWatch("schedule_type", form);
  const githubDeployEnabled = Form.useWatch("github_deploy_enabled", form);
  const htmlBackupEnabled = Form.useWatch("html_backup_enabled", form);
  const messageStatsEnabled = Form.useWatch("message_stats_enabled", form);
  const messageStatsGithubEnabled = Form.useWatch("message_stats_github_enabled", form);
  const chatlogBackupEnabled = Form.useWatch("chatlog_backup_enabled", form);
  const modelOutputBackupEnabled = Form.useWatch("model_output_backup_enabled", form);
  const topicImageEnabled = Form.useWatch("topic_image_enabled", form);
  const topicImageBackupEnabled = Form.useWatch("topic_image_backup_enabled", form);
  const topicTextLayout = Form.useWatch("topic_text_layout", form);
  const topicImageLayout = Form.useWatch("topic_image_layout", form);
  const imageSplitEnabled = Form.useWatch("image_split_enabled", form);
  const imaSyncEnabled = Form.useWatch("ima_sync_enabled", form);
  const imaUseDefaultAccount = Form.useWatch("ima_use_default_account", form);
  const imaAccountId = Form.useWatch("ima_account_id", form);
  const imaUseDefaultTarget = Form.useWatch("ima_use_default_target", form);
  const imaTargetType = Form.useWatch("ima_target_type", form);
  const imaKnowledgeBaseId = Form.useWatch("ima_knowledge_base_id", form);
  const isWeeklyReport = scheduleTypeValue === "weekly_report";
  const isManual = scheduleTypeValue === "manual";
  const messageStatsGithubActiveView = messageStatsEnabled && messageStatsGithubEnabled;
  const htmlBackupActiveView = Boolean(htmlBackupEnabled);
  const imaTargetActiveView = modelOutputBackupEnabled && imaSyncEnabled;
  const isTopicCardTask = taskType === "topic_card";
  const isImageCardTask = taskType === "image_card";
  const [githubConfigs, setGithubConfigs] = useState<GithubConfig[]>([]);
  const [configModalOpen, setConfigModalOpen] = useState(false);
  const [configTarget, setConfigTarget] = useState<"deploy" | "message_stats">("deploy");
  const [configModalLoading, setConfigModalLoading] = useState(false);
  const [imaAccounts, setImaAccounts] = useState<ImaAccount[]>([]);
  const [imaNoteFolders, setImaNoteFolders] = useState<ImaOption[]>([]);
  const [imaKnowledgeBases, setImaKnowledgeBases] = useState<ImaOption[]>([]);
  const [imaKnowledgeFolders, setImaKnowledgeFolders] = useState<ImaOption[]>([ROOT_IMA_KNOWLEDGE_FOLDER_OPTION]);
  const [imagePromptTemplates, setImagePromptTemplates] = useState<PromptTemplate[]>([]);
  const [imagePromptTemplatesLoading, setImagePromptTemplatesLoading] = useState(false);
  const [imaLoading, setImaLoading] = useState({
    noteFolders: false,
    knowledgeBases: false,
    knowledgeFolders: false
  });
  const githubConfigOptions = useMemo(
    () =>
      githubConfigs.map((config) => ({
        label: `${config.name}（${config.owner}/${config.repo}）`,
        value: config.id
      })),
    [githubConfigs]
  );
  const defaultImaAccountId = useMemo(() => imaAccounts.find((item) => item.is_default)?.id, [imaAccounts]);
  const effectiveImaAccountId = imaUseDefaultAccount ? defaultImaAccountId : imaAccountId;
  const imaAccountOptions = useMemo(
    () =>
      imaAccounts.map((account) => ({
        label: account.name + (account.is_default ? "（默认）" : ""),
        value: account.id
      })),
    [imaAccounts]
  );
  const imaNoteFolderOptions = useMemo(() => imaNoteFolders, [imaNoteFolders]);
  const imaKnowledgeBaseOptions = useMemo(() => imaKnowledgeBases, [imaKnowledgeBases]);
  const imaKnowledgeFolderOptions = useMemo(
    () => (imaKnowledgeFolders.length ? imaKnowledgeFolders : [ROOT_IMA_KNOWLEDGE_FOLDER_OPTION]),
    [imaKnowledgeFolders]
  );
  const imagePromptTemplateOptions = useMemo(
    () => imagePromptTemplates.map((template) => ({ label: template.name, value: template.id })),
    [imagePromptTemplates]
  );

  const setTimeField = (field: "start_time" | "end_time" | "execution_time", time: Dayjs) => {
    form.setFieldsValue({ [field]: time });
  };

  const loadGithubConfigs = useCallback(async () => {
    try {
      const list = await fetchGithubConfigs();
      setGithubConfigs(list);
    } catch (error) {
      console.error("failed to load github configs", error);
    }
  }, []);

  const loadImagePromptTemplates = useCallback(async () => {
    setImagePromptTemplatesLoading(true);
    try {
      const list = await fetchPromptTemplates();
      setImagePromptTemplates(
        list.filter((template) => (template.template_type ?? "regular") === "image")
      );
    } catch (error) {
      console.error("failed to load image prompt templates", error);
      setImagePromptTemplates([]);
    } finally {
      setImagePromptTemplatesLoading(false);
    }
  }, []);

  const loadImaAccounts = useCallback(async () => {
    try {
      const list = await fetchImaAccounts();
      setImaAccounts(list);
    } catch (error) {
      console.error("failed to load ima accounts", error);
    }
  }, []);

  const loadImaNoteFolders = useCallback(async (accountId?: number) => {
    if (!accountId) {
      setImaNoteFolders([]);
      return;
    }
    try {
      setImaLoading((prev) => ({ ...prev, noteFolders: true }));
      const list = await fetchImaNoteFolders(accountId);
      setImaNoteFolders(list);
    } catch (error) {
      console.error("failed to load ima note folders", error);
    } finally {
      setImaLoading((prev) => ({ ...prev, noteFolders: false }));
    }
  }, []);

  const loadImaKnowledgeBases = useCallback(async (accountId?: number) => {
    if (!accountId) {
      setImaKnowledgeBases([]);
      return;
    }
    try {
      setImaLoading((prev) => ({ ...prev, knowledgeBases: true }));
      const list = await fetchImaKnowledgeBases(accountId);
      setImaKnowledgeBases(list);
    } catch (error) {
      console.error("failed to load ima knowledge bases", error);
    } finally {
      setImaLoading((prev) => ({ ...prev, knowledgeBases: false }));
    }
  }, []);

  const loadImaKnowledgeFolders = useCallback(async (knowledgeBaseId?: string, accountId?: number) => {
    if (!knowledgeBaseId || !accountId) {
      setImaKnowledgeFolders((prev) =>
        mergeImaKnowledgeFolderOptions(
          [],
          prev.find((item) => item.value === form.getFieldValue("ima_knowledge_folder_id"))
        )
      );
      return;
    }
    try {
      setImaLoading((prev) => ({ ...prev, knowledgeFolders: true }));
      const list = await fetchImaKnowledgeFolders(knowledgeBaseId, accountId);
      setImaKnowledgeFolders((prev) => {
        const selectedValue = form.getFieldValue("ima_knowledge_folder_id");
        const selectedFallback =
          selectedValue && selectedValue !== ROOT_IMA_KNOWLEDGE_FOLDER_OPTION.value
            ? prev.find((item) => item.value === selectedValue) ??
              buildDisplayImaKnowledgeFolderOption(selectedValue, selectedValue)
            : null;
        return mergeImaKnowledgeFolderOptions(list, selectedFallback);
      });
    } catch (error) {
      console.error("failed to load ima knowledge folders", error);
      setImaKnowledgeFolders((prev) =>
        mergeImaKnowledgeFolderOptions(
          [],
          prev.find((item) => item.value === form.getFieldValue("ima_knowledge_folder_id"))
        )
      );
    } finally {
      setImaLoading((prev) => ({ ...prev, knowledgeFolders: false }));
    }
  }, [form]);

  const handleInlineConfigSubmit = useCallback(
    async (values: GithubConfigPayload) => {
      try {
        setConfigModalLoading(true);
        const created = await createGithubConfig(values);
        message.success("GitHub 配置已创建");
        await loadGithubConfigs();
        if (configTarget === "message_stats") {
          form.setFieldsValue({
            message_stats_github_config_id: created.id,
            message_stats_github_enabled: true
          });
        } else {
          form.setFieldsValue({ github_config_id: created.id, github_deploy_enabled: true });
        }
        setConfigModalOpen(false);
      } catch (error) {
        const err = error as Error;
        message.error(err.message || "创建 GitHub 配置失败");
      } finally {
        setConfigModalLoading(false);
      }
    },
    [form, loadGithubConfigs, configTarget]
  );

  useEffect(() => {
    if (!open) {
      return;
    }
    setActiveSection("basic");
    const nextValues = initialValues ? toJobFormValues(initialValues) : defaultFormValues;
    form.resetFields();
    form.setFieldsValue(nextValues);
    setImaKnowledgeFolders(
      mergeImaKnowledgeFolderOptions(
        [],
        buildDisplayImaKnowledgeFolderOption(initialValues?.ima_knowledge_folder_id, initialValues?.ima_knowledge_folder_name)
      )
    );
    void loadGithubConfigs();
    void loadImaAccounts();
    if (isImageCardTask) {
      void loadImagePromptTemplates();
    } else {
      setImagePromptTemplates([]);
    }
    const nextAccountId = nextValues.ima_use_default_account ? defaultImaAccountId : nextValues.ima_account_id;
    if (nextAccountId) {
      void loadImaNoteFolders(nextAccountId);
      void loadImaKnowledgeBases(nextAccountId);
    } else {
      setImaNoteFolders([]);
      setImaKnowledgeBases([]);
      const currentFolderValue = form.getFieldValue("ima_knowledge_folder_id");
      setImaKnowledgeFolders((prev) =>
        mergeImaKnowledgeFolderOptions([], prev.find((item) => item.value === currentFolderValue))
      );
    }
    if (nextValues.ima_knowledge_base_id && nextAccountId) {
      void loadImaKnowledgeFolders(nextValues.ima_knowledge_base_id, nextAccountId);
    } else {
      const currentFolderValue = form.getFieldValue("ima_knowledge_folder_id");
      setImaKnowledgeFolders((prev) =>
        mergeImaKnowledgeFolderOptions([], prev.find((item) => item.value === currentFolderValue))
      );
    }
  }, [open, initialValues, form, loadGithubConfigs, loadImaAccounts, loadImaKnowledgeBases, loadImaKnowledgeFolders, loadImaNoteFolders, defaultImaAccountId, isImageCardTask, loadImagePromptTemplates]);

  useEffect(() => {
    if (!open || !imaSyncEnabled) {
      return;
    }
    if (!effectiveImaAccountId) {
      setImaNoteFolders([]);
      setImaKnowledgeBases([]);
      const currentFolderValue = form.getFieldValue("ima_knowledge_folder_id");
      setImaKnowledgeFolders((prev) =>
        mergeImaKnowledgeFolderOptions([], prev.find((item) => item.value === currentFolderValue))
      );
      return;
    }
    void loadImaNoteFolders(effectiveImaAccountId);
    void loadImaKnowledgeBases(effectiveImaAccountId);
    if (imaKnowledgeBaseId) {
      void loadImaKnowledgeFolders(imaKnowledgeBaseId, effectiveImaAccountId);
    } else {
      const currentFolderValue = form.getFieldValue("ima_knowledge_folder_id");
      setImaKnowledgeFolders((prev) =>
        mergeImaKnowledgeFolderOptions([], prev.find((item) => item.value === currentFolderValue))
      );
    }
  }, [open, imaSyncEnabled, effectiveImaAccountId, imaKnowledgeBaseId, loadImaKnowledgeBases, loadImaKnowledgeFolders, loadImaNoteFolders]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(VIEW_STORAGE_KEY, viewMode);
  }, [viewMode]);

  useEffect(() => {
    if (
      (scheduleTypeValue === "weekly_report" || scheduleTypeValue === "manual") &&
      form.getFieldValue("interval_enabled")
    ) {
      form.setFieldsValue({ interval_enabled: false });
    }
  }, [scheduleTypeValue, form]);

  useEffect(() => {
    if (!githubDeployEnabled) {
      form.setFieldsValue({ github_config_id: undefined });
    }
  }, [githubDeployEnabled, form]);

  useEffect(() => {
    if (!messageStatsEnabled) {
      form.setFieldsValue({ message_stats_github_enabled: false, message_stats_github_config_id: undefined });
    }
  }, [messageStatsEnabled, form]);

  useEffect(() => {
    if (!messageStatsGithubEnabled) {
      form.setFieldsValue({ message_stats_github_config_id: undefined });
    }
  }, [messageStatsGithubEnabled, form]);

  useEffect(() => {
    if (!modelOutputBackupEnabled) {
      form.setFieldsValue({
        ima_sync_enabled: false,
        ima_use_default_target: true,
        ima_target_type: "knowledge_base",
        ima_note_folder_id: undefined,
        ima_knowledge_base_id: undefined,
        ima_knowledge_folder_id: "root"
      });
    }
  }, [modelOutputBackupEnabled, form]);

  useEffect(() => {
    if (!imaSyncEnabled) {
      form.setFieldsValue({
        ima_use_default_target: true,
        ima_target_type: "knowledge_base",
        ima_note_folder_id: undefined,
        ima_knowledge_base_id: undefined,
        ima_knowledge_folder_id: "root"
      });
    }
  }, [imaSyncEnabled, form]);

  useEffect(() => {
    if (imaUseDefaultTarget) {
      form.setFieldsValue({
        ima_target_type: "knowledge_base",
        ima_note_folder_id: undefined,
        ima_knowledge_base_id: undefined,
        ima_knowledge_folder_id: "root"
      });
    }
  }, [imaUseDefaultTarget, form]);

  useEffect(() => {
    if (imaTargetType === "note") {
      form.setFieldsValue({
        ima_knowledge_base_id: undefined,
        ima_knowledge_folder_id: "root"
      });
    } else {
      form.setFieldsValue({ ima_note_folder_id: undefined });
    }
  }, [imaTargetType, form]);

  useEffect(() => {
    if (!imaKnowledgeBaseId || !effectiveImaAccountId) {
      const currentValue = form.getFieldValue("ima_knowledge_folder_id");
      setImaKnowledgeFolders((prev) =>
        mergeImaKnowledgeFolderOptions([], prev.find((item) => item.value === currentValue))
      );
      if (!currentValue) {
        form.setFieldValue("ima_knowledge_folder_id", "root");
      }
      return;
    }
    void loadImaKnowledgeFolders(imaKnowledgeBaseId, effectiveImaAccountId);
  }, [imaKnowledgeBaseId, effectiveImaAccountId, form, loadImaKnowledgeFolders]);

  const handleFinish = (values: JobFormValues) => {
    const descriptionPayload: Record<string, unknown> = {};
    if (values.description?.trim()) {
      descriptionPayload.note = values.description.trim();
    }
    if (values.custom_range && values.custom_range.length === 2) {
      descriptionPayload.time_range = `${values.custom_range[0].format("YYYY-MM-DD HH:mm")}~${values.custom_range[1].format("YYYY-MM-DD HH:mm")}`;
    }
    if (values.active_range && values.active_range.length === 2) {
      descriptionPayload.active_range = `${values.active_range[0].format("YYYY-MM-DD")}~${values.active_range[1].format("YYYY-MM-DD")}`;
    }

    const windowStart = values.window_start ?? parseTime("00:00");
    const windowEnd = values.window_end ?? parseTime("24:00");
    const weekdaysPayload =
      values.schedule_type === "weekly"
        ? values.weekdays ?? []
        : values.schedule_type === "weekly_report"
        ? [values.weekly_report_weekday ?? 0]
        : undefined;
    const weeklyStartTime = values.weekly_start_time_picker ?? parseTime("00:00");
    const weeklyEndTime = values.weekly_end_time_picker ?? parseTime("24:00");
    const githubEnabled = values.github_deploy_enabled;
    const isWeeklyReportPayload = values.schedule_type === "weekly_report";
    const htmlBackupActive = Boolean(values.html_backup_enabled);
    const messageStatsGithubActive = values.message_stats_enabled ? values.message_stats_github_enabled : false;
    const imaSyncActive = values.model_output_backup_enabled ? values.ima_sync_enabled : false;
    const effectiveSubmitAccountId = values.ima_use_default_account ? defaultImaAccountId : values.ima_account_id;
    const selectedImaNoteFolder = imaNoteFolderOptions.find((item) => item.value === values.ima_note_folder_id);
    const selectedImaKnowledgeBase = imaKnowledgeBaseOptions.find((item) => item.value === values.ima_knowledge_base_id);
    const selectedImaKnowledgeFolder = imaKnowledgeFolderOptions.find((item) => item.value === values.ima_knowledge_folder_id);
    const payload: JobPayload = {
      name: values.name.trim(),
      start_time: formatTime(values.start_time),
      end_time: formatTime(values.end_time),
      execution_time: formatTime(values.execution_time || values.start_time),
      date_baseline: values.date_baseline,
      schedule_type: values.schedule_type,
      cron_expression: values.schedule_type === "custom_cron" ? values.cron_expression ?? "" : null,
      weekdays: weekdaysPayload,
      offset_minutes: values.offset_minutes,
      interval_enabled: values.interval_enabled,
      interval_minutes: values.interval_enabled ? values.interval_minutes ?? 120 : null,
      window_start: formatTime(windowStart),
      window_end: formatTime(windowEnd),
      disk_alert_enabled: values.disk_alert_enabled,
      disk_alert_threshold_bytes: Math.round((values.disk_alert_threshold_mb ?? 100) * 1024 * 1024),
      max_retry: values.max_retry,
      retry_interval_sec: values.retry_interval_sec,
      is_enabled: values.is_enabled,
      description: Object.keys(descriptionPayload).length ? JSON.stringify(descriptionPayload) : null,
      github_deploy_enabled: githubEnabled,
      github_config_id: githubEnabled ? values.github_config_id ?? null : null,
      github_filename_template: githubEnabled ? values.github_filename_template?.trim() || undefined : undefined,
      html_backup_enabled: htmlBackupActive,
      html_backup_path: htmlBackupActive ? values.html_backup_path?.trim() || undefined : undefined,
      html_backup_filename_template: htmlBackupActive
        ? values.html_backup_filename_template?.trim() || undefined
        : undefined,
      html_backup_filename_date_offset_days: htmlBackupActive
        ? (isWeeklyReportPayload ? 0 : values.html_backup_filename_date_offset_days ?? 0)
        : undefined,
      days_offset: isWeeklyReportPayload ? 0 : values.days_offset ?? 0,
      message_stats_enabled: values.message_stats_enabled,
      message_stats_formats: values.message_stats_enabled ? values.message_stats_formats ?? ["md"] : undefined,
      message_stats_path: values.message_stats_enabled ? values.message_stats_path?.trim() || undefined : undefined,
      message_stats_filename_template: values.message_stats_enabled
        ? values.message_stats_filename_template?.trim() || "每日群成员发言数量统计_{YYYY-MM-DD}"
        : undefined,
      message_stats_filename_date_offset_days: values.message_stats_enabled
        ? (isWeeklyReportPayload ? 0 : values.message_stats_filename_date_offset_days ?? 0)
        : undefined,
      message_stats_github_enabled: messageStatsGithubActive,
      message_stats_github_config_id: messageStatsGithubActive ? values.message_stats_github_config_id ?? null : null,
      message_stats_github_filename_template: messageStatsGithubActive
        ? values.message_stats_github_filename_template?.trim() || "每日群成员发言数量统计_{YYYY-MM-DD}"
        : undefined,
      message_stats_github_filename_date_offset_days: messageStatsGithubActive
        ? (isWeeklyReportPayload ? 0 : values.message_stats_github_filename_date_offset_days ?? 0)
        : undefined,
      message_stats_github_root: messageStatsGithubActive ? values.message_stats_github_root?.trim() || "xinjian" : undefined,
      chatlog_backup_enabled: values.chatlog_backup_enabled,
      chatlog_backup_formats: values.chatlog_backup_enabled ? values.chatlog_backup_formats ?? ["txt"] : undefined,
      chatlog_backup_path: values.chatlog_backup_enabled ? values.chatlog_backup_path?.trim() || undefined : undefined,
      chatlog_backup_filename_template: values.chatlog_backup_enabled
        ? values.chatlog_backup_filename_template?.trim() || "聊天记录_{week_start}_{week_end}"
        : undefined,
      chatlog_backup_filename_date_offset_days: values.chatlog_backup_enabled
        ? values.chatlog_backup_filename_date_offset_days ?? 0
        : undefined,
      model_output_backup_enabled: values.model_output_backup_enabled,
      model_output_path: values.model_output_backup_enabled ? values.model_output_path?.trim() || undefined : undefined,
      model_output_formats: values.model_output_backup_enabled ? values.model_output_formats ?? ["md"] : undefined,
      model_output_filename_template: values.model_output_backup_enabled
        ? values.model_output_filename_template?.trim() || "模型输出_{YYYY-MM-DD}"
        : undefined,
      model_output_filename_date_offset_days: values.model_output_backup_enabled
        ? (isWeeklyReportPayload ? 0 : values.model_output_filename_date_offset_days ?? 0)
        : undefined,
      topic_text_layout: isTopicCardTask ? values.topic_text_layout ?? "per_topic" : "per_topic",
      topic_text_merge_threshold: isTopicCardTask ? values.topic_text_merge_threshold ?? 3 : 3,
      topic_image_enabled: isTopicCardTask ? values.topic_image_enabled : false,
      topic_image_layout: isTopicCardTask && values.topic_image_enabled ? values.topic_image_layout ?? "single" : "single",
      topic_image_merge_threshold:
        isTopicCardTask && values.topic_image_enabled ? values.topic_image_merge_threshold ?? 3 : 3,
      topic_image_backup_enabled: isTopicCardTask && values.topic_image_enabled ? values.topic_image_backup_enabled : false,
      topic_image_backup_path:
        isTopicCardTask && values.topic_image_enabled && values.topic_image_backup_enabled
          ? values.topic_image_backup_path?.trim() || undefined
          : undefined,
      image_prompt_template_id: isImageCardTask ? values.image_prompt_template_id ?? null : null,
      image_split_enabled: isImageCardTask ? values.image_split_enabled : false,
      image_split_prompt:
        isImageCardTask && values.image_split_enabled ? values.image_split_prompt?.trim() || DEFAULT_IMAGE_SPLIT_PROMPT : null,
      image_aspect_ratio: isImageCardTask ? values.image_aspect_ratio ?? "auto" : "auto",
      image_resolution: isImageCardTask ? values.image_resolution ?? "auto" : "auto",
      max_image_count: isImageCardTask ? values.max_image_count ?? 6 : 6,
      ima_sync_enabled: imaSyncActive,
      ima_use_default_account: imaSyncActive ? values.ima_use_default_account : true,
      ima_account_id: imaSyncActive && !values.ima_use_default_account ? values.ima_account_id ?? null : null,
      ima_use_default_target: imaSyncActive ? values.ima_use_default_target : true,
      ima_target_type:
        imaSyncActive && effectiveSubmitAccountId && !values.ima_use_default_target ? values.ima_target_type : undefined,
      ima_note_folder_id:
        imaSyncActive && effectiveSubmitAccountId && !values.ima_use_default_target && values.ima_target_type === "note"
          ? values.ima_note_folder_id ?? null
          : null,
      ima_note_folder_name:
        imaSyncActive && effectiveSubmitAccountId && !values.ima_use_default_target && values.ima_target_type === "note"
          ? selectedImaNoteFolder?.label ?? ""
          : undefined,
      ima_knowledge_base_id:
        imaSyncActive &&
        effectiveSubmitAccountId &&
        !values.ima_use_default_target &&
        values.ima_target_type === "knowledge_base"
          ? values.ima_knowledge_base_id ?? null
          : null,
      ima_knowledge_base_name:
        imaSyncActive &&
        effectiveSubmitAccountId &&
        !values.ima_use_default_target &&
        values.ima_target_type === "knowledge_base"
          ? selectedImaKnowledgeBase?.label ?? ""
          : undefined,
      ima_knowledge_folder_id:
        imaSyncActive &&
        effectiveSubmitAccountId &&
        !values.ima_use_default_target &&
        values.ima_target_type === "knowledge_base"
          ? values.ima_knowledge_folder_id === "root"
            ? null
            : values.ima_knowledge_folder_id ?? null
          : null,
      ima_knowledge_folder_name:
        imaSyncActive &&
        effectiveSubmitAccountId &&
        !values.ima_use_default_target &&
        values.ima_target_type === "knowledge_base"
          ? selectedImaKnowledgeFolder?.label ?? "根目录"
          : undefined,
      weekly_period: values.schedule_type === "weekly_report" ? values.weekly_period : undefined,
      weekly_start_day: values.schedule_type === "weekly_report" ? values.weekly_start_day ?? 0 : undefined,
      weekly_start_time: values.schedule_type === "weekly_report" ? formatTime(weeklyStartTime) : undefined,
      weekly_end_day: values.schedule_type === "weekly_report" ? values.weekly_end_day ?? 6 : undefined,
      weekly_end_time: values.schedule_type === "weekly_report" ? formatTime(weeklyEndTime) : undefined
    };
    onSubmit(payload);
  };

  const sectionTitles: Record<SectionKey, string> = {
    basic: "基础设置",
    topic_card: "话题卡片配置",
    image_card: "图片卡片配置",
    chatlog: "备份聊天记录",
    message_stats: "导出群消息统计",
    message_stats_github: "同步群消息统计到 GitHub",
    model_output: "备份模型返回结果",
    github_deploy: "部署日报到 GitHub",
    html_backup: "本地 HTML 备份",
    advanced: "高级配置"
  };

  const renderNavLabel = (label: string, enabled?: boolean, indent = 0) => {
    const isChild = indent > 0;
    return (
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr auto",
          alignItems: "center",
          gap: 8,
          padding: isChild ? "6px 8px" : "2px 0",
          paddingLeft: indent,
          marginLeft: isChild ? 6 : 0,
          borderLeft: isChild ? "2px solid #f0f0f0" : undefined,
          background: isChild ? "rgba(0, 0, 0, 0.015)" : "transparent",
          borderRadius: isChild ? 6 : 0
        }}
      >
        <span
          style={{
            minWidth: 0,
            whiteSpace: "normal",
            wordBreak: "break-word",
            lineHeight: 1.45,
            fontSize: isChild ? 13.5 : 14,
            color: isChild ? "rgba(0, 0, 0, 0.7)" : undefined
          }}
        >
          {label}
        </span>
        {enabled === undefined ? null : (
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "flex-end",
              gap: 4,
              color: enabled ? "#52c41a" : "rgba(0, 0, 0, 0.45)",
              whiteSpace: "nowrap",
              fontSize: 12,
              minWidth: 56
            }}
          >
            {enabled ? <CheckCircleFilled /> : null}
            <span>{enabled ? "已启用" : "未启用"}</span>
          </span>
        )}
      </div>
    );
  };

  const menuItems = useMemo<MenuProps["items"]>(
    () => [
      { key: "basic", label: renderNavLabel("基础设置") },
      ...(isTopicCardTask ? [{ key: "topic_card", label: renderNavLabel("话题卡片配置", true) }] : []),
      ...(isImageCardTask ? [{ key: "image_card", label: renderNavLabel("图片卡片配置", true) }] : []),
      { key: "chatlog", label: renderNavLabel("备份聊天记录", chatlogBackupEnabled) },
      { key: "message_stats", label: renderNavLabel("导出群消息统计", messageStatsEnabled) },
      { key: "message_stats_github", label: renderNavLabel("同步群消息统计到 GitHub", messageStatsGithubActiveView, 18) },
      { key: "model_output", label: renderNavLabel("备份模型返回结果", modelOutputBackupEnabled) },
      { key: "github_deploy", label: renderNavLabel("部署日报到 GitHub", githubDeployEnabled) },
      { key: "html_backup", label: renderNavLabel("本地HTML备份", htmlBackupActiveView) },
      { key: "advanced", label: renderNavLabel("高级配置") }
    ],
    [
      chatlogBackupEnabled,
      messageStatsEnabled,
      messageStatsGithubActiveView,
      modelOutputBackupEnabled,
      githubDeployEnabled,
      htmlBackupActiveView,
      isTopicCardTask,
      isImageCardTask
    ]
  );

  const renderTopicCardSection = () => {
    if (!isTopicCardTask) {
      return null;
    }
    return (
      <>
        <Form.Item
          name="topic_text_layout"
          label="文字布局"
          tooltip="控制飞书文字消息怎么发：逐话题就是一张卡一条消息；合并就是多个话题放在一条消息里；自动会按阈值决定。"
          rules={[{ required: true, message: "请选择文字布局" }]}
        >
          <Select
            options={[
              { label: "逐话题", value: "per_topic" },
              { label: "合并", value: "merged" },
              { label: "自动", value: "auto" }
            ]}
          />
        </Form.Item>
        {topicTextLayout === "auto" ? (
          <Form.Item
            name="topic_text_merge_threshold"
            label="文字自动合并阈值"
            tooltip="话题数量超过这个值时，文字消息自动合并成一条。"
            rules={[{ required: true, message: "请输入文字自动合并阈值" }]}
          >
            <InputNumber min={1} max={20} style={{ width: "100%" }} />
          </Form.Item>
        ) : null}
        <Form.Item
          name="topic_image_enabled"
          label="图片推送"
          valuePropName="checked"
          tooltip="开启后会把同一份话题卡片数据渲染成 PNG 图片，再上传到飞书并用当前 Webhook 推送图片。"
        >
          <Switch />
        </Form.Item>
        {topicImageEnabled ? (
          <>
            <Form.Item
              name="topic_image_layout"
              label="图片布局"
              tooltip="单张表示每个话题一张图；合集表示多个话题合成一张长图；自动会按阈值决定。"
              rules={[{ required: true, message: "请选择图片布局" }]}
            >
              <Select
                options={[
                  { label: "单张", value: "single" },
                  { label: "合集", value: "collection" },
                  { label: "自动", value: "auto" }
                ]}
              />
            </Form.Item>
            {topicImageLayout === "auto" ? (
              <Form.Item
                name="topic_image_merge_threshold"
                label="图片自动合集阈值"
                tooltip="话题数量超过这个值时，图片自动合成一张长图。"
                rules={[{ required: true, message: "请输入图片自动合集阈值" }]}
              >
                <InputNumber min={1} max={20} style={{ width: "100%" }} />
              </Form.Item>
            ) : null}
            <Form.Item
              name="topic_image_backup_enabled"
              label="本地保存"
              valuePropName="checked"
              tooltip="开启后每次推送时，会把卡片 PNG 图片和对应 Markdown 文本自动保存到本地文件夹（按日期分目录）。"
            >
              <Switch />
            </Form.Item>
            {topicImageBackupEnabled ? (
              <Form.Item
                name="topic_image_backup_path"
                label="保存路径"
                tooltip="相对路径将基于本地备份目录（默认 backups/topic_cards），路径会被保存方便下次使用。"
                extra="示例：topic_cards/案例图 或 D:/自媒体/职场案例卡片"
              >
                <Input placeholder="留空则保存到 backups/topic_cards/日期/" />
              </Form.Item>
            ) : null}
          </>
        ) : null}
      </>
    );
  };

  const renderImageCardSection = () => {
    if (!isImageCardTask) {
      return null;
    }
    return (
      <>
        <Form.Item
          name="image_prompt_template_id"
          label="图片提示词模板"
          tooltip="该模板只负责每张图片的视觉风格和排版要求，会与拆分后的每个 Markdown 内容块组合后发送给图片模型。"
          rules={[{ required: true, message: "请选择图片提示词模板" }]}
        >
          <Select
            options={imagePromptTemplateOptions}
            loading={imagePromptTemplatesLoading}
            placeholder={imagePromptTemplatesLoading ? "加载中..." : "请选择图片提示词模板"}
            optionFilterProp="label"
            showSearch
          />
        </Form.Item>
        <Form.Item
          name="image_split_enabled"
          label="逐话题生成"
          valuePropName="checked"
          tooltip="开启后，文本模型用固定标识分隔每个话题，系统为每个话题生成一张图片；关闭后，整份模型结果只生成一张图片。"
        >
          <Switch />
        </Form.Item>
        {imageSplitEnabled ? (
          <>
            <Form.Item
              name="image_split_prompt"
              label={
                <Space size={4}>
                  <span>内容拆分规则</span>
                  <Popover
                    placement="rightTop"
                    trigger="click"
                    title="内容拆分规则说明"
                    content={
                      <div style={{ width: 460, maxWidth: "70vw", userSelect: "text", cursor: "text" }}>
                        <Typography.Paragraph style={{ marginBottom: 8 }}>
                          该规则用于拆分内容并逐块生图，无符合内容时跳过生图。
                        </Typography.Paragraph>
                        <pre
                          style={{
                            margin: "8px 0 0",
                            padding: 12,
                            borderRadius: 6,
                            background: "#f5f5f5",
                            whiteSpace: "pre-wrap",
                            userSelect: "text"
                          }}
                        >{`${"${block_start}"}\n${"${block_end}"}`}</pre>
                        <Typography.Text type="secondary">
                          前者标记内容开始，中间为AI生成的话题内容，后者标记内容结束，自定义时必须保留。
                        </Typography.Text>
                      </div>
                    }
                  >
                    <QuestionCircleOutlined style={{ color: "#8c8c8c", cursor: "pointer" }} />
                  </Popover>
                </Space>
              }
              rules={[
                { required: true, message: "请输入内容拆分规则" },
                {
                  validator: (_, value?: string) =>
                    value?.includes("${block_start}") && value?.includes("${block_end}")
                      ? Promise.resolve()
                      : Promise.reject(new Error("内容拆分规则必须同时包含 ${block_start} 和 ${block_end}"))
                }
              ]}
            >
              <Input.TextArea autoSize={{ minRows: 8, maxRows: 16 }} />
            </Form.Item>
            <Space style={{ marginTop: -12, marginBottom: 16 }}>
              <Button type="link" onClick={() => form.setFieldValue("image_split_prompt", DEFAULT_IMAGE_SPLIT_PROMPT)}>
                恢复默认
              </Button>
            </Space>
          </>
        ) : null}
        <Form.Item
          name="image_aspect_ratio"
          label="图片比例"
          tooltip="自适应由图片接口决定；指定比例后，系统会结合分辨率换算为实际像素尺寸。"
          rules={[{ required: true, message: "请选择图片比例" }]}
        >
          <Select
            options={[
              { label: "自适应", value: "auto" },
              { label: "方图 1:1", value: "1:1" },
              { label: "横版 3:2", value: "3:2" },
              { label: "竖版 2:3", value: "2:3" },
              { label: "竖屏 9:16", value: "9:16" }
            ]}
          />
        </Form.Item>
        <Form.Item
          name="image_resolution"
          label="分辨率"
          tooltip="分辨率越高，生成时间、接口费用和飞书上传体积通常越大；最终是否支持由图片模型供应商决定。"
          rules={[{ required: true, message: "请选择分辨率" }]}
        >
          <Select
            options={[
              { label: "自适应", value: "auto" },
              { label: "1K", value: "1k" },
              { label: "2K", value: "2k" },
              { label: "4K", value: "4k" }
            ]}
          />
        </Form.Item>
        <Form.Item
          name="max_image_count"
          label="单次最多生成图片"
          tooltip="在调用图片接口前校验。识别出的内容超过上限时，本次作业直接失败，避免意外产生过多费用。"
          rules={[{ required: true, message: "请输入单次最多生成图片数" }]}
        >
          <InputNumber min={1} max={20} style={{ width: "100%" }} />
        </Form.Item>
      </>
    );
  };

  const renderBasicSection = () => (
    <>
      <Form.Item name="is_enabled" label="启用" valuePropName="checked">
        <Switch />
      </Form.Item>
      <Form.Item
        name="name"
        label="作业名称"
        tooltip="用于任务列表和飞书消息标题，请保持简洁易懂"
        rules={[
          { required: true, message: "请输入作业名称" },
          { max: 120, message: "名称长度需小于 120 个字符" }
        ]}
      >
        <Input placeholder="请输入作业名称" />
      </Form.Item>
      <Form.Item
        name="schedule_type"
        label="调度类型"
        rules={[{ required: true, message: "请选择调度类型" }]}
      >
        <Select options={scheduleOptions} placeholder="请选择调度类型" />
      </Form.Item>
      {scheduleTypeValue === "custom_cron" ? (
        <Form.Item
          name="cron_expression"
          label="Cron 表达式"
          rules={[{ required: true, message: "请输入 Cron 表达式" }]}
        >
          <Input placeholder="0 9 * * *" />
        </Form.Item>
      ) : null}
      {scheduleTypeValue === "weekly" ? (
        <Form.Item
          name="weekdays"
          label="执行周几"
          rules={[{ required: true, message: "请选择执行周几" }]}
        >
          <Select options={weekdayOptions} mode="multiple" placeholder="请选择周几" />
        </Form.Item>
      ) : null}
      {scheduleTypeValue === "weekly_report" ? (
        <>
          <Form.Item
            name="weekly_report_weekday"
            label="执行周几"
            rules={[{ required: true, message: "请选择执行周几" }]}
          >
            <Select options={weekdayOptions} placeholder="请选择执行周几" />
          </Form.Item>
          <Form.Item
            name="weekly_period"
            label="统计周期"
            rules={[{ required: true, message: "请选择统计周期" }]}
          >
            <Radio.Group
              options={[
                { label: "上一周", value: "previous_week" },
                { label: "当周", value: "current_week" }
              ]}
              optionType="button"
              buttonStyle="solid"
            />
          </Form.Item>
          <Form.Item
            label="时间窗口"
            tooltip="该时间段决定聊天记录的取数范围（北京时间），例如周一0:00 到 周日24:00"
          >
            <Space direction="vertical" style={{ width: "100%" }}>
              <Space align="baseline" wrap>
                <Form.Item
                  name="weekly_start_day"
                  label="开始日"
                  rules={[{ required: true, message: "请选择开始日" }]}
                >
                  <Select options={weekdayOptions} style={{ width: 160 }} />
                </Form.Item>
                <Form.Item
                  name="weekly_start_time_picker"
                  label="时间"
                  rules={[{ required: true, message: "请选择开始时间" }]}
                >
                  <TimeSelectInput minuteStep={5} />
                </Form.Item>
              </Space>
              <Space align="baseline" wrap>
                <Form.Item
                  name="weekly_end_day"
                  label="结束日"
                  rules={[{ required: true, message: "请选择结束日" }]}
                >
                  <Select options={weekdayOptions} style={{ width: 160 }} />
                </Form.Item>
                <Form.Item
                  name="weekly_end_time_picker"
                  label="时间"
                  rules={[{ required: true, message: "请选择结束时间" }]}
                >
                  <TimeSelectInput minuteStep={5} />
                </Form.Item>
              </Space>
              <Text type="secondary">
                提示：日期偏移和文件命名模板会基于该窗口计算 {`{YYYY-MM-DD}`}/{`{week_start}`}/{`{week_end}`}。
              </Text>
            </Space>
          </Form.Item>
        </>
      ) : null}
      {scheduleTypeValue !== "weekly_report" ? (
        <>
          <Form.Item
            name="interval_enabled"
            label="按间隔执行"
            valuePropName="checked"
            tooltip="开启后按照频率循环触发；关闭则仅在固定执行时间运行一次。"
            hidden={isManual}
          >
            <Switch disabled={isManual} />
          </Form.Item>
          {!isManual && intervalEnabled ? (
            <>
              <Form.Item
                name="window_start"
                label="生效范围开始时间"
                tooltip="限定每天允许触发的起始时间"
                rules={[{ required: true, message: "请选择开始时间" }]}
              >
                <TimeSelectInput minuteStep={5} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item
                label="生效范围结束时间"
                tooltip="限定每天允许触发的结束时间，可设为24:00表示当天结束"
                required
              >
                <Space.Compact style={{ width: "100%" }}>
                  <Form.Item
                    name="window_end"
                    noStyle
                    rules={[{ required: true, message: "请选择结束时间" }]}
                  >
                    <TimeSelectInput minuteStep={5} style={{ width: "100%" }} />
                  </Form.Item>
                  <Button type="link" onClick={() => form.setFieldsValue({ window_end: parseTime("14:00") })}>
                    14:00
                  </Button>
                  <Button type="link" onClick={() => form.setFieldsValue({ window_end: parseTime("18:00") })}>
                    18:00
                  </Button>
                  <Button type="link" onClick={() => form.setFieldsValue({ window_end: parseTime("24:00") })}>
                    24:00
                  </Button>
                </Space.Compact>
              </Form.Item>
              <Form.Item
                name="interval_minutes"
                label="间隔频率（分钟）"
                rules={[{ required: true, message: "请输入间隔频率" }]}
              >
                <InputNumber min={5} max={1440} style={{ width: "100%" }} />
              </Form.Item>
            </>
          ) : (
            <>
              <Form.Item
                name="date_baseline"
                label="聊天记录日期基准"
                tooltip="控制聊天记录窗口的日期锚点：以执行时间为基准，选择“当日”则聊天记录开始时间锚定执行当天；选择“前一日”则锚定前一天，适用于跨日窗口（如昨日02:00→今日02:00）。"
                rules={[{ required: true, message: "请选择日期基准" }]}
              >
                <Radio.Group
                  options={[
                    { label: "开始时间当日", value: "current_day" },
                    { label: "开始时间前一日", value: "previous_day" }
                  ]}
                  optionType="button"
                  buttonStyle="solid"
                />
              </Form.Item>
              <Form.Item
                name="start_time"
                label="聊天记录开始时间"
                tooltip="聊天记录拉取窗口的起始时间点，与“聊天记录日期基准”组合确定具体日期。"
                rules={[{ required: true, message: "请选择开始时间" }]}
              >
                <TimeSelectInput minuteStep={5} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item
                label="聊天记录结束时间"
                tooltip="聊天记录拉取窗口的截止时间点；若早于开始时间，系统会自动将结束日期顺延一天。"
                required
              >
                <Space.Compact style={{ width: "100%" }}>
                  <Form.Item name="end_time" noStyle rules={[{ required: true, message: "请选择结束时间" }]}>
                    <TimeSelectInput minuteStep={5} style={{ width: "100%" }} />
                  </Form.Item>
                  <Button type="link" onClick={() => setTimeField("end_time", parseTime("24:00"))}>
                    设为24:00
                  </Button>
                </Space.Compact>
              </Form.Item>
              {!isManual ? (
                <Form.Item label="执行时间" tooltip="作业实际触发的时间点，可早于或晚于窗口结束。" required>
                  <Space.Compact style={{ width: "100%" }}>
                    <Form.Item
                      name="execution_time"
                      noStyle
                      rules={[{ required: true, message: "请选择执行时间" }]}
                    >
                      <TimeSelectInput minuteStep={5} style={{ width: "100%" }} />
                    </Form.Item>
                    <Button type="link" onClick={() => setTimeField("execution_time", parseTime("24:00"))}>
                      设为24:00
                    </Button>
                  </Space.Compact>
                </Form.Item>
              ) : null}
            </>
          )}
        </>
      ) : null}
      <Form.Item
        name="disk_alert_enabled"
        label="磁盘写入告警"
        valuePropName="checked"
        tooltip="开启后会复用当前任务的失败告警机器人通道，在单次作业磁盘写入超过阈值时推送提醒。"
      >
        <Switch />
      </Form.Item>
      <Form.Item
        noStyle
        shouldUpdate={(prev, next) => prev.disk_alert_enabled !== next.disk_alert_enabled}
      >
        {({ getFieldValue }) =>
          getFieldValue("disk_alert_enabled") ? (
            <Form.Item
              name="disk_alert_threshold_mb"
              label="磁盘写入告警阈值（MB）"
              tooltip="按本次作业实际磁盘写入判断，包含导出文件写入；ChatLog 模式还会计入本次解密库写入估算。"
              rules={[{ required: true, message: "请输入磁盘写入告警阈值" }]}
            >
              <InputNumber min={1} max={1024 * 1024} style={{ width: "100%" }} />
            </Form.Item>
          ) : null
        }
      </Form.Item>
      <Form.Item
        name="offset_minutes"
        label="偏移分钟数"
        tooltip="将聊天记录窗口整体向后平移（仅影响数据窗口，不改执行时间）。"
        rules={[{ required: true, message: "请输入偏移分钟数" }]}
      >
        <InputNumber min={0} max={1440} style={{ width: "100%" }} />
      </Form.Item>
      <Form.Item
        name="max_retry"
        label="最大重试次数"
        tooltip="失败后最多再试几次。比如填 3：AI 最多请求 4 次；GitHub 或飞书如果第一次失败，最多再重试 3 次，不会重新生成日报。"
        rules={[{ required: true, message: "请输入重试次数" }]}
      >
        <InputNumber min={0} max={10} style={{ width: "100%" }} />
      </Form.Item>
      <Form.Item
        name="retry_interval_sec"
        label="重试间隔（秒）"
        rules={[{ required: true, message: "请输入重试间隔" }]}
      >
        <InputNumber min={60} step={30} style={{ width: "100%" }} />
      </Form.Item>
    </>
  );

  const renderChatlogBackupSection = () => (
    <>
      <Form.Item
        name="chatlog_backup_enabled"
        label="备份聊天记录"
        valuePropName="checked"
        tooltip="开启后会把送入模型的聊天文本保存到本地，便于查阅。"
      >
        <Switch />
      </Form.Item>
      {chatlogBackupEnabled ? (
        <>
          <Form.Item
            name="chatlog_backup_path"
            label="保存路径"
            tooltip="相对路径基于本地备份目录（默认 backups/chatlogs），也可填写绝对路径。"
            extra="示例：chatlogs/测试群 或 /Users/me/chatlogs"
          >
            <Input placeholder="例如：chatlogs/测试群" />
          </Form.Item>
          <Form.Item
            name="chatlog_backup_formats"
            label="文件格式"
            rules={[{ required: true, message: "请选择文件格式" }]}
          >
            <Select
              mode="multiple"
              placeholder="请选择格式（可多选）"
              options={[
                { label: "Markdown (.md)", value: "md" },
                { label: "纯文本 (.txt)", value: "txt" }
              ]}
            />
          </Form.Item>
          <Form.Item
            name="chatlog_backup_filename_template"
            label="文件命名模板"
            tooltip={getTemplateTooltip()}
            extra={renderTemplateExample("示例：聊天记录_{week_start}_{week_end} → 聊天记录_2025-11-11_2025-11-12.txt")}
          >
            <Input placeholder="聊天记录_{week_start}_{week_end}" />
          </Form.Item>
          <Form.Item
            name="chatlog_backup_filename_date_offset_days"
            label="文件名日期参数偏移（天）"
            tooltip="基准为作业执行完成时间，取值 -7~+7；例如 -1 代表生成前一天的文件名。"
          >
            <InputNumber min={-7} max={7} style={{ width: "100%" }} />
          </Form.Item>
        </>
      ) : null}
    </>
  );

  const renderMessageStatsGithubSection = () => {
    if (!messageStatsEnabled) {
      return <Text type="secondary">请先开启“导出群消息统计”。</Text>;
    }
    return (
      <>
        <Form.Item
          name="message_stats_github_enabled"
          label="同步群消息统计到 GitHub"
          valuePropName="checked"
          tooltip={getMessageStatsGithubTooltip()}
        >
          <Switch />
        </Form.Item>
        {messageStatsGithubEnabled ? (
          <>
            <Form.Item
              name="message_stats_github_config_id"
              label="GitHub 配置"
              rules={[{ required: true, message: "请选择 GitHub 配置" }]}
            >
              <Select
                placeholder="请选择 GitHub 配置"
                options={githubConfigOptions}
                loading={githubConfigs.length === 0}
                allowClear
                dropdownRender={(menu) => (
                  <>
                    {menu}
                    <div style={{ padding: 8 }}>
                      <Button
                        type="link"
                        block
                        onClick={() => {
                          setConfigTarget("message_stats");
                          setConfigModalOpen(true);
                        }}
                      >
                        [+] 新建配置
                      </Button>
                    </div>
                  </>
                )}
              />
            </Form.Item>
            <Form.Item
              name="message_stats_github_filename_template"
              label="GitHub_消息统计文件名模板"
              tooltip={getTemplateTooltip()}
              extra={renderTemplateExample("示例：每日群成员发言数量统计_{YYYY-MM-DD} → 每日群成员发言数量统计_2025-11-12.md")}
            >
              <Input placeholder="每日群成员发言数量统计_{YYYY-MM-DD}" />
            </Form.Item>
            {!isWeeklyReport ? (
              <Form.Item
                name="message_stats_github_filename_date_offset_days"
                label="GitHub_消息统计文件名日期参数偏移（天）"
                tooltip="基准为作业执行完成时间（与 GitHub 部署一致），-1 表示前一天，+1 表示后一天。"
              >
                <InputNumber min={-7} max={7} style={{ width: "100%" }} />
              </Form.Item>
            ) : null}
            <Form.Item
              name="message_stats_github_root"
              label="消息统计根目录（一级目录）"
              tooltip="用于区分群组的一级目录名称，例如 xinjian 或 xinghuo。"
            >
              <Input placeholder="例如：xinjian" />
            </Form.Item>
          </>
        ) : null}
      </>
    );
  };

  const renderMessageStatsSection = (includeGithubSubsection: boolean) => (
    <>
      <Form.Item
        name="message_stats_enabled"
        label="导出群消息统计"
        valuePropName="checked"
        tooltip="开启后会根据当前聊天窗口生成发言数量统计，可选择多种文件格式。"
      >
        <Switch />
      </Form.Item>
      {messageStatsEnabled ? (
        <>
          <Form.Item
            name="message_stats_formats"
            label="导出格式"
            rules={[{ required: true, message: "请选择导出格式" }]}
          >
            <Select
              mode="multiple"
              placeholder="请选择格式"
              options={[
                { label: "Markdown (.md)", value: "md" },
                { label: "CSV (.csv)", value: "csv" },
                { label: "Excel (.xlsx)", value: "xlsx" }
              ]}
            />
          </Form.Item>
          <Form.Item
            name="message_stats_path"
            label="保存路径"
            tooltip="相对路径将基于本地备份目录（默认 backups/message_reports），路径会被保存方便下次使用。"
            extra="示例：message_reports/测试群 或 /Users/me/reports/message_stats"
          >
            <Input placeholder="例如：message_reports/测试群" />
          </Form.Item>
          <Form.Item
            name="message_stats_filename_template"
            label="文件命名模板"
            tooltip={getTemplateTooltip()}
            extra={renderTemplateExample("示例：群聊发言统计_{week_start}_{week_end} → 群聊发言统计_2025-11-03_2025-11-09.md")}
          >
            <Input placeholder="每日群成员发言数量统计_{YYYY-MM-DD}" />
          </Form.Item>
          {!isWeeklyReport ? (
            <Form.Item
              name="message_stats_filename_date_offset_days"
              label="文件名日期参数偏移（天）"
              tooltip="基准为作业执行完成时间（与 GitHub 部署一致），取值 -7~+7；例如 -1 代表生成前一天的统计。"
            >
              <InputNumber min={-7} max={7} style={{ width: "100%" }} />
            </Form.Item>
          ) : null}
          {includeGithubSubsection ? renderMessageStatsGithubSection() : null}
        </>
      ) : null}
    </>
  );

  const renderModelOutputSection = () => (
    <>
      <Form.Item
        name="model_output_backup_enabled"
        label="备份模型返回结果"
        valuePropName="checked"
        tooltip="开启后会将模型原始输出另存为 Markdown 或 TXT 文件。"
      >
        <Switch />
      </Form.Item>
      {modelOutputBackupEnabled ? (
        <>
          <Form.Item
            name="model_output_path"
            label="保存路径"
            tooltip="相对路径将基于本地备份目录（默认 backups/model_outputs），路径会被保存方便下次使用。"
            extra="示例：model_outputs/测试群 或 /Users/me/reports/model_outputs"
          >
            <Input placeholder="例如：model_outputs/测试群" />
          </Form.Item>
          <Form.Item
            name="model_output_formats"
            label="文件格式"
            rules={[{ required: true, message: "请选择文件格式" }]}
          >
            <Select
              mode="multiple"
              placeholder="请选择格式（可多选）"
              options={[
                { label: "Markdown (.md)", value: "md" },
                { label: "纯文本 (.txt)", value: "txt" }
              ]}
            />
          </Form.Item>
          <Form.Item
            name="model_output_filename_template"
            label="文件命名模板"
            tooltip={getTemplateTooltip()}
            extra={renderTemplateExample("示例：模型输出_{week_start}_{week_end} → 模型输出_2025-11-03_2025-11-09.md")}
          >
            <Input placeholder="模型输出_{YYYY-MM-DD}" />
          </Form.Item>
          {!isWeeklyReport ? (
            <Form.Item
              name="model_output_filename_date_offset_days"
              label="文件名日期参数偏移（天）"
              tooltip="基准为作业执行完成时间（与 GitHub 部署一致），-1 表示将文件名日期定位到前一天。"
            >
              <InputNumber min={-7} max={7} style={{ width: "100%" }} />
            </Form.Item>
          ) : null}
          <Form.Item
            name="ima_sync_enabled"
            label="同步到 ima"
            valuePropName="checked"
            tooltip="这是新增的附加同步动作。默认关闭；同步失败不会影响原有作业成功状态。"
          >
            <Switch />
          </Form.Item>
          {imaTargetActiveView ? (
            <>
              <Form.Item
                name="ima_use_default_account"
                label="使用默认ima账号"
                valuePropName="checked"
                tooltip="开启后使用“ima账号管理/ima知识库同步设置”里的默认账号；关闭后可为当前作业指定单独的 ima 账号。"
              >
                <Switch
                  onChange={() => {
                    form.setFieldsValue({
                      ima_account_id: undefined,
                      ima_note_folder_id: undefined,
                      ima_knowledge_base_id: undefined,
                      ima_knowledge_folder_id: "root"
                    });
                  }}
                />
              </Form.Item>
              {!imaUseDefaultAccount ? (
                <Form.Item
                  name="ima_account_id"
                  label="ima账号"
                  rules={[{ required: true, message: "请选择 ima 账号" }]}
                >
                  <Select
                    allowClear
                    showSearch
                    placeholder="请选择要使用的 ima 账号"
                    options={imaAccountOptions}
                    optionFilterProp="label"
                    onChange={(value) => {
                      form.setFieldsValue({
                        ima_account_id: value,
                        ima_note_folder_id: undefined,
                        ima_knowledge_base_id: undefined,
                        ima_knowledge_folder_id: "root"
                      });
                      void loadImaNoteFolders(value);
                      void loadImaKnowledgeBases(value);
                      setImaKnowledgeFolders([{ label: "根目录", value: "root" }]);
                    }}
                  />
                </Form.Item>
              ) : (
                <Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
                  {defaultImaAccountId
                    ? "当前作业会使用系统默认 ima 账号。若需改用其他账号，可关闭“使用默认 ima 账号”后单独指定。"
                    : "当前还没有配置默认 ima 账号。若继续使用默认账号模式，运行时会因为缺少默认账号而无法同步。"}
                </Text>
              )}
              <Form.Item
                name="ima_use_default_target"
                label="使用默认 ima 配置"
                valuePropName="checked"
                tooltip="开启后使用当前账号在“ima账号管理”里配置的默认目标和默认文件夹。"
              >
                <Switch />
              </Form.Item>
              {!imaUseDefaultTarget ? (
                <>
                  <Form.Item
                    name="ima_target_type"
                    label="同步目标类型"
                    rules={[{ required: true, message: "请选择同步目标类型" }]}
                  >
                    <Select
                      options={[
                        { label: "ima 笔记", value: "note" },
                        { label: "ima 知识库", value: "knowledge_base" }
                      ]}
                    />
                  </Form.Item>
                  {imaTargetType === "note" ? (
                    <Form.Item
                      name="ima_note_folder_id"
                      label="目标笔记本"
                      rules={[{ required: true, message: "请选择目标笔记本" }]}
                    >
                      <Select
                        allowClear
                        showSearch
                        placeholder={effectiveImaAccountId ? "请选择目标笔记本" : "请先选择 ima 账号"}
                        options={imaNoteFolderOptions}
                        optionFilterProp="label"
                        disabled={!effectiveImaAccountId}
                        loading={imaLoading.noteFolders}
                        dropdownRender={(menu) => (
                          <>
                            {menu}
                            <div style={{ padding: 8 }}>
                              <Button
                                type="link"
                                block
                                icon={<ReloadOutlined />}
                                disabled={!effectiveImaAccountId}
                                onClick={() => void loadImaNoteFolders(effectiveImaAccountId)}
                              >
                                刷新笔记本
                              </Button>
                            </div>
                          </>
                        )}
                      />
                    </Form.Item>
                  ) : (
                    <>
                      <Form.Item
                        name="ima_knowledge_base_id"
                        label="目标知识库"
                        rules={[{ required: true, message: "请选择目标知识库" }]}
                      >
                        <Select
                          allowClear
                          showSearch
                          placeholder={effectiveImaAccountId ? "请选择目标知识库" : "请先选择 ima 账号"}
                          options={imaKnowledgeBaseOptions}
                          optionFilterProp="label"
                          disabled={!effectiveImaAccountId}
                          loading={imaLoading.knowledgeBases}
                          onChange={() => form.setFieldValue("ima_knowledge_folder_id", "root")}
                          dropdownRender={(menu) => (
                            <>
                              {menu}
                              <div style={{ padding: 8 }}>
                                <Button
                                  type="link"
                                  block
                                  icon={<ReloadOutlined />}
                                  disabled={!effectiveImaAccountId}
                                  onClick={() => void loadImaKnowledgeBases(effectiveImaAccountId)}
                                >
                                  刷新知识库
                                </Button>
                              </div>
                            </>
                          )}
                        />
                      </Form.Item>
                      <Form.Item name="ima_knowledge_folder_id" label="目标文件夹">
                        <Select
                          allowClear
                          showSearch
                          placeholder={effectiveImaAccountId ? "请选择目标文件夹" : "请先选择 ima 账号"}
                          options={imaKnowledgeFolderOptions}
                          optionFilterProp="label"
                          disabled={!effectiveImaAccountId || !imaKnowledgeBaseId}
                          loading={imaLoading.knowledgeFolders}
                          dropdownRender={(menu) => (
                            <>
                              {menu}
                              <div style={{ padding: 8 }}>
                                <Button
                                  type="link"
                                  block
                                  icon={<ReloadOutlined />}
                                  disabled={!effectiveImaAccountId || !imaKnowledgeBaseId}
                                  onClick={() => void loadImaKnowledgeFolders(imaKnowledgeBaseId, effectiveImaAccountId)}
                                >
                                  刷新文件夹
                                </Button>
                              </div>
                            </>
                          )}
                        />
                      </Form.Item>
                    </>
                  )}
                </>
              ) : (
                <Text type="secondary">
                  将使用“ima知识库同步设置”页面里的默认目标和默认目录。未配置或同步失败都不会影响现有作业主流程。
                  将使用“ima知识库同步设置”页面里的默认目标和默认目录。未配置或同步失败都不会影响现有作业主流程。
                  将使用“ima知识库同步设置”页面里的默认目标和默认目录。未配置或同步失败都不会影响现有作业主流程。
                </Text>
              )}
            </>
          ) : null}
        </>
      ) : null}
    </>
  );

  const renderHtmlBackupSection = () => {
    return (
      <>
        <Form.Item
          name="html_backup_enabled"
          label="本地 HTML 备份"
          valuePropName="checked"
          tooltip="开启后会要求模型输出完整 HTML，并在本地保存清洗后的 HTML；不需要同时开启 GitHub 部署。"
        >
          <Switch />
        </Form.Item>
        {htmlBackupEnabled ? (
          <>
            <Form.Item
              name="html_backup_path"
              label="HTML 备份路径"
              tooltip="留空则使用默认 backups/html_reports/<年份> 目录；相对路径基于本地备份目录并会记住上次填写。"
              extra="示例：html_reports/测试群 或 /Users/me/reports/html"
            >
              <Input placeholder="例如：html_reports/测试群" />
            </Form.Item>
            <Form.Item
              name="html_backup_filename_template"
              label="HTML 备份文件命名模板"
              tooltip={getTemplateTooltip()}
              extra={renderTemplateExample("示例：测试群周报_{week_start}_{week_end} → 测试群周报_2025-11-03_2025-11-09.html")}
            >
              <Input placeholder="例如：测试群日报_{YYYY-MM-DD}" />
            </Form.Item>
            {!isWeeklyReport ? (
              <Form.Item
                name="html_backup_filename_date_offset_days"
                label="文件名日期参数偏移（天）"
                tooltip="基准为作业执行完成时间（与 GitHub 部署一致），-1 表示写入执行时间前一日的日期。"
              >
                <InputNumber min={-7} max={7} style={{ width: "100%" }} />
              </Form.Item>
            ) : null}
          </>
        ) : null}
      </>
    );
  };

  const renderGithubDeploySection = (includeHtmlSubsection: boolean) => (
    <>
      <Form.Item
        name="github_deploy_enabled"
        label="部署日报到 GitHub"
        valuePropName="checked"
        tooltip="开启后将强制模型输出完整 HTML 并上传到 GitHub Pages。"
      >
        <Switch />
      </Form.Item>
      {githubDeployEnabled ? (
        <>
          <Form.Item
            name="github_config_id"
            label="GitHub 配置"
            rules={[{ required: true, message: "请选择 GitHub 配置" }]}
          >
            <Select
              placeholder="请选择 GitHub 配置"
              options={githubConfigOptions}
              loading={githubConfigs.length === 0}
              allowClear
              dropdownRender={(menu) => (
                <>
                  {menu}
                  <div style={{ padding: 8 }}>
                    <Button
                      type="link"
                      block
                      onClick={() => {
                        setConfigTarget("deploy");
                        setConfigModalOpen(true);
                      }}
                    >
                      [+] 新建配置
                    </Button>
                  </div>
                </>
              )}
            />
          </Form.Item>
          <Form.Item
            name="github_filename_template"
            label="GitHub 文件名模板"
            tooltip={getTemplateTooltip()}
            extra={renderTemplateExample("示例：微信群日报_{YYYY-MM-DD}.html → 微信群日报_2025-11-12.html")}
          >
            <Input placeholder="例如：微信群日报_{YYYY-MM-DD}.html" />
          </Form.Item>
          {!isWeeklyReport ? (
            <Form.Item
              name="days_offset"
              label="GitHub 文件名日期参数偏移（天）"
              tooltip="控制部署日报到 GitHub 时文件名模板里的日期占位符，基准为作业执行完成时间；例如 -1 代表前一天。"
            >
              <InputNumber min={-7} max={7} style={{ width: "100%" }} />
            </Form.Item>
          ) : null}
          {includeHtmlSubsection ? renderHtmlBackupSection() : null}
        </>
      ) : null}
    </>
  );

  const renderAdvancedSection = () => (
    <>
      <Form.Item
        label="自定义时间范围"
        name="custom_range"
        tooltip="可选，覆盖默认拉取聊天记录的时间段。例如设为 2025-11-01 00:00~2025-11-02 00:00，则无论何时执行都只会读取这两天的内容。"
      >
        <DatePicker.RangePicker
          showTime={{ format: "HH:mm", minuteStep: 1 }}
          format="YYYY-MM-DD HH:mm"
          style={{ width: "100%" }}
          allowEmpty={[true, true]}
        />
      </Form.Item>
      <Form.Item
        label="生效日期范围"
        name="active_range"
        tooltip="可选，限制作业仅在指定日期内运行。例如设为 2025-11-01~2025-11-09，则 10 日后不再自动执行。"
      >
        <DatePicker.RangePicker format="YYYY-MM-DD" style={{ width: "100%" }} allowEmpty={[true, true]} />
      </Form.Item>
      <Form.Item name="description" label="备注">
        <Input.TextArea placeholder="可选补充描述" autoSize={{ minRows: 2, maxRows: 4 }} />
      </Form.Item>
    </>
  );

  const renderSectionContent = (key: SectionKey) => {
    switch (key) {
      case "basic":
        return renderBasicSection();
      case "topic_card":
        return renderTopicCardSection();
      case "image_card":
        return renderImageCardSection();
      case "chatlog":
        return renderChatlogBackupSection();
      case "message_stats":
        return renderMessageStatsSection(false);
      case "message_stats_github":
        return renderMessageStatsGithubSection();
      case "model_output":
        return renderModelOutputSection();
      case "github_deploy":
        return renderGithubDeploySection(false);
      case "html_backup":
        return renderHtmlBackupSection();
      case "advanced":
        return renderAdvancedSection();
      default:
        return null;
    }
  };

  const renderClassicView = () => (
    <>
      {renderBasicSection()}
      {renderTopicCardSection()}
      {renderImageCardSection()}
      {renderChatlogBackupSection()}
      {renderMessageStatsSection(true)}
      {renderModelOutputSection()}
      {renderGithubDeploySection(false)}
      {renderHtmlBackupSection()}
      {renderAdvancedSection()}
    </>
  );

  const renderSplitView = () => {
    const sectionOrder: SectionKey[] = [
      "basic",
      ...(isTopicCardTask ? (["topic_card"] as SectionKey[]) : []),
      ...(isImageCardTask ? (["image_card"] as SectionKey[]) : []),
      "chatlog",
      "message_stats",
      "message_stats_github",
      "model_output",
      "github_deploy",
      "html_backup",
      "advanced"
    ];

    return (
      <div style={{ display: "flex", gap: 16 }}>
        <div style={{ width: 260, borderRight: "1px solid #f0f0f0", paddingRight: 12 }}>
          <Menu
            mode="inline"
            items={menuItems}
            selectedKeys={[activeSection]}
            onClick={(info) => setActiveSection(info.key as SectionKey)}
          />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          {sectionOrder.map((key) => (
            <div key={key} style={{ display: activeSection === key ? "block" : "none" }}>
              <Typography.Title level={5} style={{ marginTop: 0 }}>
                {sectionTitles[key]}
              </Typography.Title>
              {renderSectionContent(key)}
            </div>
          ))}
        </div>
      </div>
    );
  };

  const modalTitle = (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 8,
        paddingRight: 32
      }}
    >
      <span>{title}</span>
      <Tooltip title={viewMode === "split" ? "切换到经典视图" : "切换到分栏视图"}>
        <Button
          size="small"
          type="text"
          icon={<SwapOutlined />}
          onClick={() => setViewMode(viewMode === "split" ? "classic" : "split")}
        />
      </Tooltip>
    </div>
  );

  return (
    <Modal
      open={open}
      title={modalTitle}
      destroyOnHidden
      onCancel={() => {
        form.resetFields();
        onCancel();
      }}
      onOk={() => form.submit()}
      confirmLoading={confirmLoading}
      width={viewMode === "split" ? 980 : 720}
    >
      <Form<JobFormValues>
        form={form}
        layout="vertical"
        initialValues={defaultFormValues}
        onFinish={handleFinish}
      >
        {viewMode === "split" ? renderSplitView() : renderClassicView()}
      </Form>
      <GithubConfigFormModal
        open={configModalOpen}
        initialValues={null}
        confirmLoading={configModalLoading}
        onCancel={() => setConfigModalOpen(false)}
        onSubmit={handleInlineConfigSubmit}
      />
    </Modal>
  );
}

export default JobFormModal;
