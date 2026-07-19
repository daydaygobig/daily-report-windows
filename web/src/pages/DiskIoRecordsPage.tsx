import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Button,
  Card,
  DatePicker,
  Descriptions,
  Empty,
  Form,
  InputNumber,
  Modal,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography
} from "antd";
import type { ColumnsType } from "antd/es/table";
import type { Dayjs } from "dayjs";
import dayjs from "dayjs";
import { useNavigate, useSearchParams } from "react-router-dom";
import { fetchTasks } from "../services/tasks";
import {
  fetchDiskIoAggregate,
  fetchDiskIoRecords,
  fetchDiskIoSummaries,
  type DiskIoAggregate,
  type DiskIoRecord
} from "../services/diskMonitor";
import { formatDateTime } from "../utils/datetime";

const { RangePicker } = DatePicker;
const { Paragraph, Text, Title } = Typography;
const PAGE_SIZE_OPTIONS = ["10", "20", "50", "100"];
const TIME_FORMAT = "YYYY-MM-DD HH:mm";

type FilterState = {
  execution_id?: number;
  task_id?: number;
  job_id?: number;
  provider?: string;
  task_type?: string;
  is_warning?: boolean;
  start_time?: string;
  end_time?: string;
};

type SortState = {
  sort_by?: "disk_write_bytes";
  sort_order?: "asc" | "desc";
};

const summaryColors: Record<string, string> = {
  "最近 24 小时": "#1677ff",
  "最近 7 天": "#52c41a",
  "本月": "#fa8c16",
  "上月": "#8c8c8c",
  "本年度": "#722ed1"
};

const aggregateSummaryColors: Record<string, { color: string; background: string }> = {
  "磁盘写入": { color: "#1677ff", background: "#f0f7ff" },
  "最大单次": { color: "#fa8c16", background: "#fff7e6" },
  "异常次数": { color: "#f5222d", background: "#fff1f0" },
  "平均写入": { color: "#52c41a", background: "#f6ffed" }
};

const formatNumber = (value: number) => {
  if (value === 0) return "0";
  if (Math.abs(value) < 10) return value.toFixed(2);
  if (Math.abs(value) < 100) return value.toFixed(1);
  return Math.round(value).toString();
};

export const formatBytes = (value?: number | null): string => {
  if (value === null || value === undefined) return "-";
  const bytes = Number(value) || 0;
  if (Math.abs(bytes) >= 1024 ** 4) return `${formatNumber(bytes / 1024 ** 4)} TB`;
  if (Math.abs(bytes) >= 1024 ** 3) return `${formatNumber(bytes / 1024 ** 3)} GB`;
  return `${formatNumber(bytes / 1024 ** 2)} MB`;
};

const formatByteTooltip = (value?: number | null) => {
  if (value === null || value === undefined) return "-";
  const bytes = Number(value) || 0;
  return `约 ${formatNumber(bytes / 1024 ** 2)} MB；约 ${formatNumber(bytes / 1024 ** 3)} GB；约 ${formatNumber(bytes / 1024 ** 4)} TB`;
};

export const BytesText = ({ value }: { value?: number | null }) => (
  <Tooltip title={formatByteTooltip(value)}>
    <span>{formatBytes(value)}</span>
  </Tooltip>
);

const renderProvider = (provider: string) => {
  if (provider === "weflow") return <Tag color="blue">WeFlow</Tag>;
  if (provider === "chatlog") return <Tag color="purple">ChatLog</Tag>;
  return <Tag>{provider || "-"}</Tag>;
};

const renderTaskType = (value: string) => {
  if (value === "export") {
    return "数据导出";
  }
  if (value === "topic_card") {
    return "话题卡片";
  }
  return "日报";
};

