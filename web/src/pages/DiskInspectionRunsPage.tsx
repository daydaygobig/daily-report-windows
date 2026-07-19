import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, DatePicker, Descriptions, Form, Modal, Select, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { Dayjs } from "dayjs";
import { useNavigate } from "react-router-dom";
import {
  fetchDiskInspectionJobs,
  fetchDiskInspectionRuns,
  type DiskInspectionJob,
  type DiskInspectionRun,
} from "../services/diskMonitor";
import { formatDateTime } from "../utils/datetime";
import { BytesText } from "./DiskIoRecordsPage";

const { RangePicker } = DatePicker;
const { Text, Paragraph } = Typography;
const PAGE_SIZE_OPTIONS = ["10", "20", "50", "100"];
const TIME_FORMAT = "YYYY-MM-DD HH:mm";

type FilterState = {
  inspection_job_id?: number;
  status?: string;
  start_time?: string;
  end_time?: string;
};

const renderStatus = (status: string) => {
  if (status === "warning") {
    return <Tag color="red">超过阈值</Tag>;
  }
  if (status === "success") {
    return <Tag color="green">正常</Tag>;
  }
  return <Tag>{status}</Tag>;
};

function scheduleSummary(job?: DiskInspectionJob | null) {
  if (!job) return "-";
  if (job.schedule_type === "manual") return "仅手动执行";
  if (job.schedule_type === "custom_cron") return job.cron_expression || "-";
  const base = job.schedule_time || "-";
  if (!job.interval_enabled) return base;
  return `${base} 起，每 ${job.interval_minutes ?? 120} 分钟，${job.window_start} - ${job.window_end}`;
}

