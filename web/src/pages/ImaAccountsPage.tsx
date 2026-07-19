import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Popconfirm, Space, Table, Tag, Tooltip, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { PlusOutlined } from "@ant-design/icons";
import {
  createImaAccount,
  deleteImaAccount,
  fetchImaAccounts,
  testImaAccount,
  updateImaAccount,
  type ImaAccount,
  type ImaAccountPayload
} from "../services/ima";
import { formatBeijingDateTime } from "../utils/datetime";
import ImaAccountFormModal from "../components/ImaAccountFormModal";

const { Paragraph, Title } = Typography;

function ImaAccountsPage() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingAccount, setEditingAccount] = useState<ImaAccount | null>(null);

  const accountsQuery = useQuery({
    queryKey: ["ima-accounts"],
    queryFn: fetchImaAccounts,
    staleTime: 30_000
  });

  const createMutation = useMutation({
    mutationFn: (payload: ImaAccountPayload) => createImaAccount(payload),
    onSuccess: async () => {
      message.success("ima 账号已创建");
      setModalOpen(false);
      setEditingAccount(null);
      await queryClient.invalidateQueries({ queryKey: ["ima-accounts"] });
      await queryClient.invalidateQueries({ queryKey: ["ima-settings"] });
    },
    onError: (error) => {
      const err = error as Error;
      message.error(err.message || "创建 ima 账号失败");
    }
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: ImaAccountPayload }) => updateImaAccount(id, payload),
    onSuccess: async () => {
      message.success("ima 账号已更新");
      setModalOpen(false);
      setEditingAccount(null);
      await queryClient.invalidateQueries({ queryKey: ["ima-accounts"] });
      await queryClient.invalidateQueries({ queryKey: ["ima-settings"] });
      await queryClient.invalidateQueries({ queryKey: ["ima-sync-jobs"] });
    },
    onError: (error) => {
      const err = error as Error;
      message.error(err.message || "更新 ima 账号失败");
    }
  });

  const deleteMutation = useMutation({
    mutationFn: (accountId: number) => deleteImaAccount(accountId),
    onSuccess: async () => {
      message.success("ima 账号已删除");
      await queryClient.invalidateQueries({ queryKey: ["ima-accounts"] });
      await queryClient.invalidateQueries({ queryKey: ["ima-settings"] });
    },
    onError: (error) => {
      const err = error as Error;
      message.error(err.message || "删除 ima 账号失败");
    }
  });

  const testMutation = useMutation({
    mutationFn: (accountId: number) => testImaAccount(accountId),
    onSuccess: async (result) => {
      message.success(result.message);
      await queryClient.invalidateQueries({ queryKey: ["ima-accounts"] });
    },
    onError: (error) => {
      const err = error as Error;
      message.error(err.message || "测试 ima 账号失败");
      void queryClient.invalidateQueries({ queryKey: ["ima-accounts"] });
    }
  });

  const columns: ColumnsType<ImaAccount> = [
    {
      title: "账号名称",
      dataIndex: "name",
      key: "name",
      render: (_, record) => (
        <Space>
          <span>{record.name}</span>
          {record.is_default ? <Tag color="blue">默认账号</Tag> : null}
        </Space>
      )
    },
    {
      title: "Client ID",
      dataIndex: "client_id_masked",
      key: "client_id_masked"
    },
    {
      title: "状态",
      key: "status",
      render: (_, record) => (record.is_enabled ? <Tag color="green">已启用</Tag> : <Tag>已停用</Tag>)
    },
    {
      title: "默认目标",
      key: "default_target",
      render: (_, record) =>
        record.default_target_type === "note"
          ? `ima 笔记 / ${record.default_note_folder_name || "-"}`
          : `ima 知识库 / ${record.default_knowledge_base_name || "-"} / ${record.default_knowledge_folder_name || "根目录"}`
    },
    {
      title: "备注",
      dataIndex: "remark",
      key: "remark",
      width: 260,
      render: (value?: string | null) =>
        value ? (
          <Tooltip title={value}>
            <Paragraph style={{ marginBottom: 0, maxWidth: 240 }} ellipsis={{ rows: 2 }}>
              {value}
            </Paragraph>
          </Tooltip>
        ) : (
          "-"
        )
    },
    {
      title: "最近测试",
      key: "last_test",
      width: 260,
      render: (_, record) => (
        <Space direction="vertical" size={2}>
          <span>{formatBeijingDateTime(record.last_test_at)}</span>
          {record.last_test_status ? (
            <Tooltip title={record.last_test_message || undefined}>
              <Tag color={record.last_test_status === "success" ? "green" : "red"}>
                {record.last_test_status === "success" ? "连接成功" : "连接失败"}
              </Tag>
            </Tooltip>
          ) : (
            <Tag>未测试</Tag>
          )}
        </Space>
      )
    },
    {
      title: "更新时间",
      dataIndex: "updated_at",
      key: "updated_at",
      width: 180,
      render: (value: string) => formatBeijingDateTime(value)
    },
    {
      title: "操作",
      key: "actions",
      width: 260,
      render: (_, record) => (
        <Space wrap>
          <Button
            type="link"
            onClick={() => {
              setEditingAccount(record);
              setModalOpen(true);
            }}
          >
            编辑
          </Button>
          <Button type="link" loading={testMutation.isPending} onClick={() => testMutation.mutate(record.id)}>
            测试连接
          </Button>
          <Popconfirm title="确认删除这个 ima 账号吗？" onConfirm={() => deleteMutation.mutate(record.id)}>
            <Button type="link" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      )
    }
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card>
        <Title level={4} style={{ marginTop: 0 }}>
          ima账号管理
        </Title>
        <Paragraph type="secondary" style={{ marginBottom: 0 }}>
          这里维护多个 ima 账号。账号名称由你自己定义，后续群聊日报作业和 ima 自动同步作业都会按这个名称选择账号。
        </Paragraph>
      </Card>

      <Card
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setEditingAccount(null);
              setModalOpen(true);
            }}
          >
            新增ima账号
          </Button>
        }
      >
        <Table<ImaAccount>
          rowKey={(record) => record.id}
          dataSource={accountsQuery.data ?? []}
          columns={columns}
          loading={accountsQuery.isLoading || accountsQuery.isFetching}
          pagination={false}
          locale={{ emptyText: "暂无 ima 账号配置" }}
          scroll={{ x: "max-content" }}
        />
      </Card>

      <ImaAccountFormModal
        open={modalOpen}
        initialValues={editingAccount}
        confirmLoading={createMutation.isPending || updateMutation.isPending}
        onCancel={() => {
          setModalOpen(false);
          setEditingAccount(null);
        }}
        onSubmit={async (payload) => {
          if (editingAccount) {
            await updateMutation.mutateAsync({ id: editingAccount.id, payload });
            return;
          }
          await createMutation.mutateAsync(payload);
        }}
      />
    </Space>
  );
}

export default ImaAccountsPage;