const processIoTooltip = "此数值为进程 IO 计数（程序层面的读写请求统计），不等于 SSD 实际写入量，不影响磁盘寿命。其中包含网络传输（调用 API、推送消息）、内存操作、日志输出等开销，实际磁盘写入以\"磁盘写入\"字段为准";
const backendWriteTooltip = "非磁盘写入，不影响磁盘寿命。主要是网络传输开销（HTTP 响应、调用 LLM、推送飞书/GitHub 等）";
const backendReadTooltip = "非磁盘读取指标。主要是网络接收开销（接收 WeFlow API 响应等）";
const weflowWriteTooltip = "非磁盘写入，不影响磁盘寿命。主要是通过 HTTP 返回聊天记录数据的网络开销";
const weflowReadTooltip = "非磁盘读取指标。主要是 WeFlow 在内存中解密微信数据库的开销";
const diskWriteTooltip = "WeFlow 模式下是实际导出到磁盘的文件大小；ChatLog 模式下是导出文件大小 + ChatLog 解密库写入估算。";
const diskWriteTooltipForProvider = (provider?: string) => {
  if (provider === "weflow") return "WeFlow 模式：实际导出到磁盘的文件大小。";
  if (provider === "chatlog") return "ChatLog 模式：导出文件大小 + ChatLog 解密库写入估算。";
  return diskWriteTooltip;
};
const diskWriteTooltipForRecord = (provider: string) =>
  provider === "chatlog" ? "ChatLog 模式：导出文件大小 + ChatLog 解密库写入估算。" : "WeFlow 模式：实际导出到磁盘的文件大小。";
const renderChatlogDecryptStatus = (status?: string | null) => {
  if (status === "decrypted") return "已解密";
  if (status === "skipped") return "已跳过";
  if (status === "failed") return "解密失败";
  if (status === "unknown") return "未知";
  return status || "未知";
};
const getDiskWriteBytes = (record: DiskIoRecord) => {
  const diskWrite = Number(record.disk_write_bytes);
  if (Number.isFinite(diskWrite) && diskWrite > 0) return diskWrite;
  const exported = Number(record.exported_file_bytes);
  return Number.isFinite(exported) ? exported : diskWrite;
};

const buildAggregateRange = (key: string): [Dayjs, Dayjs] => {
  const now = dayjs();
  if (key === "thisYear") return [now.startOf("year"), now];
  if (key === "lastYear") return [now.subtract(1, "year").startOf("year"), now.subtract(1, "year").endOf("year")];
  return [now.subtract(30, "day"), now];
};

function SummaryCards({ data }: { data?: Array<{ label: string; total_write_bytes: number; max_single_write_bytes: number; warning_count: number }> }) {
  return (
    <Card size="small" title="磁盘写入量">
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
        {(data ?? []).map((item) => {
          const color = summaryColors[item.label] ?? "#1677ff";
          return (
            <Card key={item.label} size="small" style={{ borderColor: color, borderLeft: `4px solid ${color}` }}>
              <Tooltip title={formatByteTooltip(item.total_write_bytes)}>
                <Statistic title={<Tag color={color}>{item.label}</Tag>} value={formatBytes(item.total_write_bytes)} />
              </Tooltip>
              <Text type="secondary">
                最大单次 <BytesText value={item.max_single_write_bytes} />，异常 {item.warning_count} 次
              </Text>
            </Card>
          );
        })}
      </div>
    </Card>
  );
}

