/**
 * 本地 HTML 备份分区。从 JobFormModal 拆出，逻辑原样搬移。
 */
import { Form, Input, InputNumber, Switch } from "antd";
import { getTemplateTooltip, renderTemplateExample } from "../constants";

function HtmlBackupSection() {
  const form = Form.useFormInstance();
  const htmlBackupEnabled = Form.useWatch("html_backup_enabled", form);
  const isWeeklyReport = Form.useWatch("schedule_type", form) === "weekly_report";

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
}

export default HtmlBackupSection;
