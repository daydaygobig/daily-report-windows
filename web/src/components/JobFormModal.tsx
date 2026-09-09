/**
 * 作业表单主组件：状态编排、提交组装、经典/分栏双视图。
 * 各配置分区的渲染拆分在同目录 sections/ 下；表单类型、时间工具、默认值、
 * ima 资源分别见 types.ts / timeUtils.tsx / defaults.ts / useImaResources.ts。
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Form, Menu, Modal, Tooltip, Typography, message } from "antd";
import type { MenuProps } from "antd";
import dayjs from "dayjs";
import type { Dayjs } from "dayjs";
import type { Job, JobPayload, Task } from "../services/tasks";
import type { PromptTemplate } from "../services/promptTemplates";
import { DEFAULT_IMAGE_SPLIT_PROMPT, fetchPromptTemplates } from "../services/promptTemplates";
import type { GithubConfig, GithubConfigPayload } from "../services/githubConfigs";
import { fetchGithubConfigs, createGithubConfig } from "../services/githubConfigs";
import GithubConfigFormModal from "./GithubConfigFormModal";
import { SwapOutlined, CheckCircleFilled } from "@ant-design/icons";
import { formatTime, parseTime } from "./jobForm/timeUtils";
import { defaultFormValues, toJobFormValues } from "./jobForm/defaults";
import {
  buildDisplayImaKnowledgeFolderOption,
  mergeImaKnowledgeFolderOptions
} from "./jobForm/imaOptions";
import { useImaResources } from "./jobForm/useImaResources";
import type { JobFormValues, JobFormModalProps, SectionKey, ViewMode } from "./jobForm/types";
import BasicSection from "./jobForm/sections/BasicSection";
import TopicCardSection from "./jobForm/sections/TopicCardSection";
import ImageCardSection from "./jobForm/sections/ImageCardSection";
import ChatlogBackupSection from "./jobForm/sections/ChatlogBackupSection";
import MessageStatsSection, { MessageStatsGithubSection } from "./jobForm/sections/MessageStatsSection";
import ModelOutputSection from "./jobForm/sections/ModelOutputSection";
import GithubDeploySection from "./jobForm/sections/GithubDeploySection";
import HtmlBackupSection from "./jobForm/sections/HtmlBackupSection";
import AdvancedSection from "./jobForm/sections/AdvancedSection";

const { Text } = Typography;

const VIEW_STORAGE_KEY = "job_form_view_mode";

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
  const githubDeployEnabled = Form.useWatch("github_deploy_enabled", form);
  const htmlBackupEnabled = Form.useWatch("html_backup_enabled", form);
  const messageStatsEnabled = Form.useWatch("message_stats_enabled", form);
  const messageStatsGithubEnabled = Form.useWatch("message_stats_github_enabled", form);
  const chatlogBackupEnabled = Form.useWatch("chatlog_backup_enabled", form);
  const modelOutputBackupEnabled = Form.useWatch("model_output_backup_enabled", form);
  const imaSyncEnabled = Form.useWatch("ima_sync_enabled", form);
  const imaUseDefaultAccount = Form.useWatch("ima_use_default_account", form);
  const imaAccountId = Form.useWatch("ima_account_id", form);
  const imaKnowledgeBaseId = Form.useWatch("ima_knowledge_base_id", form);
  const scheduleTypeValue = Form.useWatch("schedule_type", form);
  const isTopicCardTask = taskType === "topic_card";
  const isImageCardTask = taskType === "image_card";
  const messageStatsGithubActiveView = messageStatsEnabled && messageStatsGithubEnabled;
  const htmlBackupActiveView = Boolean(htmlBackupEnabled);

  const [githubConfigs, setGithubConfigs] = useState<GithubConfig[]>([]);
  const [configModalOpen, setConfigModalOpen] = useState(false);
  const [configTarget, setConfigTarget] = useState<"deploy" | "message_stats">("deploy");
  const [configModalLoading, setConfigModalLoading] = useState(false);
  const [imagePromptTemplates, setImagePromptTemplates] = useState<PromptTemplate[]>([]);
  const [imagePromptTemplatesLoading, setImagePromptTemplatesLoading] = useState(false);

  const ima = useImaResources(form);
  const {
    imaNoteFolderOptions,
    imaKnowledgeBaseOptions,
    imaKnowledgeFolderOptions,
    defaultImaAccountId,
    loadImaAccounts,
    loadImaNoteFolders,
    loadImaKnowledgeBases,
    loadImaKnowledgeFolders,
    setImaKnowledgeFolders
  } = ima;
  const effectiveImaAccountId = imaUseDefaultAccount ? defaultImaAccountId : imaAccountId;

  const githubConfigOptions = useMemo(
    () =>
      githubConfigs.map((config) => ({
        label: `${config.name}（${config.owner}/${config.repo}）`,
        value: config.id
      })),
    [githubConfigs]
  );
  const imagePromptTemplateOptions = useMemo(
    () => imagePromptTemplates.map((template) => ({ label: template.name, value: template.id })),
    [imagePromptTemplates]
  );

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
  }, [open, initialValues, form, loadGithubConfigs, loadImaAccounts, loadImaNoteFolders, loadImaKnowledgeBases, loadImaKnowledgeFolders, setImaKnowledgeFolders, defaultImaAccountId, isImageCardTask, loadImagePromptTemplates]);

  useEffect(() => {
    if (!open || !imaSyncEnabled) {
      return;
    }
    if (!effectiveImaAccountId) {
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
  }, [open, imaSyncEnabled, effectiveImaAccountId, imaKnowledgeBaseId, loadImaNoteFolders, loadImaKnowledgeBases, loadImaKnowledgeFolders, setImaKnowledgeFolders]);

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
    if (!effectiveImaAccountId) {
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
  }, [imaKnowledgeBaseId, effectiveImaAccountId, form, loadImaKnowledgeFolders, setImaKnowledgeFolders]);

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
      max_image_count: isImageCardTask ? values.max_image_count ?? 12 : 6,
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

  const githubSelectProps = {
    githubConfigOptions,
    githubConfigsLoading: githubConfigs.length === 0
  };
  const openGithubConfigModal = (target: "deploy" | "message_stats") => () => {
    setConfigTarget(target);
    setConfigModalOpen(true);
  };

  const renderSectionContent = (key: SectionKey) => {
    switch (key) {
      case "basic":
        return <BasicSection />;
      case "topic_card":
        return isTopicCardTask ? <TopicCardSection /> : null;
      case "image_card":
        return isImageCardTask ? (
          <ImageCardSection
            imagePromptTemplateOptions={imagePromptTemplateOptions}
            loading={imagePromptTemplatesLoading}
          />
        ) : null;
      case "chatlog":
        return <ChatlogBackupSection />;
      case "message_stats":
        return (
          <MessageStatsSection
            includeGithubSubsection={false}
            {...githubSelectProps}
            onOpenGithubConfigModal={openGithubConfigModal("message_stats")}
          />
        );
      case "message_stats_github":
        return (
          <MessageStatsGithubSection
            {...githubSelectProps}
            onOpenGithubConfigModal={openGithubConfigModal("message_stats")}
          />
        );
      case "model_output":
        return <ModelOutputSection ima={ima} />;
      case "github_deploy":
        return (
          <GithubDeploySection
            includeHtmlSubsection={false}
            {...githubSelectProps}
            onOpenGithubConfigModal={openGithubConfigModal("deploy")}
          />
        );
      case "html_backup":
        return <HtmlBackupSection />;
      case "advanced":
        return <AdvancedSection />;
      default:
        return null;
    }
  };

  const renderClassicView = () => (
    <>
      <BasicSection />
      {isTopicCardTask ? <TopicCardSection /> : null}
      {isImageCardTask ? (
        <ImageCardSection
          imagePromptTemplateOptions={imagePromptTemplateOptions}
          loading={imagePromptTemplatesLoading}
        />
      ) : null}
      <ChatlogBackupSection />
      <MessageStatsSection
        includeGithubSubsection
        {...githubSelectProps}
        onOpenGithubConfigModal={openGithubConfigModal("message_stats")}
      />
      <ModelOutputSection ima={ima} />
      <GithubDeploySection
        includeHtmlSubsection={false}
        {...githubSelectProps}
        onOpenGithubConfigModal={openGithubConfigModal("deploy")}
      />
      <HtmlBackupSection />
      <AdvancedSection />
    </>
  );

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