function AggregateTab() {
  const [rangePreset, setRangePreset] = useState("last30");
  const [range, setRange] = useState<[Dayjs, Dayjs]>(() => buildAggregateRange("last30"));
  const aggregateQuery = useQuery({
    queryKey: ["disk-io-aggregate", range[0].format(TIME_FORMAT), range[1].format(TIME_FORMAT)],
    queryFn: () => fetchDiskIoAggregate({ start_time: range[0].format(TIME_FORMAT), end_time: range[1].format(TIME_FORMAT) })
  });

  const data = aggregateQuery.data;
  const maxMonthBytes = Math.max(...(data?.monthly_trend ?? []).map((item) => item.disk_write_bytes), 1);
  const chartWidth = Math.max(320, (data?.monthly_trend?.length ?? 0) * 120);
  const chartHeight = 220;
  const chartPadding = 32;
  const chartPoints = (data?.monthly_trend ?? []).map((item, index, rows) => {
    const x = rows.length <= 1 ? chartWidth / 2 : chartPadding + (index * (chartWidth - chartPadding * 2)) / (rows.length - 1);
    const y = chartHeight - chartPadding - (item.disk_write_bytes / maxMonthBytes) * (chartHeight - chartPadding * 2);
    return { ...item, x, y };
  });
  const polylinePoints = chartPoints.map((item) => `${item.x},${item.y}`).join(" ");
  const summaryCards = data
    ? [
        { label: "磁盘写入", value: data.summary.disk_write_bytes, sub: `执行 ${data.summary.record_count} 次` },
        { label: "最大单次", value: data.summary.max_single_disk_write_bytes, sub: "所选范围内最大磁盘写入" },
        { label: "异常次数", text: `${data.summary.warning_count} 次`, sub: data.summary.record_count ? `异常率 ${formatNumber((data.summary.warning_count / data.summary.record_count) * 100)}%` : "异常率 0%" },
        {
          label: "平均写入",
          value: data.summary.record_count ? Math.round(data.summary.disk_write_bytes / data.summary.record_count) : 0,
          sub: "每次"
        }
      ]
    : [];

  const handlePresetChange = (value: string) => {
    setRangePreset(value);
    if (value !== "custom") {
      setRange(buildAggregateRange(value));
    }
  };

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Space wrap>
        <Select
          value={rangePreset}
          style={{ width: 140 }}
          onChange={handlePresetChange}
          options={[
            { label: "最近 30 天", value: "last30" },
            { label: "今年", value: "thisYear" },
            { label: "去年", value: "lastYear" },
            { label: "自定义", value: "custom" }
          ]}
        />
        <RangePicker
          showTime={{ format: "HH:mm" }}
          format={TIME_FORMAT}
          value={range}
          onChange={(next) => {
            if (next?.[0] && next?.[1]) {
              setRangePreset("custom");
              setRange([next[0], next[1]]);
            }
          }}
          allowClear={false}
        />
      </Space>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
        {summaryCards.map((item) => {
          const style = aggregateSummaryColors[item.label] ?? { color: "#1677ff", background: "#f0f7ff" };
          return (
            <Card
              key={item.label}
              size="small"
              style={{
                flex: "0 1 calc((100% - 48px) / 5)",
                minWidth: 180,
                borderColor: style.color,
                borderLeft: `4px solid ${style.color}`,
                background: style.background
              }}
            >
              {"value" in item ? (
                <Tooltip title={formatByteTooltip(item.value)}>
                  <Statistic title={<Tag color={style.color}>{item.label}</Tag>} value={formatBytes(item.value)} />
                </Tooltip>
              ) : (
                <Statistic title={<Tag color={style.color}>{item.label}</Tag>} value={item.text} />
              )}
              <Text type="secondary">{item.sub}</Text>
            </Card>
          );
        })}
      </div>

      <Card title="月度磁盘写入趋势" loading={aggregateQuery.isLoading || aggregateQuery.isFetching}>
        {(data?.monthly_trend?.length ?? 0) === 0 ? (
          <Empty description="暂无汇总数据" />
        ) : (
          <div style={{ overflowX: "auto", paddingTop: 12 }}>
            <svg width={chartWidth} height={chartHeight + 48} role="img" aria-label="月度磁盘写入趋势折线图">
              <line x1={chartPadding} y1={chartHeight - chartPadding} x2={chartWidth - chartPadding} y2={chartHeight - chartPadding} stroke="#d9d9d9" />
              <line x1={chartPadding} y1={chartPadding} x2={chartPadding} y2={chartHeight - chartPadding} stroke="#d9d9d9" />
              {chartPoints.length > 1 ? <polyline points={polylinePoints} fill="none" stroke="#1677ff" strokeWidth={3} strokeLinejoin="round" strokeLinecap="round" /> : null}
              {chartPoints.map((item) => (
                <Tooltip key={item.month} title={`${item.month}：${formatBytes(item.disk_write_bytes)}，执行 ${item.record_count} 次`}>
                  <g>
                    <circle cx={item.x} cy={item.y} r={5} fill="#1677ff" />
                    <text x={item.x} y={chartHeight + 8} textAnchor="middle" fill="#8c8c8c" fontSize="13">{item.month}</text>
                    <text x={item.x} y={chartHeight + 30} textAnchor="middle" fill="#8c8c8c" fontSize="13">{item.record_count} 次</text>
                  </g>
                </Tooltip>
              ))}
            </svg>
          </div>
        )}
      </Card>

      <Card title="任务磁盘写入排行" loading={aggregateQuery.isLoading || aggregateQuery.isFetching}>
        <Table<DiskIoAggregate["task_ranking"][number]>
          rowKey={(record, index) => `${record.task_name || "-"}-${record.job_name || "-"}-${index}`}
          dataSource={data?.task_ranking ?? []}
          pagination={false}
          locale={{ emptyText: "暂无排行数据" }}
          columns={[
            { title: "排名", width: 80, render: (_, __, index) => index + 1 },
            { title: "任务名", dataIndex: "task_name", render: (value) => value || "-" },
            { title: "作业名", dataIndex: "job_name", render: (value) => value || "-" },
            { title: "执行次数", dataIndex: "record_count", width: 110 },
            { title: "累计磁盘写入", dataIndex: "disk_write_bytes", width: 150, render: (value) => <BytesText value={value} /> },
            { title: "平均单次写入", dataIndex: "avg_disk_write_bytes", width: 150, render: (value) => <BytesText value={value} /> }
          ]}
        />
      </Card>
    </Space>
  );
}

