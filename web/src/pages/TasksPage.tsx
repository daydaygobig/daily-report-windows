import React, { useContext, useEffect, useMemo, useState } from "react";
import { Button, Popconfirm, Space, Table, Tag, Tooltip, message } from "antd";
import { MenuOutlined, ReloadOutlined } from "@ant-design/icons";
import {
  DragDropContext,
  Droppable,
  Draggable,
  type DropResult,
  type DraggableProvidedDragHandleProps
} from "@hello-pangea/dnd";
import type { ColumnsType } from "antd/es/table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import TaskFormModal from "../components/TaskFormModal";
import JobFormModal from "../components/JobFormModal";
import type { Job, JobPayload, Task, TaskPayload } from "../services/tasks";
import {
  fetchTasks,
  createJob,
  createTask,
  deleteJob,
  deleteTask,
  runJob as runJobRequest,
  updateJob,
  updateTask,
  reorderJobs
} from "../services/tasks";
import { fetchChatrooms } from "../services/chatRecords";
import { formatBeijingDateTime } from "../utils/datetime";

const DragHandleContext = React.createContext<DraggableProvidedDragHandleProps | null>(null);

const scheduleTypeLabels: Record<string, string> = {
  daily: "每日",
  weekday: "工作日",
  weekend: "周末",
  weekly: "自定义周几",
  weekly_report: "周报模式",
  manual: "手动执行",
  custom_cron: "自定义 Cron"
};

const weekdayLabelMap: Record<number, string> = {
  0: "周一",
  1: "周二",
  2: "周三",
  3: "周四",
  4: "周五",
  5: "周六",
  6: "周日"
};

const getErrorMessage = (error: unknown): string => {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: { message?: string } })?.detail;
    if (detail && typeof detail === "object" && "message" in detail) {
      return (detail as { message?: string }).message ?? "请求失败";
    }
    return error.message;
  }
  return (error as Error)?.message ?? "请求失败";
};

const formatWeekdays = (weekdays?: number[] | null) =>
  weekdays && weekdays.length
    ? weekdays
        .map((day) => weekdayLabelMap[day] ?? `#${day}`)
        .join("、")
    : "-";

const DragHandleCell: React.FC = () => {
  const dragHandleProps = useContext(DragHandleContext);
  return (
    <Tooltip title="按住拖拽调整顺序">
      <span
        className="drag-handle"
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: "100%",
          cursor: dragHandleProps ? "grab" : "not-allowed"
        }}
        {...(dragHandleProps ?? ({} as DraggableProvidedDragHandleProps))}
      >
        <MenuOutlined style={{ fontSize: 16 }} />
      </span>
    </Tooltip>
  );
};