function DiskInspectionRunsPage() {
  const [form] = Form.useForm();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [filters, setFilters] = useState<FilterState>({});
  const [detail, setDetail] = useState<DiskInspectionRun | null>(null);

  const jobsQuery = useQuery({
    queryKey: ["disk-inspection-jobs", "run-filter"],
    queryFn: fetchDiskInspectionJobs,
    staleTime: 60_000,
  });
  const runsQuery = useQuery({
    queryKey: ["disk-inspection-runs", page, pageSize, filters],
    queryFn: () => fetchDiskInspectionRuns({ page, page_size: pageSize, ...filters }),
  });

  const jobsById = useMemo(
    () => new Map((jobsQuery.data ?? []).map((item) => [item.id, item] as const)),
    [jobsQuery.data],
  );

  const handleSearch = () => {
    const values = form.getFieldsValue(true);
    const range = values.time_range as [Dayjs, Dayjs] | undefined;
    setFilters({
      inspection_job_id: values.inspection_job_id ?? undefined,
      status: values.status ?? undefined,
      start_time: range?.[0]?.format(TIME_FORMAT),
      end_time: range?.[1]?.format(TIME_FORMAT),
    });
    setPage(1);
  };

  const handleReset = () => {
    form.resetFields();
    setFilters({});
    setPage(1);
  };

  const buildDiskLogUrl = (record: DiskInspectionRun) => {
    const params = new URLSearchParams({
      start_time: record.window_start.slice(0, 16).replace("T", " "),
      end_time: record.window_end.slice(0, 16).replace("T", " "),
    });
    if (record.status === "warning") {
      params.set("is_warning", "true");
    }
    return `/logs/disk?${params.toString()}`;
  };

  const columns: ColumnsType<DiskInspectionRun> = [
    {
      title: "巡检日期",
      dataIndex: "inspected_at",
      key: "inspected_at",
      width: 180,
      render: formatDateTime,
    },
    {
      title: "巡检任务",
      dataIndex: "inspection_job_name",
      key: "inspection_job_name",
      width: 220,
      render: (value) => value || "-",
    },
    {
      title: "调度方式",
      key: "schedule",
      width: 260,
      render: (_, record) => {
        const job = record.inspection_job_id ? jobsById.get(record.inspection_job_id) : undefined;
        return (
          <Space direction="vertical" size={0}>
            <Text>{job ? scheduleSummary(job) : "-"}</Text>
            {job?.next_run_at ? <Text type="secondary">{`下次巡检：${formatDateTime(job.next_run_at)}`}</Text> : null}
          </Space>
        );
      },
    },
    {
      title: "检查窗口",
      key: "window",
      width: 260,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Text>{`${formatDateTime(record.window_start)} ~ ${formatDateTime(record.window_end)}`}</Text>
          <Text type="secondary">最近 {record.window_hours} 小时</Text>
        </Space>
      ),
    },
    {
      title: "总写入",
      dataIndex: "total_write_bytes",
      key: "total_write_bytes",
      width: 120,
      render: (value) => <BytesText value={value} />,
    },
    {
      title: "最大单次写入",
      dataIndex: "max_single_write_bytes",
      key: "max_single_write_bytes",
      width: 140,
      render: (value) => <BytesText value={value} />,
    },
    {
      title: "异常次数",
      dataIndex: "warning_count",
      key: "warning_count",
      width: 100,
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 110,
      render: renderStatus,
    },
    {
      title: "飞书告警",
      dataIndex: "alert_sent",
      key: "alert_sent",
      width: 120,
      render: (value, record) =>
        value ? <Tag color="green">已推送</Tag> : record.alert_error ? <Tag color="red">推送失败</Tag> : <Tag>未推送</Tag>,
    },
    {
      title: "操作",
      key: "actions",
      fixed: "right",
      width: 220,
      render: (_, record) => (
        <Space wrap>
          <Button type="link" onClick={() => setDetail(record)}>
            查看详情
          </Button>
          <Button type="link" onClick={() => navigate(buildDiskLogUrl(record))}>
            查看磁盘日志
          </Button>
        </Space>
      ),
    },
  ];

  const pagination = useMemo(
    () => ({
      current: page,
      pageSize,
      total: runsQuery.data?.total ?? 0,
      showSizeChanger: true,
      pageSizeOptions: PAGE_SIZE_OPTIONS,
      onChange: (nextPage: number, nextSize?: number) => {
        setPage(nextPage);
        if (nextSize && nextSize !== pageSize) {
          setPageSize(nextSize);
        }
      },
    }),
    [page, pageSize, runsQuery.data?.total],
  );

  const detailJob = detail?.inspection_job_id ? jobsById.get(detail.inspection_job_id) : undefined;

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Form form={form} layout="inline" onFinish={handleSearch} style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
        <Form.Item label="巡检任务" name="inspection_job_id" style={{ marginBottom: 8 }}>
          <Select
            allowClear
            placeholder="全部巡检任务"
            style={{ minWidth: 220 }}
            loading={jobsQuery.isLoading}
            options={(jobsQuery.data ?? []).map((item) => ({ label: item.name, value: item.id }))}
          />
        </Form.Item>
        <Form.Item label="状态" name="status" style={{ marginBottom: 8 }}>
          <Select
            allowClear
            placeholder="全部状态"
            style={{ width: 160 }}
            options={[
              { label: "正常", value: "success" },
              { label: "超过阈值", value: "warning" },
            ]}
          />
        </Form.Item>
        <Form.Item label="巡检日期" name="time_range" style={{ marginBottom: 8 }}>
          <RangePicker showTime={{ format: "HH:mm" }} format={TIME_FORMAT} allowClear style={{ minWidth: 360 }} />
        </Form.Item>
        <Form.Item style={{ marginBottom: 8 }}>
          <Space>
            <Button type="primary" htmlType="submit">
              查询
            </Button>
            <Button onClick={handleReset}>重置</Button>
          </Space>
        </Form.Item>
      </Form>

      <Table<DiskInspectionRun>
        rowKey={(record) => record.id}
        loading={runsQuery.isLoading || runsQuery.isFetching}
        dataSource={runsQuery.data?.items ?? []}
        columns={columns}
        pagination={pagination}
        scroll={{ x: "max-content" }}
        locale={{ emptyText: "暂无巡检日志" }}
      />

      <Modal
        open={Boolean(detail)}
        title={detail ? `巡检日志详情 #${detail.id}` : "巡检日志详情"}
        width={900}
        onCancel={() => setDetail(null)}
        footer={<Button onClick={() => setDetail(null)}>关闭</Button>}
        destroyOnClose
      >
        {detail ? (
          <Descriptions bordered column={2} size="small">
            <Descriptions.Item label="巡检日期">{formatDateTime(detail.inspected_at)}</Descriptions.Item>
            <Descriptions.Item label="巡检任务">{detail.inspection_job_name || "-"}</Descriptions.Item>
            <Descriptions.Item label="状态">{renderStatus(detail.status)}</Descriptions.Item>
            <Descriptions.Item label="调度方式">{detailJob ? scheduleSummary(detailJob) : "-"}</Descriptions.Item>
            <Descriptions.Item label="生效时间窗">{detailJob ? `${detailJob.window_start} - ${detailJob.window_end}` : "-"}</Descriptions.Item>
            <Descriptions.Item label="下次巡检">{detailJob?.next_run_at ? formatDateTime(detailJob.next_run_at) : "-"}</Descriptions.Item>
            <Descriptions.Item label="检查窗口">最近 {detail.window_hours} 小时</Descriptions.Item>
            <Descriptions.Item label="窗口开始">{formatDateTime(detail.window_start)}</Descriptions.Item>
            <Descriptions.Item label="窗口结束">{formatDateTime(detail.window_end)}</Descriptions.Item>
            <Descriptions.Item label="总写入">
              <BytesText value={detail.total_write_bytes} />
            </Descriptions.Item>
            <Descriptions.Item label="总读取">
              <BytesText value={detail.total_read_bytes} />
            </Descriptions.Item>
            <Descriptions.Item label="最大单次写入">
              <BytesText value={detail.max_single_write_bytes} />
            </Descriptions.Item>
            <Descriptions.Item label="阈值">
              <BytesText value={detail.threshold_bytes} />
            </Descriptions.Item>
            <Descriptions.Item label="异常次数">{detail.warning_count}</Descriptions.Item>
            <Descriptions.Item label="记录数">{detail.record_count}</Descriptions.Item>
            <Descriptions.Item label="ChatLog 解密大写入次数">{detail.chatlog_decrypt_count}</Descriptions.Item>
            <Descriptions.Item label="WeFlow 媒体导出次数">{detail.weflow_media_count}</Descriptions.Item>
            <Descriptions.Item label="飞书告警">
              {detail.alert_sent ? "已推送" : detail.alert_error ? "推送失败" : "未推送"}
            </Descriptions.Item>
            <Descriptions.Item label="告警机器人">{detail.webhook_ids?.length ?? 0} 个</Descriptions.Item>
            {detail.alert_error ? (
              <Descriptions.Item label="告警错误" span={2}>
                <Paragraph style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}>{detail.alert_error}</Paragraph>
              </Descriptions.Item>
            ) : null}
            {detail.summary ? (
              <Descriptions.Item label="摘要" span={2}>
                <Paragraph style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}>{detail.summary}</Paragraph>
              </Descriptions.Item>
            ) : null}
          </Descriptions>
        ) : null}
      </Modal>
    </Space>
  );
}

export default DiskInspectionRunsPage;
