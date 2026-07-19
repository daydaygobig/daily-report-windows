import { useMemo, useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Table, Tag, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useNavigate } from "react-router-dom";
import { fetchAlerts, type Alert } from "../services/alerts";
import { fetchTasks } from "../services/tasks";
import { formatDateTime } from "../utils/datetime";
import { useResizableColumns } from "../hooks/useResizableColumns";
import { fetchExecutionDetail, type Execution } from "../services/executions";
import ExecutionDetailModal from "../components/ExecutionDetailModal";

const PAGE_SIZE_OPTIONS = ["10", "20", "50", "100"];

function AlertsPage() {
  const { data, isLoading } = useQuery({ queryKey: ["alerts"], queryFn: fetchAlerts, refetchInterval: 60_000 });
  const tasksQuery = useQuery({ queryKey: ["tasks", "options"], queryFn: fetchTasks, staleTime: 60_000 });
  const navigate = useNavigate();
  const [executionDetail, setExecutionDetail] = useState<Execution | null>(null);
  const [loadingExecutionId, setLoadingExecutionId] = useState<number | null>(null);
  const taskMap = useMemo(() => {
    const map = new Map<number, string>();
    const jobs = new Map<number, string>();
    (tasksQuery.data ?? []).forEach((task) => {
      map.set(task.id, task.name);
      (task.jobs ?? []).forEach((job) => jobs.set(job.id, job.name));
    });
    return { map, jobs };
  }, [tasksQuery.data]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  const openExecutionDetail = useCallback(
    async (executionId: number) => {
      try {
        setLoadingExecutionId(executionId);
        const record = await fetchExecutionDetail(executionId);
        setExecutionDetail(record);
      } catch (error) {
        console.error(error);
        message.error("未找到该执行记录");
      } finally {
        setLoadingExecutionId((prev) => (prev === executionId ? null : prev));
      }
    },
    []
  );

  const baseColumns: (ColumnsType<Alert>[number] & { key: string })[] = useMemo(
    () => [
      {
        title: "执行ID",
        dataIndex: "execution_id",
        key: "execution_id",
        render: (value?: number | null) =>
          value ? (
            <Button type="link" onClick={() => openExecutionDetail(value)} loading={loadingExecutionId === value}>
              #{value}
            </Button>
          ) : (
            "-"
          )
      },
      {
        title: "任务名称",
        dataIndex: "task_id",
        key: "task_name",
        render: (taskId?: number | null) => (taskId ? taskMap.map.get(taskId) ?? `#${taskId}` : "-")
      },
      {
        title: "作业名称",
        dataIndex: "job_id",
        key: "job_name",
        render: (jobId?: number | null) => (jobId ? taskMap.jobs.get(jobId) ?? `#${jobId}` : "-")
      },
      { title: "类型", dataIndex: "category", key: "category" },
      {
        title: "信息",
        dataIndex: "message",
        key: "message",
        render: (value: string) => <div className="text-clamp">{value}</div>
      },
      {
        title: "等级",
        dataIndex: "level",
        key: "level",
        render: (level: string) => <Tag color={level === "error" ? "red" : "orange"}>{level}</Tag>
      },
      {
        title: "时间",
        dataIndex: "created_at",
        key: "created_at",
        render: (value: string) => formatDateTime(value)
      }
    ],
    [loadingExecutionId, openExecutionDetail, taskMap]
  );

  const { columns, components } = useResizableColumns<Alert>(baseColumns, "alerts_table_columns");

  const pagination = {
    current: page,
    pageSize,
    total: data?.length ?? 0,
    showSizeChanger: true,
    pageSizeOptions: PAGE_SIZE_OPTIONS,
    onChange: (nextPage: number, nextSize?: number) => {
      setPage(nextPage);
      if (nextSize && nextSize !== pageSize) {
        setPageSize(nextSize);
      }
    }
  };

  return (
    <>
      <Table
        loading={isLoading}
        dataSource={data ?? []}
        components={components}
        rowKey={(record) => record.id}
        pagination={pagination}
        columns={columns}
        scroll={{ x: "max-content" }}
        locale={{ emptyText: "暂无告警" }}
      />
      <ExecutionDetailModal
        execution={executionDetail}
        onClose={() => setExecutionDetail(null)}
        onOpenDeployRecord={(recordId) => navigate(`/github/deployments?recordId=${recordId}`)}
      />
    </>
  );
}

export default AlertsPage;
