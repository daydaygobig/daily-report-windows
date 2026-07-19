import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, DatePicker, Form, InputNumber, Select, Space, Table, Tag, Tooltip } from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs, { type Dayjs } from "dayjs";
import { useNavigate, useSearchParams } from "react-router-dom";
import { fetchGithubDeployments, type GithubDeployment, type GithubDeploymentPage } from "../services/githubDeployments";
import { fetchGithubConfigs } from "../services/githubConfigs";
import { fetchTasks, type Task } from "../services/tasks";
import { formatDateTime } from "../utils/datetime";

const { RangePicker } = DatePicker;
const PAGE_SIZE_OPTIONS = ["10", "20", "50", "100"];

type FilterState = {
  task_id?: number;
  job_id?: number;
  config_id?: number;
  status?: string;
  start_time?: string;
  end_time?: string;
  record_id?: number;
};

const decodeGithubUrl = (url?: string | null) => {
  if (!url) {
    return "";
  }
  try {
    return decodeURI(url);
  } catch {
    return url;
  }
};

const buildGithubFileUrl = (record: GithubDeployment) => {
  if (record.github_file_url) {
    return record.github_file_url;
  }
  if (!record.repo_full_name || !record.repo_path) {
    return undefined;
  }
  const branch = record.branch || "main";
  return `https://github.com/${record.repo_full_name}/blob/${encodeURIComponent(branch)}/${record.repo_path
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/")}`;
};

