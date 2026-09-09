/**
 * 话题卡片样式：类型映射配置、样式/主题选项与卡片风格预览。
 * 从 TaskFormModal 拆出（数据与组件原样搬移，行为不变）。
 */
import { Space, Typography } from "antd";
import type { TopicStyleConfig, TopicStyleKey, TopicThemeKey, TopicTypeKey } from "../services/tasks";

export const DEFAULT_TOPIC_STYLE_CONFIG: TopicStyleConfig = {
  industry_business: { style_key: "style_a", theme: "amber" },
  work_methods: { style_key: "style_b", theme: "blue" },
  career_growth: { style_key: "style_c", theme: "green" },
  mind_wellbeing: { style_key: "style_d", theme: "neutral" }
};

export const TOPIC_TYPE_OPTIONS: Array<{ key: TopicTypeKey; label: string; desc: string }> = [
  { key: "industry_business", label: "行业商业", desc: "行业趋势、商业逻辑、组织管理、宏观经营" },
  { key: "work_methods", label: "工作方法", desc: "项目推进、沟通协作、效率工具、流程方法" },
  { key: "career_growth", label: "求职发展", desc: "职业规划、求职面试、技能提升、转型路径" },
  { key: "mind_wellbeing", label: "心理认知", desc: "职场心理、精力管理、情绪压力、习惯认知和兜底话题" }
];

export const STYLE_OPTIONS: Array<{ label: string; value: TopicStyleKey }> = [
  { label: "极简线框", value: "style_a" },
  { label: "温暖气泡", value: "style_b" },
  { label: "快报嵌套", value: "style_c" },
  { label: "兜底毛玻璃", value: "style_d" }
];

export const THEME_OPTIONS: Array<{ label: string; value: TopicThemeKey; color: string; light: string; dark: string; bg: string }> = [
  { label: "琥珀橙", value: "amber", color: "#f59e0b", light: "#fef3c7", dark: "#b45309", bg: "#fffbeb" },
  { label: "靛蓝", value: "blue", color: "#2563eb", light: "#dbeafe", dark: "#1d4ed8", bg: "#eff6ff" },
  { label: "翠绿", value: "green", color: "#10b981", light: "#d1fae5", dark: "#047857", bg: "#f0fdf4" },
  { label: "中性紫", value: "neutral", color: "#6366f1", light: "#e0e7ff", dark: "#4338ca", bg: "#f5f3ff" }
];

export const normalizeTopicStyleConfig = (value?: Partial<TopicStyleConfig> | null): TopicStyleConfig => {
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

export const STYLE_PREVIEWS: Array<{
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

export function StylePreviewCard({ item }: { item: (typeof STYLE_PREVIEWS)[number] }) {
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
