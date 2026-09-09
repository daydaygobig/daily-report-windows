/**
 * 作业表单共用常量与说明文案。从 JobFormModal 拆出，内容原样搬移。
 */
import { Space, Typography } from "antd";

const { Text } = Typography;

export const scheduleOptions = [
  { label: "每日执行", value: "daily" },
  { label: "工作日执行", value: "weekday" },
  { label: "周末执行", value: "weekend" },
  { label: "自定义周几", value: "weekly" },
  { label: "手动执行", value: "manual" },
  { label: "周报模式", value: "weekly_report" },
  { label: "自定义 Cron", value: "custom_cron" }
];

export const weekdayOptions = [
  { label: "周一", value: 0 },
  { label: "周二", value: 1 },
  { label: "周三", value: 2 },
  { label: "周四", value: 3 },
  { label: "周五", value: 4 },
  { label: "周六", value: 5 },
  { label: "周日", value: 6 }
];

export const getTemplateTooltip = () => (
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

export const getMessageStatsGithubTooltip = () => (
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

export const renderTemplateExample = (example: string) => (
  <Space direction="vertical" size={2}>
    <Text type="secondary">{example}</Text>
  </Space>
);
