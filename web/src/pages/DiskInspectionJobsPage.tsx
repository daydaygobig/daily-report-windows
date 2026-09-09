import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Form,
  Input,
  InputNumber,
  message,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { QuestionCircleOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import {
  createDiskInspectionJob,
  deleteDiskInspectionJob,
  fetchDiskInspectionJobs,
  runDiskInspectionJob,
  updateDiskInspectionJob,
  type DiskInspectionJob,
  type DiskInspectionJobPayload,
} from "../services/diskMonitor";
import { fetchWebhooks } from "../services/webhooks";
import { formatBeijingDateTime } from "../utils/datetime";
import { BytesText } from "./DiskIoRecordsPage";
import { getErrorMessage } from "../services/apiClient";

const { Text } = Typography;

type FormValues = Omit<DiskInspectionJobPayload, "threshold_bytes"> & {
  threshold_mb: number;
};

const defaultValues: FormValues = {
  name: "",
  is_enabled: true,
  schedule_type: "daily",
  schedule_time: "09:00",
  schedule_weekday: 0,
  schedule_month_day: 1,
  cron_expression: "",
  interval_enabled: false,
  interval_minutes: 120,
  window_start: "00:00",
  window_end: "24:00",
  window_hours: 24,
  threshold_mb: 100,
  webhook_ids: [],
  cooldown_hours: 6,
  weflow_process_names: "",
};

const scheduleTypeLabel: Record<string, string> = {
  daily: "每天",
  weekly: "每周",
  monthly: "每月",
  custom_cron: "自定义 Cron",
  manual: "手动巡检",
};

const weekdayOptions = [
  { label: "周一", value: 0 },
  { label: "周二", value: 1 },
  { label: "周三", value: 2 },
  { label: "周四", value: 3 },
  { label: "周五", value: 4 },
  { label: "周六", value: 5 },
  { label: "周日", value: 6 },
];

const buildScheduleSummary = (record: Pick<
  DiskInspectionJob,
  | "schedule_type"
  | "schedule_time"
  | "cron_expression"
  | "interval_enabled"
  | "interval_minutes"
  | "window_start"
  | "window_end"
>) => {
  if (record.schedule_type === "manual") {
    return "仅手动执行";
  }
  if (record.schedule_type === "custom_cron") {
    return record.cron_expression || "-";
  }
  if (record.interval_enabled) {
    return `${record.window_start} - ${record.window_end}，每 ${record.interval_minutes ?? 120} 分钟`;
  }
  return record.schedule_time;
};

function DiskInspectionJobsPage() {
  const [form] = Form.useForm<FormValues>();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<DiskInspectionJob | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const scheduleType = Form.useWatch("schedule_type", form);
  const intervalEnabled = Form.useWatch("interval_enabled", form);

  const jobsQuery = useQuery({ queryKey: ["disk-inspection-jobs"], queryFn: fetchDiskInspectionJobs });
  const webhooksQuery = useQuery({
    queryKey: ["webhooks", "disk-inspection"],
    queryFn: fetchWebhooks,
    staleTime: 60_000,
  });

  const invalidateJobs = () => queryClient.invalidateQueries({ queryKey: ["disk-inspection-jobs"] });

  const createMutation = useMutation({
    mutationFn: createDiskInspectionJob,
    onSuccess: () => {
      message.success("巡检任务已保存");
      setModalOpen(false);
      invalidateJobs();
    },
    onError: (error) => message.error(getErrorMessage(error, "巡检任务保存失败")),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: DiskInspectionJobPayload }) =>
      updateDiskInspectionJob(id, payload),
    onSuccess: () => {
      message.success("巡检任务已保存");
      setModalOpen(false);
      invalidateJobs();
    },
    onError: (error) => message.error(getErrorMessage(error, "巡检任务保存失败")),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteDiskInspectionJob,
    onSuccess: () => {
      message.success("巡检任务已删除");
      invalidateJobs();
    },
    onError: (error) => message.error(getErrorMessage(error, "巡检任务删除失败")),
  });

  const runMutation = useMutation({
    mutationFn: runDiskInspectionJob,
    onSuccess: () => {
      message.success("巡检已完成，可到巡检日志查看结果");
      queryClient.invalidateQueries({ queryKey: ["disk-inspection-runs"] });
      invalidateJobs();
    },
    onError: (error) => message.error(getErrorMessage(error, "手动巡检失败")),
  });

  const openCreate = () => {
    setEditing(null);
    form.setFieldsValue(defaultValues);
    setModalOpen(true);
  };

  const openEdit = (record: DiskInspectionJob) => {
    setEditing(record);
    form.setFieldsValue({
      ...record,
      threshold_mb: Math.max(1, Math.round(record.threshold_bytes / 1024 / 1024)),
      cron_expression: record.cron_expression ?? "",
      weflow_process_names: record.weflow_process_names ?? "",
      schedule_weekday: record.schedule_weekday ?? 0,
      schedule_month_day: record.schedule_month_day ?? 1,
      interval_enabled: record.interval_enabled ?? false,
      interval_minutes: record.interval_minutes ?? 120,
      window_start: record.window_start ?? "00:00",
      window_end: record.window_end ?? "24:00",
    });
    setModalOpen(true);
  };

  const buildPayload = (values: FormValues): DiskInspectionJobPayload => {
    const intervalMode = values.interval_enabled && !["manual", "custom_cron"].includes(values.schedule_type);
    return {
      name: values.name.trim(),
      is_enabled: values.is_enabled,
      schedule_type: values.schedule_type,
      schedule_time: intervalMode ? values.window_start || "00:00" : values.schedule_time || "09:00",
      schedule_weekday: values.schedule_type === "weekly" ? values.schedule_weekday ?? 0 : null,
      schedule_month_day: values.schedule_type === "monthly" ? values.schedule_month_day ?? 1 : null,
      cron_expression: values.schedule_type === "custom_cron" ? values.cron_expression?.trim() || null : null,
      interval_enabled: intervalMode,
      interval_minutes: intervalMode ? values.interval_minutes ?? 120 : null,
      window_start: values.window_start || "00:00",
      window_end: values.window_end || "24:00",
      window_hours: values.window_hours,
      threshold_bytes: Math.round(values.threshold_mb * 1024 * 1024),
      webhook_ids: values.webhook_ids ?? [],
      cooldown_hours: values.cooldown_hours,
      weflow_process_names: values.weflow_process_names?.trim() || null,
    };
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    const payload = buildPayload(values);
    if (editing) {
      updateMutation.mutate({ id: editing.id, payload });
      return;
    }
    createMutation.mutate(payload);
  };

  const columns: ColumnsType<DiskInspectionJob> = [
    {
      title: "任务名",
      dataIndex: "name",
      key: "name",
      width: 220,
    },
    {
      title: "状态",
      dataIndex: "is_enabled",
      key: "is_enabled",
      width: 100,
      render: (value) => (value ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>),
    },
    {
      title: "巡检频率",
      key: "schedule",
      width: 320,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Text>{scheduleTypeLabel[record.schedule_type] ?? record.schedule_type}</Text>
          <Text type="secondary">{buildScheduleSummary(record)}</Text>
        </Space>
      ),
    },
    {
      title: "检查窗口",
      dataIndex: "window_hours",
      key: "window_hours",
      width: 120,
      render: (value) => `最近 ${value} 小时`,
    },
    {
      title: "告警阈值",
      dataIndex: "threshold_bytes",
      key: "threshold_bytes",
      width: 120,
      render: (value) => <BytesText value={value} />,
    },
    {
      title: "飞书机器人",
      dataIndex: "webhook_ids",
      key: "webhook_ids",
      width: 120,
      render: (value: number[]) => `${value?.length ?? 0} 个`,
    },
    {
      title: "上次巡检",
      dataIndex: "last_run_at",
      key: "last_run_at",
      width: 180,
      render: (value?: string | null) => formatBeijingDateTime(value),
    },
    {
      title: "下次巡检",
      dataIndex: "next_run_at",
      key: "next_run_at",
      width: 180,
      render: (value?: string | null) => formatBeijingDateTime(value),
    },
    {
      title: "更新时间",
      dataIndex: "updated_at",
      key: "updated_at",
      width: 180,
      render: (value: string) => formatBeijingDateTime(value),
    },
    {
      title: "操作",
      key: "actions",
      fixed: "right",
      width: 260,
      render: (_, record) => (
        <Space wrap>
          <Button type="link" onClick={() => runMutation.mutate(record.id)} loading={runMutation.isPending}>
            手动巡检
          </Button>
          <Button type="link" onClick={() => openEdit(record)}>
            编辑
          </Button>
          <Popconfirm title="确定删除这个巡检任务吗？" onConfirm={() => deleteMutation.mutate(record.id)}>
            <Button type="link" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Space style={{ justifyContent: "space-between", width: "100%" }}>
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>
            巡检任务
          </Typography.Title>
          <Text type="secondary">可以建多个巡检任务，比如每天看最近 24 小时、每月看最近 720 小时。</Text>
        </div>
        <Button type="primary" onClick={openCreate}>
          新增巡检任务
        </Button>
      </Space>

      <Table<DiskInspectionJob>
        rowKey={(record) => record.id}
        loading={jobsQuery.isLoading || jobsQuery.isFetching}
        dataSource={jobsQuery.data ?? []}
        columns={columns}
        pagination={false}
        scroll={{ x: "max-content" }}
        locale={{ emptyText: "暂无巡检任务" }}
      />

      <Modal
        open={modalOpen}
        width={720}
        destroyOnClose
        title={editing ? "编辑巡检任务" : "新增巡检任务"}
        onCancel={() => setModalOpen(false)}
        onOk={handleSubmit}
        confirmLoading={createMutation.isPending || updateMutation.isPending}
      >
        <Form form={form} layout="vertical" initialValues={defaultValues}>
          <Form.Item label="任务名" name="name" rules={[{ required: true, message: "请输入任务名" }]}>
            <Input placeholder="例如：每天磁盘写入巡检" />
          </Form.Item>

          <Form.Item label="是否启用" name="is_enabled" valuePropName="checked">
            <Switch />
          </Form.Item>

          <Form.Item label="巡检频率" name="schedule_type" rules={[{ required: true }]}>
            <Select
              options={[
                { label: "每天", value: "daily" },
                { label: "每周", value: "weekly" },
                { label: "每月", value: "monthly" },
                { label: "自定义 Cron", value: "custom_cron" },
                { label: "手动巡检", value: "manual" },
              ]}
            />
          </Form.Item>

          {scheduleType !== "manual" && scheduleType !== "custom_cron" ? (
            <>
              <Form.Item label="按间隔执行" name="interval_enabled" valuePropName="checked">
                <Switch />
              </Form.Item>

              {!intervalEnabled ? (
                <Form.Item
                  label="执行时间"
                  name="schedule_time"
                  rules={[{ required: true, pattern: /^\d{2}:\d{2}$/, message: "格式示例：09:00" }]}
                >
                  <Input placeholder="09:00" />
                </Form.Item>
              ) : null}
            </>
          ) : null}

          {scheduleType === "weekly" ? (
            <Form.Item label="每周几巡检" name="schedule_weekday">
              <Select options={weekdayOptions} />
            </Form.Item>
          ) : null}

          {scheduleType === "monthly" ? (
            <Form.Item label="每月几号巡检" name="schedule_month_day">
              <InputNumber min={1} max={31} style={{ width: "100%" }} />
            </Form.Item>
          ) : null}

          {scheduleType === "custom_cron" ? (
            <Form.Item label="Cron 表达式" name="cron_expression" rules={[{ required: true, message: "请输入 Cron 表达式" }]}>
              <Input placeholder="例如：0 9 * * *" />
            </Form.Item>
          ) : null}

          {scheduleType !== "manual" && scheduleType !== "custom_cron" && intervalEnabled ? (
            <>
              <Form.Item
                label="生效开始时间"
                name="window_start"
                rules={[{ required: true, pattern: /^\d{2}:\d{2}$/, message: "格式示例：20:00" }]}
                extra="开启按间隔执行后，会从这里开始按间隔续排。"
              >
                <Input placeholder="00:00" />
              </Form.Item>

              <Form.Item
                label="生效结束时间"
                name="window_end"
                rules={[{ required: true, pattern: /^\d{2}:\d{2}$/, message: "格式示例：24:00" }]}
              >
                <Input placeholder="24:00" />
              </Form.Item>

              <Form.Item label="间隔分钟" name="interval_minutes" rules={[{ required: true, message: "请输入间隔分钟" }]}>
                <InputNumber min={1} max={1440} style={{ width: "100%" }} />
              </Form.Item>
            </>
          ) : null}

          <Form.Item label="检查窗口（最近多少小时）" name="window_hours" rules={[{ required: true }]}>
            <InputNumber min={1} style={{ width: "100%" }} />
          </Form.Item>

          <Form.Item
            label="磁盘写入告警阈值（MB）"
            name="threshold_mb"
            rules={[{ required: true }]}
            extra="基于实际落盘文件大小判断，不是进程 IO 计数。"
          >
            <InputNumber min={1} style={{ width: "100%" }} placeholder="单位 MB" />
          </Form.Item>

          <Form.Item label="飞书告警机器人" name="webhook_ids">
            <Select
              mode="multiple"
              allowClear
              loading={webhooksQuery.isLoading}
              placeholder="超过阈值时推送到这些机器人"
              options={(webhooksQuery.data ?? []).map((item) => ({ label: item.name, value: item.id }))}
            />
          </Form.Item>

          <Form.Item
            label={
              <Space size={6}>
                <span>告警冷却时间（小时）</span>
                <Tooltip title="同一个巡检任务在冷却时间内重复超阈值时，不会反复刷屏。">
                  <QuestionCircleOutlined style={{ color: "#8c8c8c" }} />
                </Tooltip>
              </Space>
            }
            name="cooldown_hours"
          >
            <InputNumber min={0} style={{ width: "100%" }} />
          </Form.Item>

          <Form.Item label="WeFlow 进程名（可选）" name="weflow_process_names">
            <Input placeholder="例如：weflow.exe，多个用逗号分隔；留空则使用默认识别" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}

export default DiskInspectionJobsPage;
