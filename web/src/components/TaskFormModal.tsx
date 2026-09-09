import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Form, Input, Modal, Select, Space, Spin, Switch, Tooltip, Typography, message } from "antd";
import type { SelectProps } from "antd";
import type { Task, TaskPayload, TopicStyleConfig } from "../services/tasks";
import { fetchTasks } from "../services/tasks";
import { fetchModels } from "../services/models";
import { fetchChatrooms } from "../services/chatRecords";
import { fetchWebhooks } from "../services/webhooks";
import type { PromptTemplate, PromptTemplatePayload } from "../services/promptTemplates";
import { createPromptTemplate, fetchPromptTemplates } from "../services/promptTemplates";
import PromptTemplateModal from "./PromptTemplateModal";
import ModelSequenceList from "./ModelSequenceList";
import {
  DEFAULT_TOPIC_STYLE_CONFIG,
  normalizeTopicStyleConfig,
  STYLE_OPTIONS,
  STYLE_PREVIEWS,
  StylePreviewCard,
  THEME_OPTIONS,
  TOPIC_TYPE_OPTIONS
} from "./topicStyle";
import { InfoCircleOutlined } from "@ant-design/icons";

const { Text } = Typography;

type TaskFormValues = {
  name: string;
  task_type: "report" | "export" | "topic_card" | "image_card";
  prompt: string;
  model_id?: number;
  model_sequence?: { model_id?: number; max_attempts?: number }[];
  image_model_id?: number;
  image_model_sequence?: { model_id?: number; max_attempts?: number }[];
  upstream_task_id?: number;
  card_input_source: "chatlog" | "report";
  talkers: string[];
  talker_names?: string[];
  push_webhook_ids: number[];
  alert_webhook_ids: number[];
  is_active: boolean;
  system_prompt_custom_enabled: boolean;
  system_prompt_template?: string;
  system_prompt_include_message_count: boolean;
  topic_style_config: TopicStyleConfig;
};

type TaskFormModalProps = {
  open: boolean;
  initialValues?: Task | null;
  confirmLoading?: boolean;
  onCancel: () => void;
  onSubmit: (values: TaskPayload) => void | Promise<void>;
};

const DEFAULT_SYSTEM_PROMPT_TEMPLATE =
  "请基于聊天记录，根据提示词完成任务。\n时间范围: ${time_range}\n群聊: ${chatroom_name}";

const defaultFormValues: TaskFormValues = {
  name: "",
  task_type: "report",
  prompt: "",
  model_id: undefined,
  model_sequence: [{ model_id: undefined, max_attempts: 2 }],
  image_model_id: undefined,
  image_model_sequence: [{ model_id: undefined, max_attempts: 2 }],
  upstream_task_id: 0,
  card_input_source: "chatlog",
  talkers: [],
  talker_names: [],
  push_webhook_ids: [],
  alert_webhook_ids: [],
  is_active: true,
  system_prompt_custom_enabled: false,
  system_prompt_template: "",
  system_prompt_include_message_count: false,
  topic_style_config: DEFAULT_TOPIC_STYLE_CONFIG
};

type Option<T = string | number> = { label: string; value: T };

