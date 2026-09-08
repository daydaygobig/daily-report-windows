import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Form, Input, InputNumber, Modal, Select, Space, Spin, Switch, Tooltip, Typography, message } from "antd";
import type { SelectProps } from "antd";
import type { Task, TaskPayload, TopicStyleConfig, TopicStyleKey, TopicThemeKey, TopicTypeKey } from "../services/tasks";
import { fetchTasks } from "../services/tasks";
import { fetchModels } from "../services/models";
import { fetchChatrooms } from "../services/chatRecords";
import { fetchWebhooks } from "../services/webhooks";
import type { PromptTemplate, PromptTemplatePayload } from "../services/promptTemplates";
import { createPromptTemplate, fetchPromptTemplates } from "../services/promptTemplates";
import PromptTemplateModal from "./PromptTemplateModal";
import { ArrowDownOutlined, ArrowUpOutlined, DeleteOutlined, InfoCircleOutlined, PlusOutlined } from "@ant-design/icons";

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


const DEFAULT_TOPIC_STYLE_CONFIG: TopicStyleConfig = {
  industry_business: { style_key: "style_a", theme: "amber" },
  work_methods: { style_key: "style_b", theme: "blue" },
  career_growth: { style_key: "style_c", theme: "green" },
  mind_wellbeing: { style_key: "style_d", theme: "neutral" }
};

const TOPIC_TYPE_OPTIONS: Array<{ key: TopicTypeKey; label: string; desc: string }> = [
  { key: "industry_business", label: "行业商业", desc: "行业趋势、商业逻辑、组织管理、宏观经营" },
  { key: "work_methods", label: "工作方法", desc: "项目推进、沟通协作、效率工具、流程方法" },
  { key: "career_growth", label: "求职发展", desc: "职业规划、求职面试、技能提升、转型路径" },
  { key: "mind_wellbeing", label: "心理认知", desc: "职场心理、精力管理、情绪压力、习惯认知和兜底话题" }
];

const STYLE_OPTIONS: Array<{ label: string; value: TopicStyleKey }> = [
  { label: "极简线框", value: "style_a" },
  { label: "温暖气泡", value: "style_b" },
  { label: "快报嵌套", value: "style_c" },
  { label: "兜底毛玻璃", value: "style_d" }
];

const THEME_OPTIONS: Array<{ label: string; value: TopicThemeKey; color: string; light: string; dark: string; bg: string }> = [
  { label: "琥珀橙", value: "amber", color: "#f59e0b", light: "#fef3c7", dark: "#b45309", bg: "#fffbeb" },
  { label: "靛蓝", value: "blue", color: "#2563eb", light: "#dbeafe", dark: "#1d4ed8", bg: "#eff6ff" },
  { label: "翠绿", value: "green", color: "#10b981", light: "#d1fae5", dark: "#047857", bg: "#f0fdf4" },
  { label: "中性紫", value: "neutral", color: "#6366f1", light: "#e0e7ff", dark: "#4338ca", bg: "#f5f3ff" }
];

const normalizeTopicStyleConfig = (value?: Partial<TopicStyleConfig> | null): TopicStyleConfig => {
  const next = { ...DEFAULT_TOPIC_STYLE_CONFIG } as TopicStyleConfig;
  TOPIC_TYPE_OPTIONS.forEach((item) => {
    next[item.key] = {
      style_key: value?.[item.key]?.style_key ?? DEFAULT_TOPIC_STYLE_CONFIG[item.key].style_key,
      theme: value?.[item.key]?.theme ?? DEFAULT_TOPIC_STYLE_CONFIG[item.key].theme
    };
  });
  return next;
};

const getTheme = (theme: TopicThemeKey) => THEME_OPTIONS.find((item) => item.value === theme) ?? THEME_OPTIONS[1];

