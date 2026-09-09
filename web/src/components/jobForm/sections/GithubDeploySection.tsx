/**
 * GitHub 部署分区。从 JobFormModal 拆出，逻辑原样搬移。
 */
import { Button, Form, Input, InputNumber, Select, Switch } from "antd";
import { getTemplateTooltip, renderTemplateExample } from "../constants";
import HtmlBackupSection from "./HtmlBackupSection";

type GithubDeploySectionProps = {
  includeHtmlSubsection: boolean;
  githubConfigOptions: { label: string; value: number }[];
  githubConfigsLoading: boolean;
  onOpenGithubConfigModal: () => void;
};

function GithubDeploySection({
  includeHtmlSubsection,
  githubConfigOptions,
  githubConfigsLoading,
  onOpenGithubConfigModal
}: GithubDeploySectionProps) {
  const form = Form.useFormInstance();
  const githubDeployEnabled = Form.useWatch("github_deploy_enabled", form);
  const isWeeklyReport = Form.useWatch("schedule_type", form) === "weekly_report";

  return (
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
          {includeHtmlSubsection ? <HtmlBackupSection /> : null}
        </>
      ) : null}
    </>
  );
}

export default GithubDeploySection;
