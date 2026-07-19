import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, DatePicker, Form, Input, InputNumber, Modal, Select, Space, Table, Tag, Tooltip, Typography } from "antd";
import type { Dayjs } from "dayjs";
import type { ColumnsType } from "antd/es/table";
import { useNavigate, useSearchParams } from "react-router-dom";
import { fetchTasks } from "../services/tasks";
import {
  fetchImaAccounts,
  fetchImaBatchItems,
  fetchImaSyncBatches,
  fetchImaSyncJobs,
  type ImaSyncBatch,
  type ImaSyncBatchPage,
  type ImaSyncRecord
} from "../services/ima";
import { formatUtcDateTime } from "../utils/datetime";

const { RangePicker } = DatePicker;
const { Paragraph } = Typography;
const PAGE_SIZE_OPTIONS = ["10", "20", "50", "100"];

type FilterState = {
  ima_account_id?: number;
  task_id?: number;
  job_id?: number;
  sync_job_id?: number;
  sync_scope?: "daily_report_job" | "ima_sync_job";
  status?: string;
  trigger_type?: string;
  execution_id?: number;
  batch_id?: string;
  query?: string;
  start_time?: string;
  end_time?: string;
};

type TriggerMode = "daily_report_job_sync" | "ima_auto_sync" | "manual_sync";

const getBatchTriggerLabel = (record: Pick<ImaSyncBatch, "trigger_type" | "sync_scope">): string => {
  if (record.trigger_type === "job") {
    return "群聊日报作业同步";
  }
  if (record.trigger_type === "auto" && record.sync_scope === "ima_sync_job") {
    return "ima自动同步";
  }
  if (record.trigger_type === "manual") {
    return "手动同步";
  }
  if (record.trigger_type === "auto") {
    return "自动同步";
  }
  return record.trigger_type;
};

const renderStatus = (status: string, errorMessage?: string | null) => {
  const colorMap: Record<string, string> = {
    success: "green",
    failed: "red",
    skipped: "default",
    partial: "orange",
    none: "default"
  };
  const labelMap: Record<string, string> = {
    success: "同步成功",
    failed: "同步失败",
    skipped: "已跳过",
    partial: "部分成功",
    none: "未执行"
  };
  const tag = <Tag color={colorMap[status] ?? "default"}>{labelMap[status] ?? status}</Tag>;
  return errorMessage ? <Tooltip title={errorMessage}>{tag}</Tooltip> : tag;
};

const renderSkipReason = (reason?: string | null) => {
  if (!reason) {
    return "-";
  }
  const reasonMap: Record<string, string> = {
    duplicate: "同名文件已存在，已跳过同步"
  };
  return reasonMap[reason] ?? reason;
};

