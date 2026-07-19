import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Popconfirm, Space, Table, Tag, Tooltip, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { PlusOutlined, SyncOutlined } from "@ant-design/icons";
import {
  createImaSyncJob,
  fetchImaAccounts,
  fetchImaSyncJobs,
  runImaSyncJob,
  updateImaSyncJob,
  deleteImaSyncJob,
  type ImaSyncJob,
  type ImaSyncJobPayload
} from "../services/ima";
import { fetchWebhooks } from "../services/webhooks";
import { formatBeijingDateTime } from "../utils/datetime";
import ImaSyncJobFormModal from "../components/ImaSyncJobFormModal";

const { Paragraph, Title } = Typography;

const renderStatus = (status?: string | null) => {
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
  return <Tag color={colorMap[status ?? "none"] ?? "default"}>{labelMap[status ?? "none"] ?? "未执行"}</Tag>;
};

function ImaSettingsPage() {
  const queryClient = useQueryClient();
  const [jobModalOpen, setJobModalOpen] = useState(false);
  const [editingJob, setEditingJob] = useState<ImaSyncJob | null>(null);

  const accountsQuery = useQuery({
    queryKey: ["ima-accounts"],
    queryFn: fetchImaAccounts,
    staleTime: 30_000
  });
  const syncJobsQuery = useQuery({
    queryKey: ["ima-sync-jobs"],
    queryFn: fetchImaSyncJobs,
    staleTime: 30_000
  });
  const webhooksQuery = useQuery({
    queryKey: ["webhooks", "options"],
    queryFn: fetchWebhooks,
    staleTime: 60_000
  });

  const createJobMutation = useMutation({
    mutationFn: (payload: ImaSyncJobPayload) => createImaSyncJob(payload),
    onSuccess: async () => {
      message.success("ima 同步作业已创建");
      setJobModalOpen(false);
      setEditingJob(null);
      await queryClient.invalidateQueries({ queryKey: ["ima-sync-jobs"] });
    },
    onError: (error) => {
      const err = error as Error;
      message.error(err.message || "创建 ima 同步作业失败");
    }
  });

  const updateJobMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: ImaSyncJobPayload }) => updateImaSyncJob(id, payload),
    onSuccess: async () => {
      message.success("ima 同步作业已更新");
      setJobModalOpen(false);
      setEditingJob(null);
      await queryClient.invalidateQueries({ queryKey: ["ima-sync-jobs"] });
    },
    onError: (error) => {
      const err = error as Error;
      message.error(err.message || "更新 ima 同步作业失败");
    }
  });

  const deleteJobMutation = useMutation({
    mutationFn: (id: number) => deleteImaSyncJob(id),
    onSuccess: async () => {
      message.success("ima 同步作业已删除");
      await queryClient.invalidateQueries({ queryKey: ["ima-sync-jobs"] });
    },
    onError: (error) => {
      const err = error as Error;
      message.error(err.message || "删除 ima 同步作业失败");
    }
  });

  const runJobMutation = useMutation({
    mutationFn: (id: number) => runImaSyncJob(id),
    onSuccess: async (result) => {
      message.success(result.message);
      await queryClient.invalidateQueries({ queryKey: ["ima-sync-jobs"] });
      await queryClient.invalidateQueries({ queryKey: ["ima-sync-record-batches"] });
    },
    onError: (error) => {
      const err = error as Error;
      message.error(err.message || "执行 ima 同步作业失败");
    }
  });

  const columns: ColumnsType<ImaSyncJob> = [
    {
      title: "作业名称",
      dataIndex: "name",
      key: "name"
    },
    {
      title: "状态",
      key: "status",
      render: (_, record) => (record.is_enabled ? <Tag color="green">已启用</Tag> : <Tag>已停用</Tag>)
    },
    {
      title: "ima账号",
      key: "ima_account_name",
      render: (_, record) => record.ima_account_name || "-"
    },
    {
      title: "本地同步路径",
      dataIndex: "local_sync_path",
      key: "local_sync_path",
      width: 220,
      render: (value: string) => (
        <Tooltip title={value}>
          <Paragraph style={{ marginBottom: 0, maxWidth: 200 }} ellipsis={{ rows: 1 }}>
            {value}
          </Paragraph>
        </Tooltip>
      )
    },
    {
      title: "目标位置",
      key: "target",
      render: (_, record) =>
        record.target_type === "note"
          ? `ima 笔记 / ${record.note_folder_name || "-"}`
          : `ima 知识库 / ${record.knowledge_base_name || "-"} / ${record.knowledge_folder_name || "根目录"}`
    },
    {
      title: "执行频率",
      key: "schedule",
      render: (_, record) =>
        record.schedule_frequency === "weekly"
          ? `每周 ${["周一", "周二", "周三", "周四", "周五", "周六", "周日"][record.schedule_weekday ?? 0]} ${record.schedule_time}`
          : `每天 ${record.schedule_time}`
    },
    {
      title: "告警Webhook",
      key: "webhook",
      render: (_, record) => record.webhook_name || "-"
    },
    {
      title: "最近同步",
      key: "last_sync",
      render: (_, record) => (
        <Space direction="vertical" size={2}>
          <span>{formatBeijingDateTime(record.last_sync_at)}</span>
          {renderStatus(record.last_sync_status)}
        </Space>
      )
    },
    {
      title: "下次执行",
      dataIndex: "next_run_at",
      key: "next_run_at",
      render: (value?: string | null) => formatBeijingDateTime(value)
    },
    {
      title: "更新时间",
      dataIndex: "updated_at",
      key: "updated_at",
      render: (value: string) => formatBeijingDateTime(value)
    },
    {
      title: "操作",
      key: "actions",
      width: 260,
      render: (_, record) => (
        <div style={{ display: "flex", alignItems: "center", gap: 12, whiteSpace: "nowrap" }}>
          <Button
            type="link"
            onClick={() => {
              setEditingJob(record);
              setJobModalOpen(true);
            }}
          >
            编辑
          </Button>
          <Button
            type="link"
            icon={<SyncOutlined />}
            loading={runJobMutation.isPending}
            onClick={() => runJobMutation.mutate(record.id)}
          >
            手动同步
          </Button>
          <Popconfirm title="确认删除这个 ima 同步作业吗？" onConfirm={() => deleteJobMutation.mutate(record.id)}>
            <Button type="link" danger>
              删除
            </Button>
          </Popconfirm>
        </div>
      )
    }
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card>
        <Title level={4} style={{ marginTop: 0 }}>
          ima知识库同步设置
        </Title>
        <Paragraph type="secondary" style={{ marginBottom: 0 }}>
          这里不再维护账号凭证与默认账号，只维护独立的 ima 自动同步作业列表。账号默认目标请到“ima账号管理”里配置。
        </Paragraph>
      </Card>

      <Card
        title="ima自动同步作业列表"
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setEditingJob(null);
              setJobModalOpen(true);
            }}
          >
            新增同步作业
          </Button>
        }
      >
        <Paragraph type="secondary">
          这里的同步作业只负责“本地目录 -&gt; ima”的定时/手动同步，和群聊日报“任务&作业”页面里的作业是两套独立能力。
        </Paragraph>
        <Table<ImaSyncJob>
          rowKey={(record) => record.id}
          dataSource={syncJobsQuery.data ?? []}
          columns={columns}
          loading={syncJobsQuery.isLoading || syncJobsQuery.isFetching}
          pagination={false}
          locale={{ emptyText: "暂无 ima 自动同步作业" }}
          scroll={{ x: "max-content" }}
        />
      </Card>

      <ImaSyncJobFormModal
        open={jobModalOpen}
        initialValues={editingJob}
        confirmLoading={createJobMutation.isPending || updateJobMutation.isPending}
        webhookOptions={(webhooksQuery.data ?? []).map((item) => ({ label: item.name, value: item.id }))}
        accountOptions={(accountsQuery.data ?? []).map((item) => ({ label: item.name, value: item.id }))}
        onCancel={() => {
          setJobModalOpen(false);
          setEditingJob(null);
        }}
        onSubmit={async (payload) => {
          if (editingJob) {
            await updateJobMutation.mutateAsync({ id: editingJob.id, payload });
            return;
          }
          await createJobMutation.mutateAsync(payload);
        }}
      />
    </Space>
  );
}

export default ImaSettingsPage;