function TasksPage() {
  const queryClient = useQueryClient();
  const { data: tasks, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["tasks"],
    queryFn: fetchTasks,
    refetchOnMount: "always"
  });
  const [talkerMap, setTalkerMap] = useState<Record<string, string>>({});
  const [taskModalOpen, setTaskModalOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const [jobModalState, setJobModalState] = useState<{ open: boolean; task: Task | null; job: Job | null }>({
    open: false,
    task: null,
    job: null
  });

  const invalidateTasks = () => queryClient.invalidateQueries({ queryKey: ["tasks"] });

  const replaceTaskInCache = (updatedTask: Task) => {
    queryClient.setQueryData<Task[] | undefined>(["tasks"], (current) =>
      current?.map((task) => (task.id === updatedTask.id ? updatedTask : task))
    );
  };

  const upsertJobInCache = (updatedJob: Job) => {
    queryClient.setQueryData<Task[] | undefined>(["tasks"], (current) =>
      current?.map((task) => {
        if (task.id !== updatedJob.task_id) {
          return task;
        }
        const exists = task.jobs.some((job) => job.id === updatedJob.id);
        return {
          ...task,
          jobs: exists
            ? task.jobs.map((job) => (job.id === updatedJob.id ? updatedJob : job))
            : [...task.jobs, updatedJob]
        };
      })
    );
  };

  const createTaskMutation = useMutation({
    mutationFn: createTask,
    onSuccess: (createdTask) => {
      queryClient.setQueryData<Task[] | undefined>(["tasks"], (current) =>
        current ? [...current, createdTask] : [createdTask]
      );
      return invalidateTasks();
    }
  });

  const updateTaskMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: TaskPayload }) => updateTask(id, payload),
    onSuccess: (updatedTask) => {
      replaceTaskInCache(updatedTask);
      return invalidateTasks();
    }
  });

  const deleteTaskMutation = useMutation({
    mutationFn: (id: number) => deleteTask(id),
    onSuccess: (_result, taskId) => {
      queryClient.setQueryData<Task[] | undefined>(["tasks"], (current) =>
        current?.filter((task) => task.id !== taskId)
      );
      return invalidateTasks();
    }
  });

  const createJobMutation = useMutation({
    mutationFn: ({ taskId, payload }: { taskId: number; payload: JobPayload }) => createJob(taskId, payload),
    onSuccess: (createdJob) => {
      upsertJobInCache(createdJob);
      return invalidateTasks();
    }
  });

  const updateJobMutation = useMutation({
    mutationFn: ({ jobId, payload }: { jobId: number; payload: JobPayload }) => updateJob(jobId, payload),
    onSuccess: (updatedJob) => {
      upsertJobInCache(updatedJob);
      return invalidateTasks();
    }
  });

  const deleteJobMutation = useMutation({
    mutationFn: (jobId: number) => deleteJob(jobId),
    onSuccess: (_result, jobId) => {
      queryClient.setQueryData<Task[] | undefined>(["tasks"], (current) =>
        current?.map((task) => ({
          ...task,
          jobs: task.jobs.filter((job) => job.id !== jobId)
        }))
      );
      return invalidateTasks();
    }
  });

  const runJobMutation = useMutation({
    mutationFn: (jobId: number) => runJobRequest(jobId),
    onSuccess: () => {
      invalidateTasks();
      message.success("作业执行完成");
    },
    onError: (error) => {
      message.error(getErrorMessage(error));
    }
  });

  const reorderJobsMutation = useMutation({
    mutationFn: ({ taskId, jobIds }: { taskId: number; jobIds: number[] }) => reorderJobs(taskId, jobIds),
    onSuccess: () => {
      invalidateTasks();
    },
    onError: (error) => {
      message.error(getErrorMessage(error));
      invalidateTasks();
    }
  });

  const openCreateTaskModal = () => {
    setEditingTask(null);
    setTaskModalOpen(true);
  };

  const openEditTaskModal = (task: Task) => {
    setEditingTask(task);
    setTaskModalOpen(true);
  };

  const closeTaskModal = () => {
    setTaskModalOpen(false);
    setEditingTask(null);
  };

  const handleTaskSubmit = async (values: TaskPayload) => {
    try {
      if (editingTask) {
        await updateTaskMutation.mutateAsync({ id: editingTask.id, payload: values });
        message.success("任务已更新");
      } else {
        await createTaskMutation.mutateAsync(values);
        message.success("任务已创建");
      }
      closeTaskModal();
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  };

  const handleDeleteTask = async (taskId: number) => {
    try {
      await deleteTaskMutation.mutateAsync(taskId);
      message.success("任务已删除");
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  };

  const openCreateJobModal = (task: Task) => {
    setJobModalState({ open: true, task, job: null });
  };

  const openEditJobModal = (task: Task, job: Job) => {
    setJobModalState({ open: true, task, job });
  };

  const closeJobModal = () => {
    setJobModalState({ open: false, task: null, job: null });
  };

  const handleJobSubmit = async (values: JobPayload) => {
    if (!jobModalState.task) {
      return;
    }
    try {
      if (jobModalState.job) {
        await updateJobMutation.mutateAsync({ jobId: jobModalState.job.id, payload: values });
        message.success("作业已更新");
      } else {
        await createJobMutation.mutateAsync({ taskId: jobModalState.task.id, payload: values });
        message.success("作业已创建");
      }
      closeJobModal();
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  };

  const handleDeleteJob = async (job: Job) => {
    try {
      await deleteJobMutation.mutateAsync(job.id);
      message.success("作业已删除");
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  };

  const [runningJobId, setRunningJobId] = useState<number | null>(null);

  const handleRunJob = async (jobId: number) => {
    try {
      setRunningJobId(jobId);
      await runJobMutation.mutateAsync(jobId);
    } finally {
      setRunningJobId(null);
    }
  };

  const updateTaskJobsOrder = useMemo(
    () => (taskId: number, newOrder: number[]) => {
      queryClient.setQueryData<Task[] | undefined>(["tasks"], (prev) => {
        if (!prev) {
          return prev;
        }
        return prev.map((task) => {
          if (task.id !== taskId) {
            return task;
          }
          const jobMap = new Map(task.jobs.map((job) => [job.id, job]));
          const reordered = newOrder
            .map((jobId, index) => {
              const existing = jobMap.get(jobId);
              if (!existing) {
                return null;
              }
              return { ...existing, display_order: index };
            })
            .filter(Boolean) as Job[];
          return { ...task, jobs: reordered };
        });
      });
    },
    [queryClient]
  );

  const handleJobReorder = async (task: Task, sourceIndex: number, destinationIndex: number) => {
    if (sourceIndex === destinationIndex) {
      return;
    }
    const orderedJobs = [...task.jobs].sort(
      (a, b) => (a.display_order ?? 0) - (b.display_order ?? 0) || a.id - b.id
    );
    if (
      sourceIndex < 0 ||
      destinationIndex < 0 ||
      sourceIndex >= orderedJobs.length ||
      destinationIndex >= orderedJobs.length
    ) {
      return;
    }
    const jobIds = orderedJobs.map((job) => job.id);
    const [removed] = jobIds.splice(sourceIndex, 1);
    jobIds.splice(destinationIndex, 0, removed);
    updateTaskJobsOrder(task.id, jobIds);
    await reorderJobsMutation.mutateAsync({ taskId: task.id, jobIds });
  };

  useEffect(() => {
    const fetchTalkerNames = async () => {
      if (!tasks || tasks.length === 0) {
        setTalkerMap({});
        return;
      }
      const ids = new Set<string>();
      const initial: Record<string, string> = {};
      tasks.forEach((task) => {
        (task.talkers ?? []).forEach((id, idx) => {
          ids.add(id);
          if (task.talker_names && task.talker_names[idx]) {
            initial[id] = task.talker_names[idx];
          }
        });
      });
      if (ids.size === 0) {
        setTalkerMap({});
        return;
      }
      try {
        const rooms = await fetchChatrooms(undefined, Array.from(ids));
        const map: Record<string, string> = { ...initial };
        rooms.forEach((room) => {
          map[room.name] = room.display_name;
        });
        setTalkerMap(map);
      } catch (error) {
        console.error("failed to fetch chatroom names", error);
      }
    };

    void fetchTalkerNames();
  }, [tasks]);

  const taskColumns: ColumnsType<Task> = [
    {
      title: "任务名称",
      dataIndex: "name",
      key: "name",
      width: 260,
      onCell: () => ({ style: { maxWidth: 260 } }),
      render: (value: string) =>
        value ? (
          <div className="text-clamp-2" style={{ fontWeight: 500, maxWidth: 260 }}>
            {value}
          </div>
        ) : (
          "-"
        )
    },
    {
      title: "提示词",
      dataIndex: "prompt",
      key: "prompt",
      width: 190,
      onCell: () => ({ style: { maxWidth: 190 } }),
      render: (value: string) =>
        value ? (
          <Tooltip title={<pre style={{ maxWidth: 320, whiteSpace: "pre-wrap" }}>{value}</pre>}>
            <div className="text-clamp-2" style={{ maxWidth: 190 }}>
              {value}
            </div>
          </Tooltip>
        ) : (
          "-"
        )
    },
    {
      title: "群聊",
      dataIndex: "talkers",
      key: "talkers",
      width: 140,
      render: (talkers: string[]) =>
        talkers.length ? (
          <Space size={[4, 4]} wrap>
            {talkers.map((item) => (
              <Tag key={item}>{talkerMap[item] ?? item}</Tag>
            ))}
          </Space>
        ) : (
          "-"
        )
    },
    {
      title: "启用状态",
      dataIndex: "is_active",
      key: "is_active",
      width: 90,
      onHeaderCell: () => ({ style: { whiteSpace: "nowrap" } }),
      render: (value: boolean) => (value ? <Tag color="green">启用</Tag> : <Tag color="red">停用</Tag>)
    },
    {
      title: "作业数量",
      dataIndex: "jobs",
      key: "jobs",
      width: 80,
      onHeaderCell: () => ({ style: { whiteSpace: "nowrap" } }),
      render: (jobs: Task["jobs"]) => jobs.length
    },
    {
      title: "更新时间",
      dataIndex: "updated_at",
      key: "updated_at",
      width: 170,
      render: (value: string) => formatBeijingDateTime(value)
    },
    {
      title: "操作",
      key: "actions",
      width: 150,
      render: (_, record) => (
        <Space size="small">
          <Button type="link" onClick={() => openEditTaskModal(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确认删除该任务？"
            okText="删除"
            cancelText="取消"
            onConfirm={() => handleDeleteTask(record.id)}
          >
            <Button type="link" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      )
    }
  ];

  const renderJobTable = (task: Task) => {
    const orderedJobs = [...task.jobs].sort(
      (a, b) => (a.display_order ?? 0) - (b.display_order ?? 0) || a.id - b.id
    );

    const jobColumns: ColumnsType<Job> = [
      {
        title: "",
        dataIndex: "drag",
        key: "drag",
        width: 56,
        render: () => <DragHandleCell />
      },
      {
        title: "作业名称",
        dataIndex: "name",
        key: "name",
        width: 200,
        onCell: () => ({ style: { maxWidth: 200 } }),
        render: (value: string) =>
          value ? (
            <div className="text-clamp-2" style={{ maxWidth: 200 }}>
              {value}
            </div>
          ) : (
            "-"
          )
      },
      {
        title: "聊天记录时间",
        key: "time",
        width: 200,
        onCell: () => ({ style: { maxWidth: 200 } }),
        render: (_, job) =>
          job.interval_enabled
            ? `${job.window_start ?? "00:00"} ~ ${job.window_end ?? "24:00"} · 每 ${job.interval_minutes ?? "-"} 分钟`
            : `${job.start_time} ~ ${job.end_time}`
      },
      {
        title: "执行时间",
        dataIndex: "execution_time",
        key: "execution_time",
        width: 120,
        render: (value: string | undefined | null) => value ?? "-"
      },
      {
        title: "调度类型",
        dataIndex: "schedule_type",
        key: "schedule_type",
        width: 160,
        onCell: () => ({ style: { maxWidth: 160 } }),
        render: (value: string, job) => {
          const label = scheduleTypeLabels[value] ?? value;
          if (value === "weekly") {
            return `${label}（${formatWeekdays(job.weekdays)}）`;
          }
          if (value === "weekly_report") {
            const periodLabel = job.weekly_period === "current_week" ? "当周" : "上一周";
            return `${label}（${periodLabel}）`;
          }
          if (value === "custom_cron") {
            return `${label}（${job.cron_expression ?? "-"}）`;
          }
          return label;
        }
      },
      {
        title: "启用",
        dataIndex: "is_enabled",
        key: "is_enabled",
        width: 80,
        render: (value: boolean) => (value ? <Tag color="green">启用</Tag> : <Tag color="red">停用</Tag>)
      },
      {
        title: "更新时间",
        dataIndex: "updated_at",
        key: "updated_at",
        width: 170,
        render: (value: string) => formatBeijingDateTime(value)
      },
      {
        title: "操作",
        key: "job-actions",
        fixed: "right",
        width: 200,
        render: (_, job) => (
          <Space size="small">
            <Button type="link" onClick={() => openEditJobModal(task, job)}>
              编辑
            </Button>
            <Button
              type="link"
              onClick={() => handleRunJob(job.id)}
              loading={runJobMutation.isPending && runningJobId === job.id}
            >
              手动执行
            </Button>
            <Popconfirm
              title="确认删除该作业？"
              okText="删除"
              cancelText="取消"
              onConfirm={() => handleDeleteJob(job)}
            >
              <Button type="link" danger>
                删除
              </Button>
            </Popconfirm>
          </Space>
        )
      }
    ];

    const DraggableBodyRow = (props: any) => {
      const { "data-row-key": rowKey, children, ...restProps } = props;
      const index = orderedJobs.findIndex((job) => job.id === rowKey);
      if (index === -1) {
        return <tr {...props} />;
      }
      return (
        <Draggable draggableId={`job-${rowKey}`} index={index} key={rowKey}>
          {(provided, snapshot) => (
            <DragHandleContext.Provider value={provided.dragHandleProps ?? null}>
              <tr
                {...restProps}
                {...provided.draggableProps}
                ref={provided.innerRef}
                data-row-key={rowKey}
                style={{
                  ...restProps.style,
                  ...provided.draggableProps.style,
                  cursor: snapshot.isDragging ? "grabbing" : "default"
                }}
                className={`${restProps.className ?? ""} ${snapshot.isDragging ? "dragging-row" : ""}`}
              >
                {children}
              </tr>
            </DragHandleContext.Provider>
          )}
        </Draggable>
      );
    };

    const DraggableContainer = (props: any) => {
      const { children, ...restProps } = props;
      return (
        <Droppable droppableId={`jobs-${task.id}`}>
          {(provided) => (
            <tbody {...restProps} ref={provided.innerRef} {...provided.droppableProps}>
              {children}
              {provided.placeholder}
            </tbody>
          )}
        </Droppable>
      );
    };

    const onDragEnd = (result: DropResult) => {
      if (!result.destination) {
        return;
      }
      void handleJobReorder(task, result.source.index, result.destination.index);
    };

    return (
      <div style={{ overflowX: "visible", paddingBottom: 8 }}>
        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
          <Button
            size="small"
            onClick={() => openCreateJobModal(task)}
            style={{ border: "1px dashed #d9d9d9" }}
          >
            新增作业
          </Button>
        </div>
        <DragDropContext onDragEnd={onDragEnd}>
          <Table<Job>
            columns={jobColumns}
            dataSource={orderedJobs}
            rowKey={(job) => job.id}
            pagination={false}
            size="small"
            locale={{ emptyText: "暂无作业" }}
            tableLayout="fixed"
            components={{
              body: {
                wrapper: DraggableContainer,
                row: DraggableBodyRow
              }
            }}
          />
        </DragDropContext>
      </div>
    );
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 16 }}>
        <Space>
          <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => void refetch()}>
            刷新
          </Button>
          <Button type="primary" onClick={openCreateTaskModal}>
            新增任务
          </Button>
        </Space>
      </div>
      <Table<Task>
        columns={taskColumns}
        loading={isLoading || isFetching}
        dataSource={tasks ?? []}
        rowKey={(record) => record.id}
        pagination={false}
        locale={{ emptyText: "暂无任务" }}
        tableLayout="fixed"
        expandable={{
          expandedRowRender: renderJobTable
        }}
      />
      <TaskFormModal
        open={taskModalOpen}
        initialValues={editingTask ?? undefined}
        confirmLoading={createTaskMutation.isPending || updateTaskMutation.isPending}
        onCancel={closeTaskModal}
        onSubmit={handleTaskSubmit}
      />
      <JobFormModal
        open={jobModalState.open}
        initialValues={jobModalState.job ?? undefined}
        taskType={jobModalState.task?.task_type}
        confirmLoading={createJobMutation.isPending || updateJobMutation.isPending}
        onCancel={closeJobModal}
        onSubmit={handleJobSubmit}
      />
    </div>
  );
}

export default TasksPage;