const STYLE_PREVIEWS: Array<{
  key: TopicStyleKey;
  title: string;
  theme: TopicThemeKey;
  tags: string[];
  time: string;
  topicTitle: string;
  initiatorLabel: string;
  initiator: string;
  searchKeyword: string;
  quote: string;
  summary: string;
  points: string[];
  participants: string[];
  highlight: string;
  highlightAuthor: string;
}> = [
  {
    key: "style_a",
    title: "极简线框",
    theme: "amber",
    tags: ["行业分析", "组织管理"],
    time: "11:32 - 13:10",
    topicTitle: "“王道”与“霸道”的组织管理应用",
    initiatorLabel: "提问者",
    initiator: "已设置昵称",
    searchKeyword: "已设置昵称：路线是“王道”，纪律是“霸道”，这段话怎么理解？",
    quote: "“路线是‘王道’，纪律是‘霸道’，这两者都不可少。”",
    summary: "群友围绕管理概念层层拆解，认为方向、纪律和组织共识是一组相互补足的管理工具。",
    points: ["战略方向需要先统一，执行纪律负责把方向落地。", "组织管理不能只靠理念，也不能只靠强制规则。"],
    participants: ["已设置昵称", "老默", "AA昍"],
    highlight: "王道是用来统一思想和凝聚队伍的，霸道是保证执行不变形的。",
    highlightAuthor: "AA昍"
  },
  {
    key: "style_b",
    title: "温暖气泡",
    theme: "blue",
    tags: ["工作方法", "产品实操"],
    time: "22:00 - 23:30",
    topicTitle: "To B 产品经理如何找到目标感？",
    initiatorLabel: "求助者",
    initiator: "时光",
    searchKeyword: "时光：有没有推荐的产品课？想补一补产品经理的实操能力。",
    quote: "“想找产品课，解决缺目标感和缺实操的问题。”",
    summary: "讨论从课程推荐转向真实业务训练，大家认为产品能力要回到业务一线、数据验证和利益相关方。",
    points: ["先去业务一线，戳破“伪需求”。", "用真实数据验证假设，不靠感觉判断优先级。"],
    participants: ["时光", "Suerte", "王智慧"],
    highlight: "真正的答案和方向，往往藏在一线业务和真实客户反馈里。",
    highlightAuthor: "王智慧"
  },
  {
    key: "style_c",
    title: "快报嵌套",
    theme: "green",
    tags: ["求职发展", "Offer选择"],
    time: "14:20 - 15:00",
    topicTitle: "手握保底 Offer，如何争取心仪公司？",
    initiatorLabel: "求助者",
    initiator: "阿豆",
    searchKeyword: "阿豆：已经有保底 Offer，但更想等心仪公司，这种情况怎么争取？",
    quote: "“不是反问哈，我想问问这种情况应该怎么争取比较好。”",
    summary: "阿豆收到保底 Offer 后想继续争取目标公司，群友建议主动沟通、说明期限，并把求职看成双向选择。",
    points: ["求职是双向选择，不要只等对方挑你。", "可以告知已有 Offer 和期限，但措辞要柔和专业。"],
    participants: ["阿豆", "今天是叶子", "艾尔"],
    highlight: "你想去又不争取，等着人家来挑你，这是双向选择，不是挑菜。",
    highlightAuthor: "今天是叶子"
  },
  {
    key: "style_d",
    title: "兜底毛玻璃",
    theme: "neutral",
    tags: ["心理认知", "思维模型"],
    time: "10:29 - 11:00",
    topicTitle: "用“三阶分析法”看懂政策背后",
    initiatorLabel: "提问者",
    initiator: "星际迷航",
    searchKeyword: "星际迷航：这种算不算官僚主义？",
    quote: "“这种算不算官僚主义？”",
    summary: "大家用三阶分析法拆解一刀切政策：先看事实，再换位思考，最后识别背后的真实诉求。",
    points: ["先就事论事，避免一上来贴标签。", "换位理解发布者动机，再判断沟通方式是否失当。"],
    participants: ["星际迷航", "今天是叶子", "静心守拙"],
    highlight: "要求精准审核才是落入陷阱了，根本不存在你想的那个精准。",
    highlightAuthor: "今天是叶子"
  }
];

