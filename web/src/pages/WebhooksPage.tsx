import { useMemo, useState } from "react";
import { Button, Popconfirm, Space, Table, Tag, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import WebhookFormModal from "../components/WebhookFormModal";
import type { Webhook, WebhookCreatePayload, WebhookUpdatePayload } from "../services/webhooks";
import { createWebhook, deleteWebhook, fetchWebhooks, updateWebhook } from "../services/webhooks";
import { useResizableColumns } from "../hooks/useResizableColumns";
import { formatBeijingDateTime } from "../utils/datetime";
import { getErrorMessage } from "../services/apiClient";

const { Text } = Typography;

const CARD_MODE_LABELS: Record<Webhook["card_mode"], string> = {
  markdown: "Markdown 卡片",
  template: "模板模式（待支持）",
  custom_json: "JSON 卡片（待支持）"
};

const IMAGE_ENGINE_LABELS: Record<Webhook["image_render_engine"], string> = {
  satori: "Satori",
  svg: "SVG",
  typst: "Typst"
};

function WebhooksPage() {
  const queryClient = useQueryClient();
  const { data: webhooks, isLoading } = useQuery({ queryKey: ["webhooks"], queryFn: fetchWebhooks });
  const [modalOpen, setModalOpen] = useState(false);
  const [editingWebhook, setEditingWebhook] = useState<Webhook | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["webhooks"] });

  const createMutation = useMutation({
    mutationFn: (payload: WebhookCreatePayload) => createWebhook(payload),
    onSuccess: () => invalidate()
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: WebhookUpdatePayload }) => updateWebhook(id, payload),
    onSuccess: () => invalidate()
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteWebhook(id),
    onSuccess: () => invalidate()
  });

  const openCreateModal = () => {
    setEditingWebhook(null);
    setModalOpen(true);
  };

  const openEditModal = (webhook: Webhook) => {
    setEditingWebhook(webhook);
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setEditingWebhook(null);
  };

  const handleSubmit = async (payload: WebhookCreatePayload | WebhookUpdatePayload) => {
    try {
      if (editingWebhook) {
        await updateMutation.mutateAsync({ id: editingWebhook.id, payload: payload as WebhookUpdatePayload });
        message.success("Webhook 已更新");
      } else {
        await createMutation.mutateAsync(payload as WebhookCreatePayload);
        message.success("Webhook 已创建");
      }
      closeModal();
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  };

  const handleDelete = async (webhookId: number) => {
    try {
      await deleteMutation.mutateAsync(webhookId);
      message.success("Webhook 已删除");
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  };

  const baseColumns: (ColumnsType<Webhook>[number] & { key: string })[] = useMemo(
    () => [
      { title: "名称", dataIndex: "name", key: "name" },
      {
        title: "Headers",
        dataIndex: "headers",
        key: "headers",
        render: (headers?: Record<string, unknown> | null) => (headers ? <Text code>{JSON.stringify(headers)}</Text> : "-")
      },
      {
        title: "卡片模式",
        dataIndex: "card_mode",
        key: "card_mode",
        render: (value: Webhook["card_mode"]) => CARD_MODE_LABELS[value] ?? value
      },
      {
        title: "标题/主题色",
        key: "card_header",
        render: (_, record) =>
          record.card_mode !== "markdown" ? (
            <Text type="secondary">当前模式不支持</Text>
          ) : record.card_header_enabled ? (
            <Space direction="vertical" size={0}>
              <span>标题：{record.card_header_title ? record.card_header_title : "自定义"}</span>
              <span>副标题：{record.card_header_subtitle || "（空）"}</span>
              <span>主题色：{record.card_header_color || "blue"}</span>
            </Space>
          ) : (
            <Tag color="default">使用作业名称</Tag>
          )
      },
      {
        title: "图片上传",
        key: "image_upload",
        render: (_, record) => (
          <Space direction="vertical" size={0}>
            <span>引擎：{IMAGE_ENGINE_LABELS[record.image_render_engine] ?? record.image_render_engine}</span>
            <span>App ID：{record.feishu_app_id || "-"}</span>
            <span>Secret：{record.has_feishu_app_secret ? "已配置" : "未配置"}</span>
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
        fixed: "right",
        width: 160,
        render: (_, record) => (
          <Space size="small">
            <Button type="link" onClick={() => openEditModal(record)}>
              编辑
            </Button>
            <Popconfirm title="确认删除该 Webhook？" okText="删除" cancelText="取消" onConfirm={() => handleDelete(record.id)}>
              <Button type="link" danger>
                删除
              </Button>
            </Popconfirm>
          </Space>
        )
      }
    ],
    [handleDelete, openEditModal]
  );

  const { columns, components } = useResizableColumns<Webhook>(baseColumns, "webhooks_table_columns");

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Text type="secondary">Webhook URL 不会在列表中展示，更新时如需变更请重新填写。</Text>
        <Button type="primary" onClick={openCreateModal}>
          新增 Webhook
        </Button>
      </div>
      <Table<Webhook>
        columns={columns}
        components={components}
        loading={isLoading}
        dataSource={webhooks ?? []}
        rowKey={(record) => record.id}
        pagination={false}
        scroll={{ x: "max-content" }}
        locale={{ emptyText: "暂无 Webhook" }}
      />
      <WebhookFormModal
        open={modalOpen}
        initialValues={editingWebhook ?? undefined}
        confirmLoading={createMutation.isPending || updateMutation.isPending}
        onCancel={closeModal}
        onSubmit={handleSubmit}
      />
    </div>
  );
}

export default WebhooksPage;
