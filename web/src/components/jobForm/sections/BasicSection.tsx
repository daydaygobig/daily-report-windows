/**
 * 基础设置分区。从 JobFormModal 拆出，逻辑原样搬移（表单实例经 Form 上下文获取）。
 */
import { Button, Form, Input, InputNumber, Radio, Select, Space, Switch, Typography } from "antd";
import type { Dayjs } from "dayjs";
import { TimeSelectInput, parseTime } from "../timeUtils";
import { scheduleOptions, weekdayOptions } from "../constants";
import type { JobFormValues } from "../types";

const { Text } = Typography;

function BasicSection() {
  const form = Form.useFormInstance<JobFormValues>();
  const intervalEnabled = Form.useWatch("interval_enabled", form);
  const scheduleTypeValue = Form.useWatch("schedule_type", form);
  const isWeeklyReport = scheduleTypeValue === "weekly_report";
  const isManual = scheduleTypeValue === "manual";

  const setTimeField = (field: "start_time" | "end_time" | "execution_time", time: Dayjs) => {
    form.setFieldsValue({ [field]: time });
  };

  return (
    <>
      <Form.Item name="is_enabled" label="启用" valuePropName="checked">
        <Switch />
      </Form.Item>
      <Form.Item
        name="name"
        label="作业名称"
        tooltip="用于任务列表和飞书消息标题，请保持简洁易懂"
        rules={[
          { required: true, message: "请输入作业名称" },
          { max: 120, message: "名称长度需小于 120 个字符" }
        ]}
      >
        <Input placeholder="请输入作业名称" />
      </Form.Item>
      <Form.Item
        name="schedule_type"
        label="调度类型"
        rules={[{ required: true, message: "请选择调度类型" }]}
      >
        <Select options={scheduleOptions} placeholder="请选择调度类型" />
      </Form.Item>
      {scheduleTypeValue === "custom_cron" ? (
        <Form.Item
          name="cron_expression"
          label="Cron 表达式"
          rules={[{ required: true, message: "请输入 Cron 表达式" }]}
        >
          <Input placeholder="0 9 * * *" />
        </Form.Item>
      ) : null}
      {scheduleTypeValue === "weekly" ? (
        <Form.Item
          name="weekdays"
          label="执行周几"
          rules={[{ required: true, message: "请选择执行周几" }]}
        >
          <Select options={weekdayOptions} mode="multiple" placeholder="请选择周几" />
        </Form.Item>
      ) : null}
      {scheduleTypeValue === "weekly_report" ? (
        <>
          <Form.Item
            name="weekly_report_weekday"
            label="执行周几"
            rules={[{ required: true, message: "请选择执行周几" }]}
          >
            <Select options={weekdayOptions} placeholder="请选择执行周几" />
          </Form.Item>
          <Form.Item
            name="weekly_period"
            label="统计周期"
            rules={[{ required: true, message: "请选择统计周期" }]}
          >
            <Radio.Group
              options={[
                { label: "上一周", value: "previous_week" },
                { label: "当周", value: "current_week" }
              ]}
              optionType="button"
              buttonStyle="solid"
            />
          </Form.Item>
          <Form.Item
            label="时间窗口"
            tooltip="该时间段决定聊天记录的取数范围（北京时间），例如周一0:00 到 周日24:00"
          >
            <Space direction="vertical" style={{ width: "100%" }}>
              <Space align="baseline" wrap>
                <Form.Item
                  name="weekly_start_day"
                  label="开始日"
                  rules={[{ required: true, message: "请选择开始日" }]}
                >
                  <Select options={weekdayOptions} style={{ width: 160 }} />
                </Form.Item>
                <Form.Item
                  name="weekly_start_time_picker"
                  label="时间"
                  rules={[{ required: true, message: "请选择开始时间" }]}
                >
                  <TimeSelectInput minuteStep={5} />
                </Form.Item>
              </Space>
              <Space align="baseline" wrap>
                <Form.Item
                  name="weekly_end_day"
                  label="结束日"
                  rules={[{ required: true, message: "请选择结束日" }]}
                >
                  <Select options={weekdayOptions} style={{ width: 160 }} />
                </Form.Item>
                <Form.Item
                  name="weekly_end_time_picker"
                  label="时间"
                  rules={[{ required: true, message: "请选择结束时间" }]}
                >
                  <TimeSelectInput minuteStep={5} />
                </Form.Item>
              </Space>
              <Text type="secondary">
                提示：日期偏移和文件命名模板会基于该窗口计算 {`{YYYY-MM-DD}`}/{`{week_start}`}/{`{week_end}`}。
              </Text>
            </Space>
          </Form.Item>
        </>
      ) : null}
      {scheduleTypeValue !== "weekly_report" ? (
        <>
          <Form.Item
            name="interval_enabled"
            label="按间隔执行"
            valuePropName="checked"
            tooltip="开启后按照频率循环触发；关闭则仅在固定执行时间运行一次。"
            hidden={isManual}
          >
            <Switch disabled={isManual} />
          </Form.Item>
          {!isManual && intervalEnabled ? (
            <>
              <Form.Item
                name="window_start"
                label="生效范围开始时间"
                tooltip="限定每天允许触发的起始时间"
                rules={[{ required: true, message: "请选择开始时间" }]}
              >
                <TimeSelectInput minuteStep={5} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item
                label="生效范围结束时间"
                tooltip="限定每天允许触发的结束时间，可设为24:00表示当天结束"
                required
              >
                <Space.Compact style={{ width: "100%" }}>
                  <Form.Item
                    name="window_end"
                    noStyle
                    rules={[{ required: true, message: "请选择结束时间" }]}
                  >
                    <TimeSelectInput minuteStep={5} style={{ width: "100%" }} />
                  </Form.Item>
                  <Button type="link" onClick={() => form.setFieldsValue({ window_end: parseTime("14:00") })}>
                    14:00
                  </Button>
                  <Button type="link" onClick={() => form.setFieldsValue({ window_end: parseTime("18:00") })}>
                    18:00
                  </Button>
                  <Button type="link" onClick={() => form.setFieldsValue({ window_end: parseTime("24:00") })}>
                    24:00
                  </Button>
                </Space.Compact>
              </Form.Item>
              <Form.Item
                name="interval_minutes"
                label="间隔频率（分钟）"
                rules={[{ required: true, message: "请输入间隔频率" }]}
              >
                <InputNumber min={5} max={1440} style={{ width: "100%" }} />
              </Form.Item>
            </>
          ) : (
            <>
              <Form.Item
                name="date_baseline"
                label="聊天记录日期基准"
                tooltip="控制聊天记录窗口的日期锚点：以执行时间为基准，选择“当日”则聊天记录开始时间锚定执行当天；选择“前一日”则锚定前一天，适用于跨日窗口（如昨日02:00→今日02:00）。"
                rules={[{ required: true, message: "请选择日期基准" }]}
              >
                <Radio.Group
                  options={[
                    { label: "开始时间当日", value: "current_day" },
                    { label: "开始时间前一日", value: "previous_day" }
                  ]}
                  optionType="button"
                  buttonStyle="solid"
                />
              </Form.Item>
              <Form.Item
                name="start_time"
                label="聊天记录开始时间"
                tooltip="聊天记录拉取窗口的起始时间点，与“聊天记录日期基准”组合确定具体日期。"
                rules={[{ required: true, message: "请选择开始时间" }]}
              >
                <TimeSelectInput minuteStep={5} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item
                label="聊天记录结束时间"
                tooltip="聊天记录拉取窗口的截止时间点；若早于开始时间，系统会自动将结束日期顺延一天。"
                required
              >
                <Space.Compact style={{ width: "100%" }}>
                  <Form.Item name="end_time" noStyle rules={[{ required: true, message: "请选择结束时间" }]}>
                    <TimeSelectInput minuteStep={5} style={{ width: "100%" }} />
                  </Form.Item>
                  <Button type="link" onClick={() => setTimeField("end_time", parseTime("24:00"))}>
                    设为24:00
                  </Button>
                </Space.Compact>
              </Form.Item>
              {!isManual ? (
                <Form.Item label="执行时间" tooltip="作业实际触发的时间点，可早于或晚于窗口结束。" required>
                  <Space.Compact style={{ width: "100%" }}>
                    <Form.Item
                      name="execution_time"
                      noStyle
                      rules={[{ required: true, message: "请选择执行时间" }]}
                    >
                      <TimeSelectInput minuteStep={5} style={{ width: "100%" }} />
                    </Form.Item>
                    <Button type="link" onClick={() => setTimeField("execution_time", parseTime("24:00"))}>
                      设为24:00
                    </Button>
                  </Space.Compact>
                </Form.Item>
              ) : null}
            </>
          )}
        </>
      ) : null}
      <Form.Item
        name="disk_alert_enabled"
        label="磁盘写入告警"
        valuePropName="checked"
        tooltip="开启后会复用当前任务的失败告警机器人通道，在单次作业磁盘写入超过阈值时推送提醒。"
      >
        <Switch />
      </Form.Item>
      <Form.Item
        noStyle
        shouldUpdate={(prev, next) => prev.disk_alert_enabled !== next.disk_alert_enabled}
      >
        {({ getFieldValue }) =>
          getFieldValue("disk_alert_enabled") ? (
            <Form.Item
              name="disk_alert_threshold_mb"
              label="磁盘写入告警阈值（MB）"
              tooltip="按本次作业实际磁盘写入判断，包含导出文件写入；ChatLog 模式还会计入本次解密库写入估算。"
              rules={[{ required: true, message: "请输入磁盘写入告警阈值" }]}
            >
              <InputNumber min={1} max={1024 * 1024} style={{ width: "100%" }} />
            </Form.Item>
          ) : null
        }
      </Form.Item>
      <Form.Item
        name="offset_minutes"
        label="偏移分钟数"
        tooltip="将聊天记录窗口整体向后平移（仅影响数据窗口，不改执行时间）。"
        rules={[{ required: true, message: "请输入偏移分钟数" }]}
      >
        <InputNumber min={0} max={1440} style={{ width: "100%" }} />
      </Form.Item>
      <Form.Item
        name="max_retry"
        label="最大重试次数"
        tooltip="失败后最多再试几次。比如填 3：AI 最多请求 4 次；GitHub 或飞书如果第一次失败，最多再重试 3 次，不会重新生成日报。"
        rules={[{ required: true, message: "请输入重试次数" }]}
      >
        <InputNumber min={0} max={10} style={{ width: "100%" }} />
      </Form.Item>
      <Form.Item
        name="retry_interval_sec"
        label="重试间隔（秒）"
        rules={[{ required: true, message: "请输入重试间隔" }]}
      >
        <InputNumber min={60} step={30} style={{ width: "100%" }} />
      </Form.Item>
    </>
  );
}

export default BasicSection;