function ImaSyncRecordsPage() {
  const [form] = Form.useForm();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [filters, setFilters] = useState<FilterState>({});
  const [selectedBatch, setSelectedBatch] = useState<ImaSyncBatch | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const taskIdWatch = Form.useWatch("task_id", form);
  const triggerModeWatch = Form.useWatch("trigger_mode", form) as TriggerMode | undefined;
  const inferredSyncScope =
    triggerModeWatch === "daily_report_job_sync"
      ? "daily_report_job"
      : triggerModeWatch === "ima_auto_sync"
        ? "ima_sync_job"
        : undefined;

  const tasksQuery = useQuery({ queryKey: ["tasks", "options"], queryFn: fetchTasks, staleTime: 60_000 });
  const accountsQuery = useQuery({ queryKey: ["ima-accounts", "options"], queryFn: fetchImaAccounts, staleTime: 60_000 });
  const syncJobsQuery = useQuery({ queryKey: ["ima-sync-jobs"], queryFn: fetchImaSyncJobs, staleTime: 60_000 });
  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["ima-sync-record-batches", page, pageSize, filters],
    keepPreviousData: true,
    queryFn: () =>
      fetchImaSyncBatches({
        page,
        page_size: pageSize,
        ...filters
      })
  });
  const batchItemsQuery = useQuery({
    queryKey: ["ima-sync-batch-items", selectedBatch?.batch_id],
    queryFn: () => fetchImaBatchItems(selectedBatch?.batch_id ?? ""),
    enabled: Boolean(selectedBatch?.batch_id)
  });

  const batchPage: ImaSyncBatchPage | undefined = data;
  const tableData = batchPage?.items ?? [];
  const total = batchPage?.total ?? 0;

  const tasks = tasksQuery.data ?? [];
  const jobOptions = useMemo(() => {
    const current = tasks.find((item) => item.id === taskIdWatch);
    return current?.jobs ?? [];
  }, [taskIdWatch, tasks]);

  useEffect(() => {
    const executionId = searchParams.get("executionId");
    const batchId = searchParams.get("batchId");
    if (!executionId && !batchId) {
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.delete("executionId");
    next.delete("batchId");
    setSearchParams(next, { replace: true });
    const values: Record<string, unknown> = {};
    if (executionId) {
      const numericId = Number(executionId);
      if (!Number.isNaN(numericId) && numericId > 0) {
        values.execution_id = numericId;
      }
    }
    if (batchId) {
      values.batch_id = batchId;
    }
    form.setFieldsValue(values);
    setFilters((prev) => ({
      ...prev,
      execution_id: values.execution_id as number | undefined,
      batch_id: values.batch_id as string | undefined
    }));
    setPage(1);
  }, [form, searchParams, setSearchParams]);

  const handleSearch = () => {
    const values = form.getFieldsValue();
    const triggerMode = values.trigger_mode as TriggerMode | undefined;
    const triggerType =
      triggerMode === "daily_report_job_sync" ? "job" : triggerMode === "ima_auto_sync" ? "auto" : triggerMode === "manual_sync" ? "manual" : undefined;
    const syncScope =
      triggerMode === "daily_report_job_sync" ? "daily_report_job" : triggerMode === "ima_auto_sync" ? "ima_sync_job" : undefined;
    const timeRange = values.time_range as [Dayjs, Dayjs] | undefined;
    setFilters({
      ima_account_id: values.ima_account_id ?? undefined,
      status: values.status ?? undefined,
      trigger_type: triggerType,
      task_id: values.task_id ?? undefined,
      job_id: values.job_id ?? undefined,
      sync_job_id: values.sync_job_id ?? undefined,
      sync_scope: syncScope,
      execution_id: values.execution_id ?? undefined,
      batch_id: values.batch_id?.trim() || undefined,
      query: values.query?.trim() || undefined,
      start_time: timeRange?.[0]?.format("YYYY-MM-DD HH:mm"),
      end_time: timeRange?.[1]?.format("YYYY-MM-DD HH:mm")
    });
    setPage(1);
  };

  const handleReset = () => {
    form.resetFields();
    setFilters({});
    setPage(1);
  };

  const buildExecutionHistoryUrl = (record: ImaSyncBatch) => {
    if (!record.execution_id) {
      return "/executions";
    }
    const params = new URLSearchParams({ execution_id: String(record.execution_id) });
    if (record.task_id) {
      params.set("task_id", String(record.task_id));
    }
    if (record.job_id) {
      params.set("job_id", String(record.job_id));
    }
    return `/executions?${params.toString()}`;
  };

  const columns: ColumnsType<ImaSyncBatch> = [
    {
      title: "批次时间",
      dataIndex: "created_at",
      key: "created_at",
      render: (value) => formatUtcDateTime(value)
    },
    {
      title: "批次ID",
      dataIndex: "batch_id",
      key: "batch_id",
      render: (value: string) => (
        <Tooltip title={value}>
          <span>{value.slice(0, 12)}</span>
        </Tooltip>
      )
    },
    {
      title: "日报执行ID",
      key: "daily_report_execution_id",
      render: (_, record) =>
        record.sync_scope === "daily_report_job" && record.execution_id ? `#${record.execution_id}` : "-"
    },
    {
      title: "ima账号",
      key: "ima_account_name",
      render: (_, record) => record.ima_account_name || "-"
    },
    {
      title: "触发方式",
      key: "trigger_type",
      render: (_, record) => getBatchTriggerLabel(record)
    },
    {
      title: "归属对象",
      key: "owner",
      render: (_, record) =>
        record.sync_scope === "ima_sync_job"
          ? record.sync_job_name || "-"
          : `${record.task_name || "-"} / ${record.job_name || "-"}`
    },
    {
      title: "执行时目标位置",
      dataIndex: "target_display",
      key: "target_display"
    },
    {
      title: "结果",
      key: "summary",
      render: (_, record) => (
        <Space direction="vertical" size={2}>
          {renderStatus(record.status)}
          <span>{record.summary}</span>
        </Space>
      )
    },
    {
      title: "操作",
      key: "actions",
      width: 220,
      render: (_, record) => (
        <Space wrap>
          <Button type="link" onClick={() => setSelectedBatch(record)}>
            查看详情
          </Button>
          {record.sync_scope === "daily_report_job" && record.execution_id ? (
            <Button type="link" onClick={() => navigate(buildExecutionHistoryUrl(record))}>
              查看日报作业执行详情
            </Button>
          ) : null}
        </Space>
      )
    }
  ];

  const detailColumns: ColumnsType<ImaSyncRecord> = [
    {
      title: "时间",
      dataIndex: "created_at",
      key: "created_at",
      width: 180,
      render: (value) => formatUtcDateTime(value)
    },
    {
      title: "状态",
      key: "status",
      width: 120,
      render: (_, record) =>
        renderStatus(
          record.status,
          record.error_code ? `[${record.error_code}] ${record.error_message ?? ""}` : record.error_message
        )
    },
    {
      title: "文件名",
      dataIndex: "source_name",
      key: "source_name",
      width: 340,
      render: (value?: string | null) =>
        value ? (
          <Tooltip title={value}>
            <Paragraph style={{ marginBottom: 0, maxWidth: 320 }} ellipsis={{ rows: 1 }}>
              {value}
            </Paragraph>
          </Tooltip>
        ) : (
          "-"
        )
    },
    {
      title: "本地路径",
      dataIndex: "source_path",
      key: "source_path",
      width: 320,
      render: (value?: string | null) =>
        value ? (
          <Tooltip title={value}>
            <Paragraph style={{ marginBottom: 0, maxWidth: 300 }} ellipsis={{ rows: 1 }}>
              {value}
            </Paragraph>
          </Tooltip>
        ) : (
          "-"
        )
    },
    {
      title: "执行时目标位置",
      key: "target",
      width: 260,
      render: (_, record) =>
        record.target_type === "note"
          ? `ima 笔记 / ${record.note_folder_name || "-"}`
          : `ima 知识库 / ${record.knowledge_base_name || "-"} / ${record.knowledge_folder_name || "根目录"}`
    },
    {
      title: "说明",
      key: "message",
      width: 420,
      render: (_, record) => {
        if (record.error_code || record.error_message || record.error_explanation) {
          return (
            <Space direction="vertical" size={2}>
              {record.error_code ? <span>错误码：{record.error_code}</span> : null}
              {record.error_message ? (
                <Tooltip title={record.error_message}>
                  <Paragraph style={{ marginBottom: 0, maxWidth: 400 }} ellipsis={{ rows: 2 }}>
                    原始返回：{record.error_message}
                  </Paragraph>
                </Tooltip>
              ) : null}
              {record.error_explanation ? <span>文档解释：{record.error_explanation}</span> : null}
            </Space>
          );
        }
        return renderSkipReason(record.skip_reason);
      }
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

  const neutralCardStyle = {
    padding: 14,
    borderRadius: 10,
    background: "#fafafa",
    border: "1px solid #f0f0f0"
  };

  const neutralTitleStyle = {
    color: "#595959",
    fontSize: 12,
    marginBottom: 6
  };

  const summaryStyleMap: Record<string, { background: string; border: string; title: string }> = {
    success: { background: "#f6ffed", border: "#d9f7be", title: "#389e0d" },
    failed: { background: "#fff2f0", border: "#ffccc7", title: "#cf1322" },
    partial: { background: "#fff7e6", border: "#ffe7ba", title: "#d46b08" },
    skipped: { background: "#fafafa", border: "#f0f0f0", title: "#595959" },
    none: { background: "#fafafa", border: "#f0f0f0", title: "#595959" }
  };

  const summaryColors = selectedBatch ? summaryStyleMap[selectedBatch.status] ?? summaryStyleMap.none : summaryStyleMap.none;

  return (
    <div>
      <Form
        form={form}
        layout="inline"
        onFinish={handleSearch}
        style={{ marginBottom: 16, display: "flex", flexWrap: "wrap", gap: 12 }}
      >
        <Form.Item label="触发方式" name="trigger_mode" style={{ marginBottom: 8 }}>
          <Select
            allowClear
            placeholder="全部触发方式"
            style={{ width: 180 }}
            options={[
              { label: "群聊日报作业同步", value: "daily_report_job_sync" },
              { label: "ima自动同步", value: "ima_auto_sync" },
              { label: "手动同步", value: "manual_sync" }
            ]}
            onChange={(value?: TriggerMode) => {
              if (value === "ima_auto_sync") {
                form.setFieldsValue({ task_id: undefined, job_id: undefined });
              } else if (value === "daily_report_job_sync") {
                form.setFieldValue("sync_job_id", undefined);
              }
            }}
          />
        </Form.Item>
        <Form.Item label="ima账号" name="ima_account_id" style={{ marginBottom: 8 }}>
          <Select
            allowClear
            placeholder="全部账号"
            style={{ minWidth: 200 }}
            loading={accountsQuery.isLoading}
            options={(accountsQuery.data ?? []).map((account) => ({ label: account.name, value: account.id }))}
          />
        </Form.Item>
        <Form.Item label="任务" name="task_id" style={{ marginBottom: 8 }}>
          <Select
            allowClear
            placeholder="全部任务"
            style={{ minWidth: 200 }}
            loading={tasksQuery.isLoading}
            disabled={inferredSyncScope === "ima_sync_job"}
            options={tasks.map((task) => ({ label: task.name, value: task.id }))}
            onChange={() => form.setFieldValue("job_id", undefined)}
          />
        </Form.Item>
        <Form.Item label="作业" name="job_id" style={{ marginBottom: 8 }}>
          <Tooltip title={!taskIdWatch && inferredSyncScope !== "ima_sync_job" ? "请先选择任务" : undefined}>
            <span style={{ display: "inline-block" }}>
              <Select
                allowClear
                placeholder="全部作业"
                style={{ minWidth: 200 }}
                disabled={!taskIdWatch || inferredSyncScope === "ima_sync_job"}
                options={jobOptions.map((job) => ({ label: job.name, value: job.id }))}
              />
            </span>
          </Tooltip>
        </Form.Item>
        <Form.Item label="ima同步作业" name="sync_job_id" style={{ marginBottom: 8 }}>
          <Select
            allowClear
            placeholder="全部ima同步作业"
            style={{ minWidth: 220 }}
            disabled={inferredSyncScope === "daily_report_job"}
            loading={syncJobsQuery.isLoading}
            options={(syncJobsQuery.data ?? []).map((job) => ({ label: job.name, value: job.id }))}
          />
        </Form.Item>
        <Form.Item label="状态" name="status" style={{ marginBottom: 8 }}>
          <Select
            allowClear
            placeholder="全部状态"
            style={{ width: 160 }}
            options={[
              { label: "同步成功", value: "success" },
              { label: "同步失败", value: "failed" },
              { label: "已跳过", value: "skipped" },
              { label: "部分成功", value: "partial" }
            ]}
          />
        </Form.Item>
        <Form.Item label="执行记录ID" name="execution_id" style={{ marginBottom: 8 }}>
          <InputNumber min={1} style={{ width: 160 }} placeholder="输入执行ID" />
        </Form.Item>
        <Form.Item label="批次ID" name="batch_id" style={{ marginBottom: 8 }}>
          <Input placeholder="输入批次ID" style={{ width: 220 }} />
        </Form.Item>
        <Form.Item label="关键字" name="query" style={{ marginBottom: 8 }}>
          <Input placeholder="作业名 / 文件名 / 路径 / 错误信息" style={{ width: 240 }} />
        </Form.Item>
        <Form.Item label="同步时间" name="time_range" style={{ marginBottom: 8 }}>
          <RangePicker showTime={{ format: "HH:mm" }} format="YYYY-MM-DD HH:mm" allowClear />
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

      <Table<ImaSyncBatch>
        rowKey={(record) => record.batch_id}
        dataSource={tableData}
        columns={columns}
        loading={isLoading || isFetching}
        pagination={pagination}
        scroll={{ x: "max-content" }}
        locale={{ emptyText: "暂无 ima 同步批次记录" }}
      />

      <Modal
        open={Boolean(selectedBatch)}
        width={1480}
        centered
        footer={null}
        destroyOnClose
        title={selectedBatch ? `同步批次详情 ${selectedBatch.batch_id.slice(0, 12)}` : "同步批次详情"}
        onCancel={() => setSelectedBatch(null)}
      >
        {selectedBatch ? (
          <Space direction="vertical" size={16} style={{ width: "100%" }}>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                gap: 12
              }}
            >
              <div style={neutralCardStyle}>
                <div style={neutralTitleStyle}>批次时间</div>
                <div>{formatUtcDateTime(selectedBatch.created_at)}</div>
              </div>
              <div style={neutralCardStyle}>
                <div style={neutralTitleStyle}>触发方式</div>
                <div>{getBatchTriggerLabel(selectedBatch)}</div>
              </div>
              <div style={neutralCardStyle}>
                <div style={neutralTitleStyle}>归属对象</div>
                <div>
                  {selectedBatch.sync_scope === "ima_sync_job"
                    ? selectedBatch.sync_job_name || "-"
                    : `${selectedBatch.task_name || "-"} / ${selectedBatch.job_name || "-"}`}
                </div>
              </div>
              <div style={neutralCardStyle}>
                <div style={neutralTitleStyle}>ima账号</div>
                <div>{selectedBatch.ima_account_name || "-"}</div>
              </div>
              <div style={neutralCardStyle}>
                <div style={neutralTitleStyle}>执行时目标位置</div>
                <div>{selectedBatch.target_display}</div>
              </div>
              <div
                style={{
                  padding: 14,
                  borderRadius: 10,
                  background: summaryColors.background,
                  border: `1px solid ${summaryColors.border}`,
                  gridColumn: "1 / -1"
                }}
              >
                <div style={{ color: summaryColors.title, fontSize: 12, marginBottom: 6 }}>结果汇总</div>
                <div>{selectedBatch.summary}</div>
              </div>
            </div>
            <Table<ImaSyncRecord>
              rowKey={(record) => record.id}
              dataSource={batchItemsQuery.data ?? []}
              columns={detailColumns}
              loading={batchItemsQuery.isLoading || batchItemsQuery.isFetching}
              pagination={false}
              scroll={{ x: 1440 }}
              locale={{ emptyText: "该批次暂无明细记录" }}
            />
          </Space>
        ) : null}
      </Modal>
    </div>
  );
}

export default ImaSyncRecordsPage;
