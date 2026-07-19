import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Popconfirm, Space, Table, Tag, Tooltip, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import GithubConfigFormModal from "../components/GithubConfigFormModal";
import {
  createGithubConfig,
  deleteGithubConfig,
  fetchGithubConfigs,
  type GithubConfig,
  type GithubConfigPayload,
  type GithubConfigUpdatePayload,
  updateGithubConfig
} from "../services/githubConfigs";
import { formatBeijingDateTime } from "../utils/datetime";

const { Text } = Typography;

type ModalState = {
  open: boolean;
  config: GithubConfig | null;
};

function GithubConfigsPage() {
  const queryClient = useQueryClient();
  const { data: configs, isLoading } = useQuery({ queryKey: ["github-configs"], queryFn: fetchGithubConfigs });
  const [modalState, setModalState] = useState<ModalState>({ open: false, config: null });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["github-configs"] });

  const createMutation = useMutation({
    mutationFn: (payload: GithubConfigPayload) => createGithubConfig(payload),
    onSuccess: () => {
      invalidate();
      message.success("配置已创建");
      closeModal();
    }
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: GithubConfigUpdatePayload }) => updateGithubConfig(id, payload),
    onSuccess: () => {
      invalidate();
      message.success("配置已更新");
      closeModal();
    }
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteGithubConfig(id),
    onSuccess: () => {
      invalidate();
      message.success("配置已删除");
    }
  });

  const openCreateModal = () => setModalState({ open: true, config: null });
  const openEditModal = (config: GithubConfig) => setModalState({ open: true, config });
  const closeModal = () => setModalState({ open: false, config: null });

  const handleSubmit = async (values: GithubConfigPayload | GithubConfigUpdatePayload) => {
    if (modalState.config) {
      await updateMutation.mutateAsync({ id: modalState.config.id, payload: values as GithubConfigUpdatePayload });
    } else {
      await createMutation.mutateAsync(values as GithubConfigPayload);
    }
  };

  const columns: ColumnsType<GithubConfig> = [
    { title: "名称", dataIndex: "name", key: "name" },
    {
      title: "仓库",
      key: "repo",
      render: (record) => `${record.owner}/${record.repo}`
    },
    {
      title: "分支",
      dataIndex: "branch",
      key: "branch"
    },
    {
      title: "路径前缀",
      dataIndex: "path_prefix",
      key: "path_prefix",
      render: (value?: string | null) => value || "-"
    },
    {
      title: "文件名模板",
      dataIndex: "filename_template",
      key: "filename_template",
      ellipsis: true,
      render: (value: string) => (
        <Tooltip
          title={
            <div>
              <div>{value}</div>
              <div style={{ marginTop: 4 }}>
                示例：<Text code>{`微信群日报_{YYYY-MM-DD}.html`}</Text> → <Text>微信群日报_2025-11-07.html</Text>
              </div>
            </div>
          }
        >
          <span>{value}</span>
        </Tooltip>
      )
    },
    {
      title: "查看页面链接",
      key: "view_url_mode",
      ellipsis: true,
      render: (record) =>
        record.view_url_mode === "custom_template" ? (
          <Tooltip title={record.view_url_template || ""}>
            <Tag color="purple">自定义</Tag>
            <span>{record.view_url_template || "-"}</span>
          </Tooltip>
        ) : (
          <Tag>GitHub Pages</Tag>
        )
    },
    {
      title: "默认配置",
      dataIndex: "is_default",
      key: "is_default",
      render: (val: boolean) => (val ? <Tag color="blue">默认</Tag> : <Tag>备用</Tag>)
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
      fixed: "right",
      width: 160,
      render: (_, record) => (
        <Space size="small">
          <Button type="link" onClick={() => openEditModal(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确认删除该配置？"
            okText="删除"
            cancelText="取消"
            onConfirm={() => deleteMutation.mutate(record.id)}
          >
            <Button type="link" danger loading={deleteMutation.isPending}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      )
    }
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 16 }}>
        <Button type="primary" onClick={openCreateModal}>
          新增配置
        </Button>
      </div>
      <Table<GithubConfig>
        rowKey={(record) => record.id}
        dataSource={configs ?? []}
        columns={columns}
        loading={isLoading}
        pagination={false}
        locale={{ emptyText: "暂无配置" }}
        scroll={{ x: "max-content" }}
      />
      <GithubConfigFormModal
        open={modalState.open}
        initialValues={modalState.config ?? undefined}
        onCancel={closeModal}
        confirmLoading={createMutation.isPending || updateMutation.isPending}
        onSubmit={handleSubmit}
      />
    </div>
  );
}

export default GithubConfigsPage;