function DiskIoRecordsPage() {
  const [form] = Form.useForm();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [filters, setFilters] = useState<FilterState>({});
  const [sort, setSort] = useState<SortState>({});
  const [detail, setDetail] = useState<DiskIoRecord | null>(null);
  const taskIdWatch = Form.useWatch("task_id", form);

  const tasksQuery = useQuery({ queryKey: ["tasks", "disk-io-options"], queryFn: fetchTasks, staleTime: 60_000 });
  const summariesQuery = useQuery({ queryKey: ["disk-io-summaries"], queryFn: fetchDiskIoSummaries, staleTime: 30_000 });
  const recordsQuery = useQuery({
    queryKey: ["disk-io-records", page, pageSize, filters, sort],
    queryFn: () => fetchDiskIoRecords({ page, page_size: pageSize, ...filters, ...sort })
  });

  const tasks = tasksQuery.data ?? [];
  const jobOptions = useMemo(() => {
    const current = tasks.find((task) => task.id === taskIdWatch);
    return current?.jobs ?? [];
  }, [tasks, taskIdWatch]);

  useEffect(() => {
    const parsePositiveInt = (raw: string | null) => {
      const value = Number(raw);
      return Number.isInteger(value) && value > 0 ? value : undefined;
    };
    const executionId = parsePositiveInt(searchParams.get("execution_id"));
    const taskId = parsePositiveInt(searchParams.get("task_id"));
    const jobId = parsePositiveInt(searchParams.get("job_id"));
    const startTime = searchParams.get("start_time") ?? undefined;
    const endTime = searchParams.get("end_time") ?? undefined;
    const isWarningRaw = searchParams.get("is_warning");
    const isWarning = isWarningRaw === "true" ? true : isWarningRaw === "false" ? false : undefined;
    if (!executionId && !taskId && !jobId && !startTime && !endTime && isWarning === undefined) return;
    const start = startTime ? dayjs(startTime) : null;
    const end = endTime ? dayjs(endTime) : null;
    form.setFieldsValue({
      execution_id: executionId,
      task_id: taskId,
      job_id: jobId,
      is_warning: isWarning,
      time_range: start && end && start.isValid() && end.isValid() ? [start, end] : undefined
    });
    setFilters({ execution_id: executionId, task_id: taskId, job_id: jobId, is_warning: isWarning, start_time: startTime, end_time: endTime });
    setPage(1);
  }, [form, searchParams]);

  const handleSearch = () => {
    const values = form.getFieldsValue(true);
    const range = values.time_range as [Dayjs, Dayjs] | undefined;
    setFilters({
      execution_id: values.execution_id ?? undefined,
      task_id: values.task_id ?? undefined,
      job_id: values.job_id ?? undefined,
      provider: values.provider ?? undefined,
      task_type: values.task_type ?? undefined,
      is_warning: values.is_warning,
      start_time: range?.[0]?.format(TIME_FORMAT),
      end_time: range?.[1]?.format(TIME_FORMAT)
    });
    setPage(1);
  };

  const handleReset = () => {
    form.resetFields();
    setFilters({});
    setSort({});
    setPage(1);
  };

  const columns: ColumnsType<DiskIoRecord> = [
    { title: "执行时间", dataIndex: "finished_at", key: "finished_at", width: 180, render: (_, record) => formatDateTime(record.finished_at ?? record.started_at) },
    { title: "执行 ID", dataIndex: "execution_id", key: "execution_id", width: 100, render: (value) => (value ? `#${value}` : "-") },
    {
      title: "任务 / 作业",
      key: "owner",
      width: 260,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Text>{record.task_name || "-"}</Text>
          <Text type="secondary">{record.job_name || "-"}</Text>
        </Space>
      )
    },
    { title: "类型", dataIndex: "task_type", key: "task_type", width: 100, render: renderTaskType },
    { title: "聊天记录接口", dataIndex: "provider", key: "provider", width: 130, render: renderProvider },
    {
      title: <Tooltip title={diskWriteTooltipForProvider(filters.provider)}><span>磁盘写入</span></Tooltip>,
      dataIndex: "disk_write_bytes",
      key: "disk_write_bytes",
      width: 140,
      sorter: true,
      sortOrder: sort.sort_by === "disk_write_bytes" ? (sort.sort_order === "asc" ? "ascend" : "descend") : undefined,
      showSorterTooltip: false,
      render: (_, record) => (
        <Tooltip title={diskWriteTooltipForRecord(record.provider)}>
          <span><BytesText value={getDiskWriteBytes(record)} /></span>
        </Tooltip>
      )
    },
    {
      title: (
        <Tooltip title="只表示有没有捕获到 WeFlow 进程的读写计数；捕获不到也不影响任务执行。">
          <span>进程捕获</span>
        </Tooltip>
      ),
      key: "weflow",
      width: 140,
      render: (_, record) =>
        record.provider === "weflow" ? (record.weflow_captured ? <Tag color="green">已捕获</Tag> : <Tag>未捕获</Tag>) : "-"
    },
    {
      title: "状态",
      dataIndex: "is_warning",
      key: "is_warning",
      width: 100,
      render: (value, record) =>
        value ? (
          <Tooltip title={record.warning_reason || "导出文件大小超过阈值"}>
            <Tag color="red">异常</Tag>
          </Tooltip>
        ) : (
          <Tag color="green">正常</Tag>
        )
    },
    {
      title: "作业磁盘告警",
      key: "job_alert",
      width: 150,
      render: (_, record) => {
        if (!record.job_alert_threshold_bytes) {
          return <Tag>未开启</Tag>;
        }
        if (record.job_alert_triggered) {
          return (
            <Tooltip title={record.job_alert_error || `阈值 ${formatBytes(record.job_alert_threshold_bytes)}`}>
              <Tag color={record.job_alert_sent ? "red" : "orange"}>
                {record.job_alert_sent ? "已告警" : "告警失败"}
              </Tag>
            </Tooltip>
          );
        }
        return <Tag color="green">未触发</Tag>;
      }
    },
    {
      title: "操作",
      key: "actions",
      fixed: "right",
      width: 220,
      render: (_, record) => (
        <Space wrap>
          <Button type="link" onClick={() => setDetail(record)}>查看详情</Button>
          {record.execution_id ? (
            <Button
              type="link"
              onClick={() => navigate(`/executions?execution_id=${record.execution_id}${record.task_id ? `&task_id=${record.task_id}` : ""}${record.job_id ? `&job_id=${record.job_id}` : ""}`)}
            >
              查看作业执行详情
            </Button>
          ) : null}
        </Space>
      )
    }
  ];

  return (
    <>
      <Tabs
      defaultActiveKey="records"
      items={[
        {
          key: "records",
          label: "磁盘日志",
          children: (
            <Space direction="vertical" size={16} style={{ width: "100%" }}>
              <SummaryCards data={summariesQuery.data} />

              <Form form={form} layout="inline" onFinish={handleSearch} style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
                <Form.Item label="执行 ID" name="execution_id" style={{ marginBottom: 8 }}>
                  <InputNumber min={1} style={{ width: 140 }} placeholder="执行 ID" />
                </Form.Item>
                <Form.Item label="任务" name="task_id" style={{ marginBottom: 8 }}>
                  <Select
                    allowClear
                    placeholder="全部任务"
                    style={{ minWidth: 200 }}
                    loading={tasksQuery.isLoading}
                    options={tasks.map((task) => ({ label: task.name, value: task.id }))}
                    onChange={() => form.setFieldValue("job_id", undefined)}
                  />
                </Form.Item>
                <Form.Item label="作业" name="job_id" style={{ marginBottom: 8 }}>
                  <Select allowClear placeholder="全部作业" style={{ minWidth: 200 }} disabled={!taskIdWatch} options={jobOptions.map((job) => ({ label: job.name, value: job.id }))} />
                </Form.Item>
                <Form.Item label="聊天接口" name="provider" style={{ marginBottom: 8 }}>
                  <Select allowClear placeholder="全部接口" style={{ width: 150 }} options={[{ label: "WeFlow", value: "weflow" }, { label: "ChatLog", value: "chatlog" }]} />
                </Form.Item>
                <Form.Item label="任务类型" name="task_type" style={{ marginBottom: 8 }}>
                  <Select
                    allowClear
                    placeholder="全部类型"
                    style={{ width: 150 }}
                    options={[
                      { label: "日报", value: "report" },
                      { label: "话题卡片", value: "topic_card" },
                      { label: "数据导出", value: "export" }
                    ]}
                  />
                </Form.Item>
                <Form.Item label="状态" name="is_warning" style={{ marginBottom: 8 }}>
                  <Select allowClear placeholder="全部状态" style={{ width: 150 }} options={[{ label: "正常", value: false }, { label: "异常", value: true }]} />
                </Form.Item>
                <Form.Item label="执行时间" name="time_range" style={{ marginBottom: 8 }}>
                  <RangePicker
                    showTime={{ format: "HH:mm" }}
                    format={TIME_FORMAT}
                    allowClear
                    style={{ minWidth: 360 }}
                    ranges={{
                      今日: [dayjs().startOf("day"), dayjs().endOf("day")],
                      最近24小时: [dayjs().subtract(1, "day"), dayjs()]
                    }}
                  />
                </Form.Item>
                <Form.Item style={{ marginBottom: 8 }}>
                  <Space>
                    <Button type="primary" htmlType="submit">查询</Button>
                    <Button onClick={handleReset}>重置</Button>
                  </Space>
                </Form.Item>
              </Form>

              <Table<DiskIoRecord>
                rowKey={(record) => record.id}
                loading={recordsQuery.isLoading || recordsQuery.isFetching}
                dataSource={recordsQuery.data?.items ?? []}
                columns={columns}
                showSorterTooltip={false}
                pagination={{
                  current: page,
                  pageSize,
                  total: recordsQuery.data?.total ?? 0,
                  showSizeChanger: true,
                  pageSizeOptions: PAGE_SIZE_OPTIONS,
                  onChange: (nextPage: number, nextSize?: number) => {
                    setPage(nextPage);
                    if (nextSize && nextSize !== pageSize) setPageSize(nextSize);
                  }
                }}
                onChange={(_, __, sorter) => {
                  const item = Array.isArray(sorter) ? sorter[0] : sorter;
                  if (item?.field === "disk_write_bytes" && item.order) {
                    setSort({ sort_by: "disk_write_bytes", sort_order: item.order === "ascend" ? "asc" : "desc" });
                  } else {
                    setSort({});
                  }
                  setPage(1);
                }}
                scroll={{ x: "max-content" }}
                locale={{ emptyText: "暂无磁盘日志" }}
              />
            </Space>
          )
        },
        { key: "aggregate", label: "磁盘汇总", children: <AggregateTab /> }
      ]}
      />
      <Modal
        open={Boolean(detail)}
        title={detail ? `磁盘日志详情 #${detail.id}` : "磁盘日志详情"}
        width={900}
        onCancel={() => setDetail(null)}
        footer={<Button onClick={() => setDetail(null)}>关闭</Button>}
        destroyOnClose
      >
        {detail ? (
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            <Card size="small">
              <Title level={5} style={{ marginTop: 0 }}>磁盘写入</Title>
              <Descriptions bordered column={2} size="small">
                <Descriptions.Item label={detail.provider === "chatlog" ? "磁盘写入（总计）" : "磁盘写入（即导出文件大小）"} span={2}>
                  <Tooltip title={diskWriteTooltipForRecord(detail.provider)}>
                    <span><BytesText value={detail.disk_write_bytes} /></span>
                  </Tooltip>
                </Descriptions.Item>
                {detail.provider === "chatlog" ? (
                  <>
                    <Descriptions.Item label="导出文件大小"><BytesText value={detail.exported_file_bytes} /></Descriptions.Item>
                    <Descriptions.Item label="ChatLog 解密库写入估算"><BytesText value={detail.chatlog_decrypt_write_bytes} /></Descriptions.Item>
                    <Descriptions.Item label="ChatLog 解密状态">{renderChatlogDecryptStatus(detail.chatlog_decrypt_status)}</Descriptions.Item>
                    <Descriptions.Item label="ChatLog 工作目录">{detail.chatlog_work_dir || "-"}</Descriptions.Item>
                  </>
                ) : null}
                <Descriptions.Item label="媒体导出">{detail.media_enabled ? "是" : "否，media=0"}</Descriptions.Item>
                <Descriptions.Item label="状态">{detail.is_warning ? <Tag color="red">异常</Tag> : <Tag color="green">正常</Tag>}</Descriptions.Item>
                <Descriptions.Item label="作业告警阈值">
                  {detail.job_alert_threshold_bytes ? <BytesText value={detail.job_alert_threshold_bytes} /> : "未开启"}
                </Descriptions.Item>
                <Descriptions.Item label="作业告警状态">
                  {!detail.job_alert_threshold_bytes ? (
                    <Tag>未开启</Tag>
                  ) : detail.job_alert_triggered ? (
                    <Tag color={detail.job_alert_sent ? "red" : "orange"}>
                      {detail.job_alert_sent ? "已推送" : "推送失败"}
                    </Tag>
                  ) : (
                    <Tag color="green">未触发</Tag>
                  )}
                </Descriptions.Item>
              </Descriptions>
            </Card>
            <Card size="small">
              <Tooltip title={processIoTooltip}>
                <Title level={5} style={{ marginTop: 0 }}>进程 IO 计数（仅供参考）</Title>
              </Tooltip>
              <Descriptions bordered column={2} size="small">
                <Descriptions.Item label={<Tooltip title={backendReadTooltip}><span>后端读取</span></Tooltip>}>{formatBytes(detail.backend_read_bytes)}</Descriptions.Item>
                <Descriptions.Item label={<Tooltip title={backendWriteTooltip}><span>后端写入</span></Tooltip>}>{formatBytes(detail.backend_write_bytes)}</Descriptions.Item>
                {detail.provider === "weflow" ? (
                  <>
                    <Descriptions.Item label={<Tooltip title={weflowReadTooltip}><span>WeFlow 读取</span></Tooltip>}>{detail.weflow_captured ? formatBytes(detail.weflow_read_bytes) : "未捕获"}</Descriptions.Item>
                    <Descriptions.Item label={<Tooltip title={weflowWriteTooltip}><span>WeFlow 写入</span></Tooltip>}>{detail.weflow_captured ? formatBytes(detail.weflow_write_bytes) : "未捕获"}</Descriptions.Item>
                  </>
                ) : null}
                <Descriptions.Item label={<Tooltip title={processIoTooltip}><span>总读取</span></Tooltip>}>{formatBytes(detail.total_read_bytes)}</Descriptions.Item>
                <Descriptions.Item label={<Tooltip title={processIoTooltip}><span>总写入</span></Tooltip>}>{formatBytes(detail.total_write_bytes)}</Descriptions.Item>
              </Descriptions>
            </Card>
            <Descriptions bordered column={2} size="small">
              <Descriptions.Item label="执行 ID">#{detail.execution_id ?? "-"}</Descriptions.Item>
              <Descriptions.Item label="聊天记录接口">{renderProvider(detail.provider)}</Descriptions.Item>
              <Descriptions.Item label="任务">{detail.task_name || "-"}</Descriptions.Item>
              <Descriptions.Item label="作业">{detail.job_name || "-"}</Descriptions.Item>
              <Descriptions.Item label="任务类型">{renderTaskType(detail.task_type)}</Descriptions.Item>
              <Descriptions.Item label="执行方式">{detail.is_manual ? "手动" : "自动"}</Descriptions.Item>
              <Descriptions.Item label="开始时间">{formatDateTime(detail.started_at)}</Descriptions.Item>
              <Descriptions.Item label="结束时间">{formatDateTime(detail.finished_at)}</Descriptions.Item>
              {detail.job_alert_error ? (
                <Descriptions.Item label="作业告警错误" span={2}>
                  {detail.job_alert_error}
                </Descriptions.Item>
              ) : null}
              {detail.warning_reason ? <Descriptions.Item label="异常原因" span={2}>{detail.warning_reason}</Descriptions.Item> : null}
              {detail.raw_snapshot ? (
                <Descriptions.Item label="采样快照" span={2}>
                  <Paragraph style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}>{JSON.stringify(detail.raw_snapshot, null, 2)}</Paragraph>
                </Descriptions.Item>
              ) : null}
            </Descriptions>
          </Space>
        ) : null}
      </Modal>
    </>
  );
}

export default DiskIoRecordsPage;
