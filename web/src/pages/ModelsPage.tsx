import { useCallback, useMemo, useState } from "react";
import { Button, Popconfirm, Select, Space, Table, Tag, Tooltip, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import ModelFormModal from "../components/ModelFormModal";
import type { Model, ModelCreatePayload, ModelUpdatePayload } from "../services/models";
import { createModel, deleteModel, fetchModels, updateModel } from "../services/models";
import { useResizableColumns } from "../hooks/useResizableColumns";
import { formatBeijingDateTime } from "../utils/datetime";

const { Text } = Typography;
const COLUMN_STORAGE_KEY = "models_table_column_widths";
const DEFAULT_COLUMN_WIDTHS: Record<string, number> = {
  name: 160,
  provider: 200,
  model_type: 110,
  base_url: 280,
  request_standard: 140,
  max_tokens: 120,
  temperature: 120,
  top_p: 120,
  extra: 320,
  updated_at: 180,
  actions: 160
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

function ModelsPage() {
  const queryClient = useQueryClient();
  const { data: models, isLoading } = useQuery({ queryKey: ["models"], queryFn: fetchModels });
  const [modalOpen, setModalOpen] = useState(false);
  const [editingModel, setEditingModel] = useState<Model | null>(null);
  const [modelTypeFilter, setModelTypeFilter] = useState<Model["model_type"] | undefined>();
  const [vendorFilter, setVendorFilter] = useState<string | undefined>();

  const vendorOptions = useMemo(
    () =>
      Array.from(new Set((models ?? []).map((model) => model.name)))
        .sort((left, right) => left.localeCompare(right, "zh-CN"))
        .map((value) => ({ label: value, value })),
    [models]
  );

  const filteredModels = useMemo(
    () =>
      (models ?? []).filter(
        (model) =>
          (!modelTypeFilter || model.model_type === modelTypeFilter) &&
          (!vendorFilter || model.name === vendorFilter)
      ),
    [models, modelTypeFilter, vendorFilter]
  );

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["models"] });

  const createMutation = useMutation({
    mutationFn: (payload: ModelCreatePayload) => createModel(payload),
    onSuccess: () => invalidate()
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: ModelUpdatePayload }) => updateModel(id, payload),
    onSuccess: (updatedModel) => {
      queryClient.setQueryData<Model[]>(["models"], (currentModels) =>
        currentModels?.map((model) => (model.id === updatedModel.id ? updatedModel : model))
      );
      return invalidate();
    }
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteModel(id),
    onSuccess: () => invalidate()
  });

  const openCreateModal = useCallback(() => {
    setEditingModel(null);
    setModalOpen(true);
  }, []);

  const openEditModal = useCallback((model: Model) => {
    setEditingModel(model);
    setModalOpen(true);
  }, []);

  const closeModal = useCallback(() => {
    setModalOpen(false);
    setEditingModel(null);
  }, []);

  const handleSubmit = async (payload: ModelCreatePayload | ModelUpdatePayload) => {
    try {
      if (editingModel) {
        await updateMutation.mutateAsync({ id: editingModel.id, payload: payload as ModelUpdatePayload });
        message.success("模型已更新");
      } else {
        await createMutation.mutateAsync(payload as ModelCreatePayload);
        message.success("模型已创建");
      }
      closeModal();
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  };

  const handleDelete = useCallback(
    async (modelId: number) => {
      try {
        await deleteMutation.mutateAsync(modelId);
        message.success("模型已删除");
      } catch (error) {
        message.error(getErrorMessage(error));
      }
    },
    [deleteMutation]
  );

  const baseColumns: (ColumnsType<Model>[number] & { key: string })[] = useMemo(
    () => [
      { title: "模型厂商", dataIndex: "name", key: "name", ellipsis: true },
      {
        title: "模型用途",
        dataIndex: "model_type",
        key: "model_type",
        render: (value: Model["model_type"]) => (
          <Tag color={value === "image" ? "purple" : "blue"}>{value === "image" ? "图片模型" : "文本模型"}</Tag>
        )
      },
      {
        title: "模型ID",
        dataIndex: "provider",
        key: "provider",
        render: (value: string) => (
          <div className="text-clamp">
            <Tag>{value}</Tag>
          </div>
        ),
        ellipsis: true
      },
      {
        title: "Base URL",
        dataIndex: "base_url",
        key: "base_url",
        render: (value?: string | null) => <div className="text-clamp">{value || "-"}</div>
      },
      {
        title: "请求标准",
        dataIndex: "request_standard",
        key: "request_standard",
        render: (value: string) => {
          const mapping: Record<string, string> = {
            openai: "OpenAI",
            gemini: "Gemini",
            anthropic: "Anthropic",
            openai_images: "OpenAI Images"
          };
          return <Tag>{mapping[value] ?? value}</Tag>;
        }
      },
      {
        title: "Max Tokens",
        dataIndex: "max_tokens",
        key: "max_tokens",
        render: (value?: number | null) => value ?? "-"
      },
      {
        title: "Temperature",
        dataIndex: "temperature",
        key: "temperature",
        render: (value?: number | null) => value ?? "-"
      },
      {
        title: "Top P",
        dataIndex: "top_p",
        key: "top_p",
        render: (value?: number | null) => value ?? "-"
      },
      {
        title: "额外配置",
        dataIndex: "extra",
        key: "extra",
        render: (extra?: Record<string, unknown> | null) => {
          if (!extra) return "-";
          const text = JSON.stringify(extra);
          return (
            <Tooltip title={<pre style={{ maxWidth: 480, margin: 0 }}>{text}</pre>}>
              <Text code className="text-clamp" style={{ display: "inline-block", maxWidth: "100%" }}>
                {text}
              </Text>
            </Tooltip>
          );
        }
      },
      {
        title: "更新时间",
        dataIndex: "updated_at",
        key: "updated_at",
        width: DEFAULT_COLUMN_WIDTHS.updated_at,
        render: (value: string) => formatBeijingDateTime(value)
      },
      {
        title: "操作",
        key: "actions",
        fixed: "right",
        width: DEFAULT_COLUMN_WIDTHS.actions,
        render: (_, record) => (
          <Space size="small">
            <Button type="link" onClick={() => openEditModal(record)}>
              编辑
            </Button>
            <Popconfirm title="确认删除该模型？" okText="删除" cancelText="取消" onConfirm={() => handleDelete(record.id)}>
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

  const { columns, components } = useResizableColumns<Model>(
    baseColumns,
    COLUMN_STORAGE_KEY,
    DEFAULT_COLUMN_WIDTHS
  );

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <Text type="secondary">密钥不会在列表中展示，更新时留空即可保留原值。</Text>
          <Space wrap>
            <Select<Model["model_type"]>
              allowClear
              placeholder="模型用途"
              style={{ width: 140 }}
              value={modelTypeFilter}
              onChange={setModelTypeFilter}
              options={[
                { label: "文本模型", value: "text" },
                { label: "图片模型", value: "image" }
              ]}
            />
            <Select<string>
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="模型厂商"
              style={{ width: 180 }}
              value={vendorFilter}
              onChange={setVendorFilter}
              options={vendorOptions}
            />
          </Space>
        </div>
        <Button type="primary" onClick={openCreateModal}>
          新增模型
        </Button>
      </div>
      <Table<Model>
        columns={columns}
        components={components}
        loading={isLoading}
        dataSource={filteredModels}
        rowKey={(record) => record.id}
        pagination={false}
        tableLayout="fixed"
        style={{ wordBreak: "break-word" }}
        scroll={{ x: "max-content" }}
        locale={{ emptyText: modelTypeFilter || vendorFilter ? "没有符合筛选条件的模型" : "暂无模型" }}
      />
      <ModelFormModal
        open={modalOpen}
        initialValues={editingModel ?? undefined}
        confirmLoading={createMutation.isPending || updateMutation.isPending}
        onCancel={closeModal}
        onSubmit={handleSubmit}
      />
    </div>
  );
}

export default ModelsPage;
