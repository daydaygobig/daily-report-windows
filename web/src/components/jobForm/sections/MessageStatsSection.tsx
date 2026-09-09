/**
 * 群消息统计（含 GitHub 同步子分区）。从 JobFormModal 拆出，逻辑原样搬移。
 */
import { Button, Form, Input, InputNumber, Select, Switch, Typography } from "antd";
import { getMessageStatsGithubTooltip, getTemplateTooltip, renderTemplateExample } from "../constants";

const { Text } = Typography;

type GithubConfigSelectProps = {
  githubConfigOptions: { label: string; value: number }[];
  githubConfigsLoading: boolean;
  onOpenGithubConfigModal: () => void;
};

export function MessageStatsGithubSection({
  githubConfigOptions,
  githubConfigsLoading,
  onOpenGithubConfigModal
}: GithubConfigSelectProps) {
  const form = Form.useFormInstance();
  const messageStatsEnabled = Form.useWatch("message_stats_enabled", form);
  const messageStatsGithubEnabled = Form.useWatch("message_stats_github_enabled", form);
  const isWeeklyReport = Form.useWatch("schedule_type", form) === "weekly_report";

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
              loading={githubConfigsLoading}
              allowClear
              dropdownRender={(menu) => (
                <>
                  {menu}
                  <div style={{ padding: 8 }}>
                    <Button type="link" block onClick={onOpenGithubConfigModal}>
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
}

function MessageStatsSection({
  includeGithubSubsection,
  githubConfigOptions,
  githubConfigsLoading,
  onOpenGithubConfigModal
}: GithubConfigSelectProps & { includeGithubSubsection: boolean }) {
  const form = Form.useFormInstance();
  const messageStatsEnabled = Form.useWatch("message_stats_enabled", form);
  const isWeeklyReport = Form.useWatch("schedule_type", form) === "weekly_report";

  return (
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
          {includeGithubSubsection ? (
            <MessageStatsGithubSection
              githubConfigOptions={githubConfigOptions}
              githubConfigsLoading={githubConfigsLoading}
              onOpenGithubConfigModal={onOpenGithubConfigModal}
            />
          ) : null}
        </>
      ) : null}
    </>
  );
}

export default MessageStatsSection;
