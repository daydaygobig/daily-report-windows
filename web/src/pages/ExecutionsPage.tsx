import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { ReloadOutlined } from "@ant-design/icons";
import { Button, DatePicker, Form, InputNumber, message, Select, Space, Table, Tag, Tooltip, Typography } from "antd";
import { Resizable } from "react-resizable";
import type { ColumnsType } from "antd/es/table";
import dayjs, { type Dayjs } from "dayjs";
import { useNavigate, useSearchParams } from "react-router-dom";
import { fetchExecutionDetail, fetchExecutions, type Execution, type ExecutionPage } from "../services/executions";
import { fetchTasks } from "../services/tasks";
import { formatDateTime } from "../utils/datetime";
import ExecutionDetailModal from "../components/ExecutionDetailModal";

const { RangePicker } = DatePicker;
const { Paragraph, Text } = Typography;
const TIME_FORMAT = "YYYY-MM-DD HH:mm";
const PAGE_SIZE_OPTIONS = ["10", "20", "50", "100"];
const COLUMN_STORAGE_KEY = "executions_table_column_widths";

type ExecutionFilters = {
  executionId?: number;
  taskId?: number;
  jobId?: number;
  status?: string;
  startTime?: string;
  endTime?: string;
};

function ExecutionsPage() {
  const [form] = Form.useForm();
  const [page, setPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(50);
  const [filters, setFilters] = useState<ExecutionFilters>({});
  const [detail, setDetail] = useState<Execution | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const taskQuery = useQuery({
    queryKey: ["tasks", "options"],
    queryFn: fetchTasks,
    refetchOnMount: "always"
  });
  const taskIdWatch = Form.useWatch("task_id", form);

  const { data, isLoading, isFetching, isError, error, refetch } = useQuery({
    queryKey: ["executions", page, pageSize, filters],
    queryFn: () =>
      fetchExecutions({
        page,
        page_size: pageSize,
        execution_id: filters.executionId,
        task_id: filters.taskId,
        job_id: filters.jobId,
        status: filters.status,
        start_time: filters.startTime,
        end_time: filters.endTime
      }),
    refetchOnMount: "always"
  });

  const executionPage: ExecutionPage | undefined = data;
  const tableData = executionPage?.items ?? [];
  const total = executionPage?.total ?? 0;

  useEffect(() => {
    if (!isError) {
      return;
    }
    const apiMessage =
      (error as any)?.response?.data?.detail?.message ||
      (error as any)?.response?.data?.message ||
      (error as any)?.message ||
      "执行记录查询失败";
    message.error(apiMessage);
  }, [isError, error]);
  useEffect(() => {
    const executionParam = searchParams.get("executionId");
    if (!executionParam) {
      return;
    }
    const numericId = Number(executionParam);
    const next = new URLSearchParams(searchParams);
    next.delete("executionId");
    setSearchParams(next, { replace: true });
    if (Number.isNaN(numericId) || numericId <= 0) {
      message.error("无法识别的执行记录 ID");
      return;
    }
    let cancelled = false;
    fetchExecutionDetail(numericId)
      .then((record) => {
        if (!cancelled) {
          setDetail(record);
        }
      })
      .catch(() => {
        if (!cancelled) {
          message.error("未找到该执行记录");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    const executionIdParam = searchParams.get("execution_id");
    const taskIdParam = searchParams.get("task_id");
    const jobIdParam = searchParams.get("job_id");
    const statusParam = searchParams.get("status");
    const startTimeParam = searchParams.get("start_time");
    const endTimeParam = searchParams.get("end_time");
    if (!executionIdParam && !taskIdParam && !jobIdParam && !statusParam && !startTimeParam && !endTimeParam) {
      return;
    }

    const parsePositiveInt = (value: string | null) => {
      if (!value) {
        return undefined;
      }
      const parsed = Number(value);
      return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
    };

    const executionId = parsePositiveInt(executionIdParam);
    const taskId = parsePositiveInt(taskIdParam);
    const jobId = parsePositiveInt(jobIdParam);
    const startTime = startTimeParam ?? undefined;
    const endTime = endTimeParam ?? undefined;
    const start = startTime ? dayjs(startTime) : null;
    const end = endTime ? dayjs(endTime) : null;
    const timeRange = start && end && start.isValid() && end.isValid() ? [start, end] : undefined;

    form.setFieldsValue({
      execution_id: executionId,
      task_id: taskId,
      job_id: jobId,
      status: statusParam ?? undefined,
      time_range: timeRange
    });
    setFilters({
      executionId,
      taskId,
      jobId,
      status: statusParam ?? undefined,
      startTime,
      endTime
    });
    setPage(1);
  }, [form, searchParams]);

  const tasks = taskQuery.data ?? [];
  const jobOptions = useMemo(() => {
    const current = tasks.find((task) => task.id === taskIdWatch);
    return current?.jobs ?? [];
  }, [tasks, taskIdWatch]);

  const renderDeployCell = useCallback(
    (record: Execution) => {
      if (!record.deploy_status || record.deploy_status === "none") {
        return record.deploy_record_id ? (
          <Button type="link" onClick={() => navigate(`/github/deployments?recordId=${record.deploy_record_id}`)}>
            查看记录
          </Button>
        ) : (
          "-"
        );
      }
      const nodes: ReactNode[] = [];
      if (record.deploy_status === "success") {
        nodes.push(
          record.deploy_url ? (
            <a key="view" href={record.deploy_url} target="_blank" rel="noreferrer">
              查看页面
            </a>
          ) : (
            <Tag key="status" color="green">
              成功
            </Tag>
          )
        );
      } else {
        nodes.push(
          <Tooltip key="status" title={record.deploy_error || "部署失败"}>
            <Tag color="red">失败</Tag>
          </Tooltip>
        );
      }
      if (record.deploy_record_id) {
        nodes.push(
          <Button
            key="record"
            type="link"
            size="small"
            onClick={() => navigate(`/github/deployments?recordId=${record.deploy_record_id}`)}
          >
            查看记录
          </Button>
        );
      }
      return nodes.length ? <Space size="small">{nodes}</Space> : "-";
    },
    [navigate]
  );

const renderParagraphCell = (value?: string | null) => {
  if (!value) {
    return "-";
  }
  return (
    <Tooltip title={value}>
      <Paragraph
        className="text-clamp"
        style={{ marginBottom: 0, wordBreak: "break-word", maxWidth: PREVIEW_COLUMN_WIDTH - 20 }}
      >
        {value}
      </Paragraph>
    </Tooltip>
  );
};

  const handleSearch = () => {
    const values = form.getFieldsValue(true);
    const toPositiveInt = (value: unknown): number | undefined => {
      if (value === undefined || value === null || value === "") {
        return undefined;
      }
      const parsed = Number(value);
      if (!Number.isInteger(parsed) || parsed <= 0) {
        return undefined;
      }
      return parsed;
    };
    const range = values.time_range as [Dayjs, Dayjs] | undefined;
    const nextFilters: ExecutionFilters = {
      executionId: toPositiveInt(values.execution_id),
      taskId: toPositiveInt(values.task_id),
      jobId: toPositiveInt(values.job_id),
      status: values.status ?? undefined,
      startTime: range?.[0]?.format(TIME_FORMAT),
      endTime: range?.[1]?.format(TIME_FORMAT)
    };
    if (page === 1 && JSON.stringify(nextFilters) === JSON.stringify(filters)) {
      void refetch();
    }
    setFilters(nextFilters);
    setPage(1);
  };

  const handleReset = () => {
    form.resetFields();
    if (page === 1 && Object.keys(filters).length === 0) {
      void refetch();
    }
    setFilters({});
    setPage(1);
  };

  const handleRefresh = () => {
    void Promise.all([taskQuery.refetch(), refetch()]);
  };

  type ExecutionColumn = ColumnsType<Execution>[number] & { key: string; width?: number };

  const loadStoredWidths = () => {
    try {
      const stored = localStorage.getItem(COLUMN_STORAGE_KEY);
      return stored ? (JSON.parse(stored) as Record<string, number>) : {};
    } catch (error) {
      console.warn("Failed to parse column width cache", error);
      return {};
    }
  };

const PREVIEW_COLUMN_WIDTH = 280;
const defaultColumnWidths: Record<string, number> = {
  id: 80,
  task_name: 200,
  job_name: 220,
  llm_model_name: 160,
  started_at: 180,
  status: 120,
  is_manual: 120,
  summary_md: PREVIEW_COLUMN_WIDTH,
  error_msg: PREVIEW_COLUMN_WIDTH,
  deploy_status: 180,
  actions: 160
};

  const baseColumns: ExecutionColumn[] = [
    { title: "ID", dataIndex: "id", key: "id" },
    {
      title: "任务",
      dataIndex: "task_name",
      key: "task_name",
      render: (value: string | null | undefined) => renderParagraphCell(value)
    },
    {
      title: "作业",
      dataIndex: "job_name",
      key: "job_name",
      render: (value: string | null | undefined) => renderParagraphCell(value)
    },
    {
      title: "使用模型",
      dataIndex: "llm_model_name",
      key: "llm_model_name",
      render: (value: string | null | undefined) => value || "-"
    },
    {
      title: "执行时间",
      dataIndex: "started_at",
      key: "started_at",
      render: (_: string | null | undefined, record) => formatDateTime(record.started_at)
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      render: (status: string) => <Tag color={status === "success" ? "green" : status === "failed" ? "red" : "blue"}>{status}</Tag>
    },
    {
      title: "执行类型",
      dataIndex: "is_manual",
      key: "is_manual",
      render: (value: boolean) => (value ? <Tag color="purple">手动</Tag> : <Tag>自动</Tag>)
    },
    {
      title: "摘要预览",
      dataIndex: "summary_md",
      key: "summary_md",
      ellipsis: true,
      render: (value: string | null | undefined) => renderParagraphCell(value)
    },
    {
      title: "错误预览",
      dataIndex: "error_msg",
      key: "error_msg",
      ellipsis: true,
      render: (value: string | null | undefined) => renderParagraphCell(value)
    },
    {
      title: "GitHub 部署",
      dataIndex: "deploy_status",
      key: "deploy_status",
      render: (_: string, record) => renderDeployCell(record)
    },
    {
      title: "操作",
      key: "actions",
      fixed: "right",
      width: defaultColumnWidths.actions,
      render: (_, record) => (
        <Button type="link" onClick={() => setDetail(record)}>
          查看详情
        </Button>
      )
    }
  ];

  const [columns, setColumns] = useState<ExecutionColumn[]>(() => {
    const stored = loadStoredWidths();
    return baseColumns.map((column) => ({
      ...column,
      width: stored[column.key] ?? defaultColumnWidths[column.key] ?? 160
    }));
  });

  const handleResize = useCallback(
    (index: number) => (_: unknown, { size }: { size: { width: number } }) => {
      setColumns((prev) => {
        const next = [...prev];
        next[index] = { ...next[index], width: size.width };
        return next;
      });
    },
    []
  );

  useEffect(() => {
    const widths = columns.reduce<Record<string, number>>((acc, column) => {
      if (column.width) {
        acc[column.key] = column.width;
      }
      return acc;
    }, {});
    localStorage.setItem(COLUMN_STORAGE_KEY, JSON.stringify(widths));
  }, [columns]);

  const mergedColumns = useMemo(
    () =>
      columns.map((col, index) => ({
        ...col,
        onHeaderCell: (column: ExecutionColumn) => ({
          width: column.width,
          onResize: handleResize(index)
        })
      })),
    [columns, handleResize]
  );

  const ResizableTitle = (props: any) => {
    const { onResize, width, ...restProps } = props;
    if (!width) {
      return <th {...restProps} />;
    }
    return (
      <Resizable
        width={width}
        height={0}
        handle={
          <span
            onClick={(e) => e.stopPropagation()}
            style={{
              position: "absolute",
              right: -6,
              top: 0,
              bottom: 0,
              width: 12,
              cursor: "col-resize",
              zIndex: 1
            }}
          />
        }
        onResize={onResize}
        draggableOpts={{ enableUserSelectHack: false }}
      >
        <th {...restProps} style={{ width }} />
      </Resizable>
    );
  };

  const tableComponents = useMemo(
    () => ({
      header: {
        cell: ResizableTitle
      }
    }),
    []
  );

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
    <>
      <Form
        form={form}
        layout="inline"
        onFinish={handleSearch}
        style={{ marginBottom: 16, display: "flex", flexWrap: "wrap", gap: 12 }}
      >
        <Form.Item label="执行ID" name="execution_id" style={{ marginBottom: 8 }}>
          <InputNumber min={1} placeholder="输入执行ID" style={{ width: 160 }} />
        </Form.Item>
        <Form.Item label="任务" name="task_id" style={{ marginBottom: 8 }}>
          <Select
            allowClear
            placeholder="全部任务"
            loading={taskQuery.isLoading}
            style={{ minWidth: 200 }}
            options={tasks.map((task) => ({ label: task.name, value: task.id }))}
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
        <Form.Item label="状态" name="status" style={{ marginBottom: 8 }}>
          <Select
            allowClear
            placeholder="全部状态"
            style={{ width: 160 }}
            options={[
              { label: "成功", value: "success" },
              { label: "失败", value: "failed" },
              { label: "运行中", value: "running" },
              { label: "空数据", value: "empty" }
            ]}
          />
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
            <Button type="primary" htmlType="button" onClick={handleSearch}>
              查询
            </Button>
            <Button htmlType="button" onClick={handleReset}>
              重置
            </Button>
            <Button
              icon={<ReloadOutlined />}
              loading={isFetching || taskQuery.isFetching}
              htmlType="button"
              onClick={handleRefresh}
            >
              刷新
            </Button>
          </Space>
        </Form.Item>
      </Form>
      <Table
        loading={isLoading || isFetching}
        dataSource={tableData}
        rowKey={(record) => record.id}
        pagination={pagination}
        columns={mergedColumns}
        components={tableComponents}
        tableLayout="fixed"
        style={{ wordBreak: "break-word" }}
        scroll={{ x: "max-content" }}
        locale={{ emptyText: "暂无执行记录" }}
      />
      <ExecutionDetailModal
        execution={detail}
        onClose={() => setDetail(null)}
        onOpenDeployRecord={(recordId) => navigate(`/github/deployments?recordId=${recordId}`)}
        onOpenImaSyncRecord={(executionId, batchId) =>
          navigate(
            `/ima/records?executionId=${executionId}${batchId ? `&batchId=${encodeURIComponent(batchId)}` : ""}`
          )
        }
      />
    </>
  );
}
export default ExecutionsPage;