function GithubDeploymentsPage() {
  const [form] = Form.useForm();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [filters, setFilters] = useState<FilterState>({});
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const taskIdWatch = Form.useWatch("task_id", form);

  const tasksQuery = useQuery({ queryKey: ["tasks", "options"], queryFn: fetchTasks, staleTime: 60_000 });
  const configsQuery = useQuery({ queryKey: ["github-configs", "options"], queryFn: fetchGithubConfigs, staleTime: 60_000 });

  const { data, isFetching, isLoading } = useQuery({
    queryKey: ["github-deployments", page, pageSize, filters],
    keepPreviousData: true,
    queryFn: () =>
      fetchGithubDeployments({
        page,
        page_size: pageSize,
        ...filters
      })
  });

  const deploymentPage: GithubDeploymentPage | undefined = data;
  const tableData = deploymentPage?.items ?? [];
  const total = deploymentPage?.total ?? 0;

  const taskOptions = tasksQuery.data ?? [];
  const jobOptions = useMemo(() => {
    const selectedTaskId = taskIdWatch;
    const currentTask = taskOptions.find((task) => task.id === selectedTaskId);
    return currentTask?.jobs ?? [];
  }, [taskIdWatch, taskOptions]);

  useEffect(() => {
    const recordIdParam = searchParams.get("recordId");
    if (!recordIdParam) {
      return;
    }
    const numericId = Number(recordIdParam);
    const next = new URLSearchParams(searchParams);
    next.delete("recordId");
    setSearchParams(next, { replace: true });
    if (Number.isNaN(numericId) || numericId <= 0) {
      return;
    }
    form.setFieldsValue({ record_id: numericId });
    setFilters((prev) => ({ ...prev, record_id: numericId }));
    setPage(1);
  }, [searchParams, setSearchParams, form]);

  const handleSearch = () => {
    const values = form.getFieldsValue();
    const timeRange = values.time_range as [Dayjs, Dayjs] | undefined;
    const nextFilters: FilterState = {
      task_id: values.task_id ?? undefined,
      job_id: values.job_id ?? undefined,
      config_id: values.config_id ?? undefined,
      status: values.status ?? undefined,
      start_time: timeRange?.[0]?.format("YYYY-MM-DD HH:mm"),
      end_time: timeRange?.[1]?.format("YYYY-MM-DD HH:mm"),
      record_id: values.record_id ?? undefined
    };
    setFilters(nextFilters);
    setPage(1);
  };

  const handleReset = () => {
    form.resetFields();
    setFilters({});
    setPage(1);
  };

  const columns: ColumnsType<GithubDeployment> = [
    { title: "ID", dataIndex: "id", key: "id", width: 100 },
    {
      title: "类型",
      dataIndex: "artifact_type",
      key: "artifact_type",
      width: 130,
      render: (value?: string | null, record) => {
        const label = record.artifact_label || (value === "message_stats" ? "消息统计" : "HTML 日报");
        return <Tag color={value === "message_stats" ? "purple" : "blue"}>{label}</Tag>;
      }
    },
    { title: "任务", dataIndex: "task_name", key: "task_name", render: (value) => value || "-" },
    { title: "作业", dataIndex: "job_name", key: "job_name", render: (value) => value || "-" },
    { title: "GitHub 配置", dataIndex: "config_name", key: "config_name", render: (value) => value || "-" },
    {
      title: "GitHub 路径",
      dataIndex: "repo_path",
      key: "repo_path",
      width: 460,
      render: (value?: string | null, record) => {
        const fileUrl = buildGithubFileUrl(record);
        return fileUrl ? (
          <a href={fileUrl} target="_blank" rel="noreferrer" style={{ wordBreak: "break-all" }}>
            {decodeGithubUrl(fileUrl)}
          </a>
        ) : value ? (
          <span style={{ wordBreak: "break-all" }}>{value}</span>
        ) : (
          "-"
        );
      }
    },
    {
      title: "开始时间",
      dataIndex: "started_at",
      key: "started_at",
      render: (value: string | null | undefined) => formatDateTime(value)
    },
    {
      title: "结束时间",
      dataIndex: "finished_at",
      key: "finished_at",
      render: (value: string | null | undefined) => formatDateTime(value)
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      render: (status: string) => (
        <Tag color={status === "success" ? "green" : status === "failed" ? "red" : "blue"}>{status}</Tag>
      )
    },
    {
      title: "错误信息",
      dataIndex: "error_msg",
      key: "error_msg",
      ellipsis: true,
      render: (value?: string | null) =>
        value ? (
          <Tooltip title={<pre style={{ maxWidth: 520 }}>{value}</pre>}>
            <span>{value}</span>
          </Tooltip>
        ) : (
          "-"
        )
    },
    {
      title: "操作",
      key: "actions",
      fixed: "right",
      width: 200,
      render: (_, record) => (
        <Space size="small">
          {record.pages_url ? (
            <a href={record.pages_url} target="_blank" rel="noreferrer">
              查看页面
            </a>
          ) : null}
          {record.execution_id ? (
            <Button type="link" onClick={() => navigate(`/executions?executionId=${record.execution_id}`)}>
              查看执行
            </Button>
          ) : null}
        </Space>
      )
    }
  ];

  const pagination = useMemo(
    () => ({
      current: page,
      pageSize,
      total,
      showSizeChanger: true,
      pageSizeOptions: PAGE_SIZE_OPTIONS,
      onChange: (nextPage: number, nextSize?: number) => {
        setPage(nextPage);
        if (nextSize && nextSize !== pageSize) {
          setPageSize(nextSize);
        }
      }
    }),
    [page, pageSize, total]
  );

  return (
    <div>
      <Form
        form={form}
        layout="inline"
        onFinish={handleSearch}
        style={{ marginBottom: 16, display: "flex", flexWrap: "wrap", gap: 12 }}
      >
        <Form.Item label="任务" name="task_id" style={{ marginBottom: 8 }}>
          <Select
            allowClear
            placeholder="全部任务"
            style={{ minWidth: 200 }}
            loading={tasksQuery.isLoading}
            options={taskOptions.map((task: Task) => ({ label: task.name, value: task.id }))}
            onChange={() => form.setFieldsValue({ job_id: undefined })}
          />
        </Form.Item>
        <Form.Item label="作业" name="job_id" style={{ marginBottom: 8 }}>
          <Tooltip title={!taskIdWatch ? "请先选择任务" : undefined}>
            <span style={{ display: "inline-block" }}>
              <Select
                allowClear
                placeholder="全部作业"
                style={{ minWidth: 200 }}
                disabled={!taskIdWatch}
                options={jobOptions.map((job) => ({ label: job.name, value: job.id }))}
              />
            </span>
          </Tooltip>
        </Form.Item>
        <Form.Item label="GitHub 配置" name="config_id" style={{ marginBottom: 8 }}>
          <Select
            allowClear
            placeholder="全部配置"
            style={{ minWidth: 200 }}
            loading={configsQuery.isLoading}
            options={(configsQuery.data ?? []).map((config) => ({ label: config.name, value: config.id }))}
          />
        </Form.Item>
        <Form.Item label="状态" name="status" style={{ marginBottom: 8 }}>
          <Select
            allowClear
            placeholder="全部状态"
            style={{ width: 160 }}
            options={[
              { label: "成功", value: "success" },
              { label: "失败", value: "failed" }
            ]}
          />
        </Form.Item>
        <Form.Item label="执行时间" name="time_range" style={{ marginBottom: 8 }}>
          <RangePicker
            showTime={{ format: "HH:mm" }}
            format="YYYY-MM-DD HH:mm"
            allowClear
            style={{ minWidth: 360 }}
          />
        </Form.Item>
        <Form.Item label="记录 ID" name="record_id" style={{ marginBottom: 8 }}>
          <InputNumber placeholder="输入记录 ID" min={1} style={{ width: 160 }} />
        </Form.Item>
        <Form.Item style={{ marginBottom: 8 }}>
          <Space>
            <Button type="primary" htmlType="submit">
              查询
            </Button>
            <Button htmlType="button" onClick={handleReset}>
              重置
            </Button>
          </Space>
        </Form.Item>
      </Form>
      <Table<GithubDeployment>
        dataSource={tableData}
        columns={columns}
        rowKey={(record) => record.id}
        loading={isLoading || isFetching}
        pagination={pagination}
        scroll={{ x: "max-content" }}
        locale={{ emptyText: "暂无部署记录" }}
      />
    </div>
  );
}

export default GithubDeploymentsPage;
