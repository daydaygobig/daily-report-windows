/**
 * 备份聊天记录分区。从 JobFormModal 拆出，逻辑原样搬移。
 */
import { Form, Input, InputNumber, Select, Switch } from "antd";
import { getTemplateTooltip, renderTemplateExample } from "../constants";

function ChatlogBackupSection() {
  const form = Form.useFormInstance();
  const chatlogBackupEnabled = Form.useWatch("chatlog_backup_enabled", form);

  return (
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
}

export default ChatlogBackupSection;