function StylePreviewCard({ item }: { item: (typeof STYLE_PREVIEWS)[number] }) {
  const theme = getTheme(item.theme);
  const isA = item.key === "style_a";
  const isB = item.key === "style_b";
  const isC = item.key === "style_c";
  const isD = item.key === "style_d";
  const darkHeader = isC || isD;
  const cardBackground =
    isB
      ? `linear-gradient(180deg, ${theme.bg} 0%, #ffffff 80%)`
      : isC
        ? "#f4f5f7"
        : isD
          ? theme.bg
          : "#ffffff";
  const sectionHeader = (num: string, text: string) => (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        alignSelf: "flex-start",
        background: darkHeader ? "#1f2937" : "transparent",
        color: darkHeader ? "#fff" : "#1f2937",
        borderRadius: 4,
        padding: darkHeader ? "4px 8px" : 0,
        fontWeight: 900,
        fontSize: darkHeader ? 12 : 16,
        marginBottom: 12,
        fontFamily: darkHeader ? "inherit" : "serif"
      }}
    >
      <span style={{ color: darkHeader ? "#fff" : theme.color, marginRight: 6, fontFamily: "inherit" }}>{num}</span>
      {text}
    </div>
  );
  const keywordBoxBackground = isC || isD ? "rgba(255,255,255,0.72)" : theme.bg;
  const keywordBoxBorder = isC || isD ? "rgba(255,255,255,0.92)" : theme.light;
  const translucentPanel = isD ? "rgba(255,255,255,0.72)" : "#fff";
  const quoteBoxStyle = {
    background: isB || isC ? "#fff" : isD ? translucentPanel : "transparent",
    border: isA ? "none" : `1px solid ${isD ? "rgba(255,255,255,0.92)" : "#e5e7eb"}`,
    borderLeft: `4px solid ${theme.color}`,
    borderRadius: isB ? 12 : isA ? 0 : 6,
    padding: isA ? "0 0 0 12px" : "12px 14px",
    marginBottom: 24
  };
  const bodyPadding = isA || isB ? 24 : "0 24px 24px";

  return (
    <div
      style={{
        width: 400,
        minHeight: 760,
        flex: "0 0 auto",
        background: cardBackground,
        border: isB ? `2px solid ${theme.light}` : `1px solid ${isD ? theme.light : "#d1d5db"}`,
        borderTop: isA ? "6px solid #111827" : `6px solid ${theme.color}`,
        borderRadius: isB || isA ? (isB ? 16 : 8) : "0 0 8px 8px",
        boxShadow: "0 10px 25px -8px rgba(15, 23, 42, 0.16)",
        overflow: "hidden"
      }}
    >
      <div style={{ padding: isA || isB ? 24 : "20px 24px", background: isC ? "#fff" : "transparent", borderBottom: isC || isD ? "1px solid rgba(0,0,0,0.06)" : undefined }}>
        <Typography.Text strong style={{ display: "block", color: theme.dark, marginBottom: 10 }}>
          {item.title}
        </Typography.Text>
        <Typography.Title level={5} style={{ margin: 0, fontFamily: "serif", lineHeight: 1.35 }}>
          {item.topicTitle}
        </Typography.Title>
        <Space size={8} wrap style={{ marginTop: 14 }}>
          {item.tags.map((tag) => (
            <span key={tag} style={{ background: theme.light, color: theme.dark, borderRadius: 4, padding: "2px 8px", fontWeight: 800, fontSize: 12 }}>
              {tag}
            </span>
          ))}
          <Typography.Text type="secondary">{item.time}</Typography.Text>
        </Space>
      </div>
      <div style={{ padding: bodyPadding }}>
        <div
          style={{
            background: keywordBoxBackground,
            border: `1px solid ${keywordBoxBorder}`,
            borderRadius: 8,
            color: theme.dark,
            fontSize: 12,
            padding: "8px 12px",
            marginBottom: 24,
            lineHeight: 1.6
          }}
        >
          <Typography.Text strong style={{ color: theme.dark }}>爬楼关键词：</Typography.Text>
          {item.searchKeyword}
        </div>

        {sectionHeader("01", "抛出探讨")}
        <div style={quoteBoxStyle}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <Typography.Text strong type="secondary" style={{ fontSize: 12 }}>
              {item.initiatorLabel}
            </Typography.Text>
            <span style={{ background: "#1f2937", color: "#fff", borderRadius: 6, padding: "2px 8px", fontWeight: 800, fontSize: 12 }}>
              {item.initiator}
            </span>
          </div>
          <Typography.Paragraph style={{ margin: 0, fontWeight: 700, lineHeight: 1.7 }}>
            “{item.quote}”
          </Typography.Paragraph>
        </div>

        {sectionHeader("02", "话题总结")}
        <div style={{ background: isD ? translucentPanel : isA ? "transparent" : "#fff", border: isA ? "none" : "1px solid #e5e7eb", borderRadius: 8, padding: isA ? 0 : 14, marginBottom: 24 }}>
          <Typography.Paragraph style={{ margin: 0, lineHeight: 1.75 }}>{item.summary}</Typography.Paragraph>
        </div>

        {sectionHeader("03", "大家怎么说")}
        <div
          style={{
            display: "grid",
            gap: isC ? 8 : 10,
            background: isD ? translucentPanel : "transparent",
            border: isD ? "1px solid rgba(255,255,255,0.92)" : "none",
            borderRadius: 8,
            padding: isD ? 14 : 0,
            marginBottom: 20
          }}
        >
          {item.points.map((text, index) => (
            <div
              key={text}
              style={{
                display: "flex",
                gap: 10,
                alignItems: "flex-start",
                background: isC ? "#fff" : "transparent",
                border: isC ? "1px solid #e5e7eb" : "none",
                borderRadius: 6,
                padding: isC ? "10px 12px" : 0
              }}
            >
              <Typography.Text strong style={{ color: theme.color, marginRight: 8 }}>{index + 1}</Typography.Text>
              <Typography.Text style={{ lineHeight: 1.65 }}>{text}</Typography.Text>
            </div>
          ))}
        </div>

        <div style={{ display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 24 }}>
          <Typography.Text strong type="secondary" style={{ whiteSpace: "nowrap" }}>参与者：</Typography.Text>
          <Space size={6} wrap>
            {item.participants.map((name) => (
              <span key={name} style={{ background: isD ? "rgba(255,255,255,0.72)" : "#fff", border: "1px solid #e5e7eb", borderRadius: 5, padding: "2px 8px", fontWeight: 700, color: "#4b5563", fontSize: 12 }}>{name}</span>
            ))}
          </Space>
        </div>

        <div style={{ position: "relative", background: isD ? translucentPanel : theme.bg, border: `1px solid ${isD ? "rgba(255,255,255,0.92)" : theme.light}`, borderTop: isA ? "1px solid #e5e7eb" : undefined, borderRadius: isB ? 12 : 6, padding: isA ? "16px 0 0 22px" : 16, marginTop: isA ? 8 : 0 }}>
          {(isA || isB || isD) ? (
            <span
              style={{
                position: "absolute",
                left: isA ? -8 : 16,
                top: isA ? -5 : 8,
                fontSize: isD ? 60 : 48,
                fontFamily: "serif",
                color: isD ? theme.color : theme.dark,
                opacity: isD ? 0.1 : 0.12,
                lineHeight: 1
              }}
            >
              "
            </span>
          ) : null}
          <div style={{ position: "relative", zIndex: 1 }}>
            <Typography.Text strong style={{ color: theme.dark, display: "block", marginBottom: 8 }}>高光时刻</Typography.Text>
            <Typography.Paragraph style={{ margin: "0 0 12px", fontWeight: 700, lineHeight: 1.75 }}>{item.highlight}</Typography.Paragraph>
            <Typography.Text strong style={{ display: "block", textAlign: "right", color: theme.dark }}>
              — {item.highlightAuthor}
            </Typography.Text>
          </div>
        </div>
      </div>
    </div>
  );
}
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
        const selectedTalkers = talkers && talkers.length ? talkers : form.getFieldValue("talkers") ?? [];
        const selectedNames = form.getFieldValue("talker_names") ?? [];
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

  const chatroomSelectProps: SelectProps<string[], string> = {
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
            <Form.List name="model_sequence">
              {(fields, { add, remove, move }) => (
                <div style={{ marginBottom: 16 }}>
                  <Space align="center" style={{ marginBottom: 8 }}>
                    <Typography.Text strong>模型执行顺序</Typography.Text>
                    <Tooltip title="第一行是主模型，后面的行是备用模型。失败后会按顺序重试；AI 总请求次数 = 1 + 作业最大重试次数。">
                      <InfoCircleOutlined />
                    </Tooltip>
                  </Space>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "48px minmax(260px, 1fr) 150px 116px",
                      gap: 8,
                      marginBottom: 6,
                      color: "rgba(0, 0, 0, 0.45)",
                      fontSize: 12
                    }}
                  >
                    <span>顺序</span>
                    <span>模型</span>
                    <span>最多执行次数</span>
                    <span>操作</span>
                  </div>
                  <div style={{ display: "grid", gap: 8 }}>
                    {fields.map((field, index) => (
                      <div
                        key={field.key}
                        style={{
                          display: "grid",
                          gridTemplateColumns: "48px minmax(260px, 1fr) 150px 116px",
                          gap: 8,
                          alignItems: "center"
                        }}
                      >
                        <Typography.Text type="secondary">#{index + 1}</Typography.Text>
                        <Form.Item
                          {...field}
                          name={[field.name, "model_id"]}
                          rules={[{ required: true, message: "请选择模型" }]}
                          style={{ marginBottom: 0 }}
                        >
                          <Select showSearch placeholder={index === 0 ? "请选择主模型" : "请选择备用模型"} options={modelOptions} optionFilterProp="label" />
                        </Form.Item>
                        <Form.Item
                          {...field}
                          name={[field.name, "max_attempts"]}
                          rules={[{ required: true, message: "请输入次数" }]}
                          style={{ marginBottom: 0 }}
                        >
                          <InputNumber min={1} placeholder="次数" style={{ width: "100%" }} />
                        </Form.Item>
                        <Space size={4}>
                          <Tooltip title="上移">
                            <Button size="small" icon={<ArrowUpOutlined />} disabled={index === 0} onClick={() => move(index, index - 1)} />
                          </Tooltip>
                          <Tooltip title="下移">
                            <Button size="small" icon={<ArrowDownOutlined />} disabled={index === fields.length - 1} onClick={() => move(index, index + 1)} />
                          </Tooltip>
                          <Tooltip title="删除">
                            <Button size="small" icon={<DeleteOutlined />} disabled={fields.length <= 1} onClick={() => remove(field.name)} />
                          </Tooltip>
                        </Space>
                      </div>
                    ))}
                  </div>
                  <Button
                    type="dashed"
                    icon={<PlusOutlined />}
                    style={{ marginTop: 10 }}
                    onClick={() => add({ model_id: undefined, max_attempts: 2 })}
                  >
                    添加备用模型
                  </Button>
                </div>
              )}
            </Form.List>
            {isImageCardTask ? (
              <Form.List name="image_model_sequence">
                {(fields, { add, remove, move }) => (
                  <div style={{ marginBottom: 16 }}>
                    <Space align="center" style={{ marginBottom: 8 }}>
                      <Typography.Text strong>图片模型执行顺序</Typography.Text>
                      <Tooltip title="第一行是主图片模型，后面的行是备用图片模型。某张图片生成失败时会按顺序切换模型重试；序列里的模型必须是在模型配置中类型为「图片」的模型。">
                        <InfoCircleOutlined />
                      </Tooltip>
                    </Space>
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "48px minmax(260px, 1fr) 150px 116px",
                        gap: 8,
                        marginBottom: 6,
                        color: "rgba(0, 0, 0, 0.45)",
                        fontSize: 12
                      }}
                    >
                      <span>顺序</span>
                      <span>图片模型</span>
                      <span>最多执行次数</span>
                      <span>操作</span>
                    </div>
                    <div style={{ display: "grid", gap: 8 }}>
                      {fields.map((field, index) => (
                        <div
                          key={field.key}
                          style={{
                            display: "grid",
                            gridTemplateColumns: "48px minmax(260px, 1fr) 150px 116px",
                            gap: 8,
                            alignItems: "center"
                          }}
                        >
                          <Typography.Text type="secondary">#{index + 1}</Typography.Text>
                          <Form.Item
                            {...field}
                            name={[field.name, "model_id"]}
                            rules={[{ required: true, message: "请选择图片模型" }]}
                            style={{ marginBottom: 0 }}
                          >
                            <Select
                              showSearch
                              placeholder={index === 0 ? "请选择主图片模型" : "请选择备用图片模型"}
                              options={imageModelOptions}
                              optionFilterProp="label"
                            />
                          </Form.Item>
                          <Form.Item
                            {...field}
                            name={[field.name, "max_attempts"]}
                            rules={[{ required: true, message: "请输入次数" }]}
                            style={{ marginBottom: 0 }}
                          >
                            <InputNumber min={1} placeholder="次数" style={{ width: "100%" }} />
                          </Form.Item>
                          <Space size={4}>
                            <Tooltip title="上移">
                              <Button size="small" icon={<ArrowUpOutlined />} disabled={index === 0} onClick={() => move(index, index - 1)} />
                            </Tooltip>
                            <Tooltip title="下移">
                              <Button size="small" icon={<ArrowDownOutlined />} disabled={index === fields.length - 1} onClick={() => move(index, index + 1)} />
                            </Tooltip>
                            <Tooltip title="删除">
                              <Button size="small" icon={<DeleteOutlined />} disabled={fields.length <= 1} onClick={() => remove(field.name)} />
                            </Tooltip>
                          </Space>
                        </div>
                      ))}
                    </div>
                    <Button
                      type="dashed"
                      icon={<PlusOutlined />}
                      style={{ marginTop: 10 }}
                      onClick={() => add({ model_id: undefined, max_attempts: 2 })}
                    >
                      添加备用图片模型
                    </Button>
                  </div>
                )}
              </Form.List>
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