function TaskFormModal({ open, initialValues, confirmLoading, onCancel, onSubmit }: TaskFormModalProps) {
  const [form] = Form.useForm<TaskFormValues>();
  const title = useMemo(() => (initialValues ? "编辑任务" : "新增任务"), [initialValues]);
  const [modelOptions, setModelOptions] = useState<Option<number>[]>([]);
  const [imageModelOptions, setImageModelOptions] = useState<Option<number>[]>([]);
  const [reportTasks, setReportTasks] = useState<Task[]>([]);
  const [chatroomOptions, setChatroomOptions] = useState<Option<string>[]>([]);
  const [webhookOptions, setWebhookOptions] = useState<Option<number>[]>([]);
  const [chatroomLoading, setChatroomLoading] = useState(false);
  const [chatroomKeyword, setChatroomKeyword] = useState("");
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [templateModalOpen, setTemplateModalOpen] = useState(false);
  const [templateModalLoading, setTemplateModalLoading] = useState(false);
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null);
  const [stylePreviewOpen, setStylePreviewOpen] = useState(false);

  const customPromptEnabled = Form.useWatch("system_prompt_custom_enabled", form);
  const taskType = Form.useWatch("task_type", form) ?? "report";
  const cardInputSource = Form.useWatch("card_input_source", form) ?? "chatlog";
  const isExportTask = taskType === "export";
  const isTopicCardTask = taskType === "topic_card";
  const isImageCardTask = taskType === "image_card";

  const loadModels = useCallback(async () => {
    const models = await fetchModels();
    setModelOptions(
      models
        .filter((model) => (model.model_type ?? "text") === "text")
        .map((model) => ({ label: `${model.name} (${model.provider})`, value: model.id }))
    );
    setImageModelOptions(
      models
        .filter((model) => model.model_type === "image")
        .map((model) => ({ label: `${model.name} (${model.provider})`, value: model.id }))
    );
  }, []);

  const loadWebhooks = useCallback(async () => {
    const webhooks = await fetchWebhooks();
    setWebhookOptions(webhooks.map((item) => ({ label: item.name, value: item.id })));
  }, []);

  const loadUpstreamTasks = useCallback(async () => {
    const list = await fetchTasks();
    setReportTasks(list.filter((item) => item.task_type === "report"));
  }, []);

  const loadTemplates = useCallback(async () => {
    setTemplatesLoading(true);
    try {
      const list = await fetchPromptTemplates();
      setTemplates(list);
      return list;
    } finally {
      setTemplatesLoading(false);
    }
  }, []);

  const loadChatrooms = useCallback(
    async (keyword?: string, talkers?: string[]) => {
      setChatroomLoading(true);
      try {
        const rooms = await fetchChatrooms(keyword, talkers && talkers.length ? talkers : undefined);
        const selectedTalkers: string[] =
          talkers && talkers.length ? talkers : form.getFieldValue("talkers") ?? [];
        const selectedNames: string[] = form.getFieldValue("talker_names") ?? [];
        const map = new Map<string, Option<string>>();
        rooms.forEach((room) => {
          map.set(room.name, { label: room.display_name, value: room.name });
        });
        selectedTalkers.forEach((id, idx) => {
          if (!map.has(id)) {
            map.set(id, { label: selectedNames[idx] ?? id, value: id });
          }
        });
        const merged = Array.from(map.values());
        if (selectedTalkers.length) {
          const labelMap = new Map<string, string>(merged.map((item) => [item.value, item.label]));
          form.setFieldsValue({
            talker_names: selectedTalkers.map((id, idx) => labelMap.get(id) ?? selectedNames[idx] ?? id)
          });
        }
        setChatroomOptions(merged);
      } finally {
        setChatroomLoading(false);
      }
    },
    [form]
  );

  useEffect(() => {
    if (!open) {
      return;
    }
    const values: TaskFormValues = initialValues
      ? {
          name: initialValues.name,
          task_type: initialValues.task_type ?? "report",
          prompt: initialValues.prompt,
          model_id: initialValues.model_id ?? undefined,
          model_sequence:
            initialValues.task_type === "export"
              ? [{ model_id: undefined, max_attempts: 2 }]
              : (initialValues.model_sequence && initialValues.model_sequence.length
                  ? initialValues.model_sequence.map((item) => ({
                      model_id: item.model_id,
                      max_attempts: item.max_attempts || 2
                    }))
                  : [{ model_id: initialValues.model_id ?? undefined, max_attempts: 2 }]),
          image_model_id: initialValues.image_model_id ?? undefined,
          upstream_task_id: initialValues.upstream_task_id ?? 0,
          card_input_source: initialValues.card_input_source ?? "chatlog",
          image_model_sequence:
            initialValues.task_type === "image_card"
              ? (initialValues.image_model_sequence && initialValues.image_model_sequence.length
                  ? initialValues.image_model_sequence.map((item) => ({
                      model_id: item.model_id,
                      max_attempts: item.max_attempts || 2
                    }))
                  : [{ model_id: initialValues.image_model_id ?? undefined, max_attempts: 2 }])
              : [{ model_id: undefined, max_attempts: 2 }],
          talkers: initialValues.talkers ?? [],
          talker_names: initialValues.talker_names ?? [],
          push_webhook_ids: initialValues.push_webhook_ids ?? [],
          alert_webhook_ids: initialValues.alert_webhook_ids ?? [],
          is_active: initialValues.is_active,
          system_prompt_custom_enabled: initialValues.system_prompt_custom_enabled,
          system_prompt_template: initialValues.system_prompt_template ?? DEFAULT_SYSTEM_PROMPT_TEMPLATE,
          system_prompt_include_message_count: initialValues.system_prompt_include_message_count,
          topic_style_config: normalizeTopicStyleConfig(initialValues.topic_style_config)
        }
      : defaultFormValues;
    form.resetFields();
    form.setFieldsValue(values);
    setSelectedTemplateId(initialValues?.prompt_template_id ?? null);
    setChatroomKeyword("");
    void loadModels();
    void loadWebhooks();
    void loadUpstreamTasks();
    void loadChatrooms(undefined, values.talkers);
    void loadTemplates().then((list) => {
      const firstMatching = list?.find((item) => (item.template_type ?? "regular") === "regular");
      if (!initialValues?.prompt_template_id && values.task_type !== "export" && firstMatching) {
        setSelectedTemplateId(firstMatching.id);
        form.setFieldsValue({ prompt: firstMatching.content });
      }
    });
  }, [open, initialValues, form, loadModels, loadWebhooks, loadUpstreamTasks, loadChatrooms, loadTemplates]);

  useEffect(() => {
    if (customPromptEnabled && !form.getFieldValue("system_prompt_template")) {
      form.setFieldsValue({ system_prompt_template: DEFAULT_SYSTEM_PROMPT_TEMPLATE });
    }
  }, [customPromptEnabled, form]);

  const chatroomSelectProps: SelectProps<string[], { label: string; value: string }> = {
    mode: "multiple",
    showSearch: true,
    placeholder: "输入关键词检索群聊",
    filterOption: false,
    notFoundContent: chatroomLoading ? <Spin size="small" /> : "未找到匹配的群聊",
    onSearch: (value) => {
      setChatroomKeyword(value);
      void loadChatrooms(value, form.getFieldValue("talkers") ?? []);
    },
    onDropdownVisibleChange: (visible) => {
      if (visible) {
        void loadChatrooms(chatroomKeyword, form.getFieldValue("talkers") ?? []);
      }
    },
    options: chatroomOptions
  };

  const templateOptions = templates
    .filter((tpl) => (tpl.template_type ?? "regular") === "regular")
    .map((tpl) => ({ label: tpl.name, value: tpl.id }));

  useEffect(() => {
    if (!open || isExportTask || templates.length === 0) {
      return;
    }
    const current = templates.find((item) => item.id === selectedTemplateId);
    if (current && (current.template_type ?? "regular") === "regular") {
      return;
    }
    const firstMatching = templates.find((item) => (item.template_type ?? "regular") === "regular");
    setSelectedTemplateId(firstMatching?.id ?? null);
    form.setFieldValue("prompt", firstMatching?.content ?? "");
  }, [open, isExportTask, templates, selectedTemplateId, form]);

  const handleTemplateChange = (value?: number) => {
    setSelectedTemplateId(value ?? null);
    const template = templates.find((item) => item.id === value);
    if (template) {
      form.setFieldsValue({ prompt: template.content });
    }
  };

  const handleTemplateModalSubmit = async (payload: PromptTemplatePayload) => {
    try {
      setTemplateModalLoading(true);
      const created = await createPromptTemplate(payload);
      message.success("提示词已创建");
      const list = await loadTemplates();
      setSelectedTemplateId(created.id);
      form.setFieldsValue({ prompt: created.content });
      if (!list.some((item) => item.id === created.id)) {
        setTemplates((prev) => [...prev, created]);
      }
      setTemplateModalOpen(false);
    } finally {
      setTemplateModalLoading(false);
    }
  };

  const handleFinish = (values: TaskFormValues) => {
    if (!isExportTask && !selectedTemplateId) {
      message.error("请先选择或新建提示词模板");
      return;
    }
    const modelSequence = (values.model_sequence ?? []).filter((item) => item?.model_id);
    if (!isExportTask && modelSequence.length === 0) {
      message.error("请至少选择一个模型");
      return;
    }
    const imageModelSequence = (values.image_model_sequence ?? []).filter((item) => item?.model_id);
    if (isImageCardTask && imageModelSequence.length === 0) {
      message.error("请至少选择一个图片模型");
      return;
    }
    if ((isTopicCardTask || isImageCardTask) && values.card_input_source === "report" && !values.upstream_task_id) {
      message.error("纯日报内容模式必须选择上游日报任务");
      return;
    }
    const optionMap = new Map(chatroomOptions.map((item) => [item.value, item.label]));
    const talkerPairs = values.talkers
      .map((id, idx) => ({
        id: id?.trim() ?? "",
        name: optionMap.get(id) ?? values.talker_names?.[idx] ?? id
      }))
      .filter((item) => item.id);

    onSubmit({
      name: values.name.trim(),
      task_type: values.task_type,
      prompt: isExportTask ? "" : values.prompt,
      model_id: isExportTask ? null : values.model_sequence?.[0]?.model_id ?? null,
      image_model_id: isImageCardTask ? ((imageModelSequence[0]?.model_id as number) ?? null) : null,
      image_model_sequence: isImageCardTask
        ? imageModelSequence.map((item) => ({
            model_id: item.model_id as number,
            max_attempts: Math.max(Number(item.max_attempts || 2), 1)
          }))
        : null,
      model_sequence: isExportTask
        ? null
        : modelSequence
            .map((item) => ({
              model_id: item.model_id as number,
              max_attempts: Math.max(Number(item.max_attempts || 2), 1)
            })),
      prompt_template_id: isExportTask ? null : selectedTemplateId,
      upstream_task_id: isTopicCardTask || isImageCardTask ? (values.upstream_task_id ?? 0) : null,
      card_input_source: isTopicCardTask || isImageCardTask ? values.card_input_source : undefined,
      talkers: talkerPairs.map((item) => item.id),
      talker_names: talkerPairs.map((item) => item.name),
      push_webhook_ids: isExportTask ? [] : values.push_webhook_ids ?? [],
      alert_webhook_ids: values.alert_webhook_ids?.length ? values.alert_webhook_ids : [],
      is_active: values.is_active,
      system_prompt_custom_enabled: isExportTask ? false : values.system_prompt_custom_enabled,
      system_prompt_template:
        !isExportTask && values.system_prompt_custom_enabled
          ? (values.system_prompt_template && values.system_prompt_template.trim()) || DEFAULT_SYSTEM_PROMPT_TEMPLATE
          : undefined,
      system_prompt_include_message_count:
        !isExportTask && values.system_prompt_custom_enabled ? values.system_prompt_include_message_count : false,
      topic_style_config: isTopicCardTask ? normalizeTopicStyleConfig(values.topic_style_config) : DEFAULT_TOPIC_STYLE_CONFIG
    });
  };

  return (
    <Modal
      open={open}
      title={title}
      width={1040}
      destroyOnHidden
      onCancel={() => {
        form.resetFields();
        onCancel();
      }}
      onOk={() => form.submit()}
      confirmLoading={confirmLoading}
    >
      <Form<TaskFormValues> layout="vertical" form={form} initialValues={defaultFormValues} onFinish={handleFinish}>
        <Form.Item name="talker_names" hidden>
          <Select mode="multiple" open={false} />
        </Form.Item>
        <Form.Item label="任务名称" name="name" rules={[{ required: true, message: "请输入任务名称" }]}>
          <Input placeholder="请输入任务名称" />
        </Form.Item>
        <Form.Item
          label="任务类型"
          name="task_type"
          tooltip="日报和话题卡片会调用模型；数据导出只拉取聊天记录并保存，不调用 LLM。"
        >
          <Select
            options={[
              { label: "日报", value: "report" },
              { label: "话题卡片", value: "topic_card" },
              { label: "图片卡片", value: "image_card" },
              { label: "数据导出", value: "export" }
            ]}
          />
        </Form.Item>
        {isTopicCardTask || isImageCardTask ? (
          <Form.Item
            label="上游日报任务"
            name="upstream_task_id"
            tooltip="选择日报任务后，本任务每次执行会自动关联该日报最近一次成功生成的结果；若日报尚未生成成功或已超过 24 小时：聊天记录模式自动回退为自行选题，纯日报内容模式直接报错。"
          >
            <Select
              options={[
                { label: "不跟随日报（自行选题）", value: 0 },
                ...reportTasks
                  .filter((item) => item.id !== initialValues?.id)
                  .map((item) => ({ label: item.name, value: item.id }))
              ]}
              placeholder="选择要跟随的日报任务"
            />
          </Form.Item>
        ) : null}
        {isTopicCardTask || isImageCardTask ? (
          <Form.Item
            label="卡片输入来源"
            name="card_input_source"
            tooltip="聊天记录：拉取群聊记录作为模型输入（默认，行为与旧版一致）。纯日报内容：不拉聊天记录，直接使用上游日报中每个深度话题的完整内容（背景/讨论/解决方案/金句）作为模型输入，日报缺失或超期时任务直接报错。"
          >
            <Select
              options={[
                { label: "聊天记录（拉取群聊记录生成卡片）", value: "chatlog" },
                { label: "纯日报内容（使用上游日报话题内容，不拉聊天记录）", value: "report" }
              ]}
            />
          </Form.Item>
        ) : null}
        {(isTopicCardTask || isImageCardTask) && cardInputSource === "chatlog" ? (
          <Typography.Paragraph type="secondary" style={{ marginTop: -8, marginBottom: 16 }}>
            当前为聊天记录模式：若上方选择了上游日报任务，会把日报的话题标题清单注入提示词，卡片话题与日报一一对应。
          </Typography.Paragraph>
        ) : null}
        {(isTopicCardTask || isImageCardTask) && cardInputSource === "report" ? (
          <Typography.Paragraph type="secondary" style={{ marginTop: -8, marginBottom: 16 }}>
            当前为纯日报内容模式：建议搭配「日报话题案例卡（纯日报内容）」提示词模板使用。
          </Typography.Paragraph>
        ) : null}
        {isTopicCardTask ? (
          <div style={{ marginBottom: 16, padding: 14, border: "1px solid #f0f0f0", borderRadius: 8, background: "#fafafa" }}>
            <Space align="center" style={{ marginBottom: 8 }}>
              <Typography.Text strong>话题样式配置</Typography.Text>
              <Tooltip title="查看四种话题卡片风格">
                <Button type="text" size="small" icon={<InfoCircleOutlined />} onClick={() => setStylePreviewOpen(true)} />
              </Tooltip>
            </Space>
            <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
              这里配置固定四类话题分别使用哪个版式和主题色。历史任务和新增任务都会默认使用当前映射。
            </Typography.Paragraph>
            <div style={{ display: "grid", gap: 10 }}>
              {TOPIC_TYPE_OPTIONS.map((topic) => (
                <div
                  key={topic.key}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "minmax(260px, 1fr) minmax(180px, 210px) minmax(170px, 190px)",
                    gap: 12,
                    alignItems: "center",
                    padding: 12,
                    border: "1px solid #f0f0f0",
                    borderRadius: 8,
                    background: "#fff"
                  }}
                >
                  <div style={{ minWidth: 0 }}>
                    <Typography.Text strong>{topic.label}</Typography.Text>
                    <Typography.Text type="secondary" style={{ display: "block", fontSize: 12 }}>
                      {topic.desc}
                    </Typography.Text>
                  </div>
                  <Form.Item name={["topic_style_config", topic.key, "style_key"]} noStyle>
                    <Select options={STYLE_OPTIONS} style={{ width: "100%" }} />
                  </Form.Item>
                  <Form.Item name={["topic_style_config", topic.key, "theme"]} noStyle>
                    <Select
                      style={{ width: "100%" }}
                      options={THEME_OPTIONS.map((theme) => ({
                        value: theme.value,
                        label: (
                          <Space size={6}>
                            <span
                              style={{
                                display: "inline-block",
                                width: 10,
                                height: 10,
                                borderRadius: 999,
                                background: theme.color
                              }}
                            />
                            {theme.label}
                          </Space>
                        )
                      }))}
                    />
                  </Form.Item>
                </div>
              ))}
            </div>
          </div>
        ) : null}
        {!isExportTask ? (
          <>
            <Form.Item
              label="提示词模板"
              required
              tooltip={
                isImageCardTask
                  ? "供文本模型生成 Markdown 中间产物；图片提示词模板在作业的图片卡片配置中选择。"
                  : "供文本模型处理聊天记录。"
              }
            >
              <Select
                value={selectedTemplateId ?? undefined}
                options={templateOptions}
                loading={templatesLoading}
                placeholder={templatesLoading ? "加载中..." : "请选择提示词模板"}
                onChange={handleTemplateChange}
                allowClear
                dropdownRender={(menu) => (
                  <>
                    {menu}
                    <div style={{ padding: 8 }}>
                      <Button type="link" onClick={() => setTemplateModalOpen(true)} block>
                        [+] 新建提示词
                      </Button>
                    </div>
                  </>
                )}
              />
            </Form.Item>
            <Form.Item label="提示词内容" name="prompt" rules={[{ required: true, message: "请输入提示词" }]}>
              <Input.TextArea placeholder="请输入提示词" autoSize={{ minRows: 4, maxRows: 10 }} />
            </Form.Item>
            <Form.Item
              label="自定义系统提示词"
              name="system_prompt_custom_enabled"
              valuePropName="checked"
              tooltip="开启后可自定义系统提示词，支持 ${time_range}、${chatroom_name}、${message_count}。"
            >
              <Switch />
            </Form.Item>
            {customPromptEnabled ? (
              <>
                <Form.Item
                  label="附加群消息总数参数开关"
                  name="system_prompt_include_message_count"
                  valuePropName="checked"
                  tooltip="开启后会在系统提示词中追加消息总数参数，并在执行时自动计算消息条数。"
                >
                  <Switch
                    onChange={(checked) => {
                      if (checked && !form.getFieldValue("system_prompt_template")?.includes("${message_count}")) {
                        const current = form.getFieldValue("system_prompt_template") || "";
                        form.setFieldsValue({
                          system_prompt_template: `${current}\n消息总数: \${message_count}`.trim()
                        });
                      }
                    }}
                  />
                </Form.Item>
                <Form.Item
                  label="系统提示词模板"
                  name="system_prompt_template"
                  rules={[{ required: true, message: "请输入系统提示词模板" }]}
                >
                  <Input.TextArea
                    placeholder="支持 ${time_range} / ${chatroom_name} / ${message_count}"
                    autoSize={{ minRows: 4, maxRows: 8 }}
                  />
                </Form.Item>
                <Text type="secondary">
                  调用顺序：聊天记录 → 系统提示词 → 任务提示词。聊天记录放前面，更利于多个作业共用同一份记录时命中 AI 缓存；未开启该开关时，作业层的消息统计仍可独立导出。
                </Text>
              </>
            ) : null}
            <ModelSequenceList
              name="model_sequence"
              entityLabel="模型"
              title="模型执行顺序"
              tooltip="第一行是主模型，后面的行是备用模型。失败后会按顺序重试；AI 总请求次数 = 1 + 作业最大重试次数。"
              options={modelOptions}
            />
            {isImageCardTask ? (
              <ModelSequenceList
                name="image_model_sequence"
                entityLabel="图片模型"
                title="图片模型执行顺序"
                tooltip="第一行是主图片模型，后面的行是备用图片模型。某张图片生成失败时会按顺序切换模型重试；序列里的模型必须是在模型配置中类型为「图片」的模型。"
                options={imageModelOptions}
              />
            ) : null}
          </>
        ) : null}
        <Form.Item label="群聊名称" name="talkers" tooltip="可搜索群聊名称或备注，支持多选。">
          <Select {...chatroomSelectProps} />
        </Form.Item>
        {!isExportTask ? (
          <Form.Item label="推送 Webhook ID" name="push_webhook_ids" tooltip="任务执行成功后需要推送的 Webhook，可多选。">
            <Select mode="multiple" placeholder="请选择推送渠道" options={webhookOptions} optionFilterProp="label" allowClear />
          </Form.Item>
        ) : null}
        <Form.Item label="告警 Webhook ID" name="alert_webhook_ids" tooltip="执行失败告警推送渠道，可多选。">
          <Select mode="multiple" placeholder="请选择告警渠道" options={webhookOptions} optionFilterProp="label" allowClear />
        </Form.Item>
        <Form.Item label="启用状态" name="is_active" valuePropName="checked">
          <Switch />
        </Form.Item>
      </Form>
      <PromptTemplateModal
        open={templateModalOpen}
        initialValues={null}
        templateType="regular"
        confirmLoading={templateModalLoading}
        onSubmit={handleTemplateModalSubmit}
        onCancel={() => setTemplateModalOpen(false)}
      />
      <Modal
        open={stylePreviewOpen}
        title="话题卡片风格预览"
        footer={null}
        width={1280}
        onCancel={() => setStylePreviewOpen(false)}
      >
        <Typography.Paragraph type="secondary">
          这里展示四种实际卡片版式。任务配置里改的是“话题类型 → 版式/主题色”的默认映射。
        </Typography.Paragraph>
        <div style={{ display: "flex", gap: 18, overflowX: "auto", paddingBottom: 12, alignItems: "flex-start" }}>
          {STYLE_PREVIEWS.map((item) => (
            <StylePreviewCard key={item.key} item={item} />
          ))}
        </div>
      </Modal>
    </Modal>
  );
}

export default TaskFormModal;
