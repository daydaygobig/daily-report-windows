/**
 * 高级配置分区。从 JobFormModal 拆出，逻辑原样搬移。
 */
import { DatePicker, Form, Input } from "antd";

function AdvancedSection() {
  return (
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
}

export default AdvancedSection;
