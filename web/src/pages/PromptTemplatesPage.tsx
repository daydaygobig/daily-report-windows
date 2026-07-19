import { useMemo, useState } from "react";
import { Button, Popconfirm, Space, Table, Tag, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import PromptTemplateModal from "../components/PromptTemplateModal";
import type { PromptTemplate, PromptTemplatePayload } from "../services/promptTemplates";
import {
  createPromptTemplate,
  deletePromptTemplate,
  fetchPromptTemplates,
  updatePromptTemplate
} from "../services/promptTemplates";
import { useResizableColumns } from "../hooks/useResizableColumns";
import { formatBeijingDateTime } from "../utils/datetime";

const { Paragraph, Text } = Typography;

function PromptTemplatesPage() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["prompt-templates"], queryFn: fetchPromptTemplates });
  const [modalState, setModalState] = useState<{ open: boolean; template: PromptTemplate | null }>({
    open: false,
    template: null
  });
  const [expandedRows, setExpandedRows] = useState<Record<number, boolean>>({});

  const closeModal = () => setModalState({ open: false, template: null });

  const commonMutationOptions = {
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["prompt-templates"] })
  };

  const createMutation = useMutation({ mutationFn: createPromptTemplate, ...commonMutationOptions });
  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: PromptTemplatePayload }) => updatePromptTemplate(id, payload),
    ...commonMutationOptions
  });
  const deleteMutation = useMutation({
    mutationFn: (id: number) => deletePromptTemplate(id),
    ...commonMutationOptions
  });

  const handleSubmit = async (payload: PromptTemplatePayload) => {
    try {
      if (modalState.template) {
        await updateMutation.mutateAsync({ id: modalState.template.id, payload });
        message.success("提示词已更新");
      } else {
        await createMutation.mutateAsync(payload);
        message.success("提示词已创建");
      }
      closeModal();
    } catch (error) {
      message.error((error as Error).message || "操作失败");
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteMutation.mutateAsync(id);
      message.success("提示词已删除");
    } catch (error) {
      message.error((error as Error).message || "删除失败");
    }
  };

  const baseColumns: (ColumnsType<PromptTemplate>[number] & { key: string })[] = useMemo(
    () => [
      { title: "名称", dataIndex: "name", key: "name" },
      {
        title: "内容预览",
        dataIndex: "content",
        key: "content",
        render: (value: string, record) => {
          const expanded = expandedRows[record.id] ?? false;
          const toggle = () =>
            setExpandedRows((prev) => ({
              ...prev,
              [record.id]: !expanded
            }));
          const paragraphStyle = expanded
            ? { marginBottom: 0 }
            : {
                marginBottom: 0,
                display: "-webkit-box",
                WebkitLineClamp: 2,
                WebkitBoxOrient: "vertical" as const,
                overflow: "hidden"
              };
          return (
            <div>
              <Paragraph className={expanded ? undefined : "text-clamp"} style={paragraphStyle}>
                {value}
              </Paragraph>
              {value && value.length > 0 ? (
                <Button type="link" size="small" onClick={toggle} style={{ padding: 0 }}>
                  {expanded ? "收起" : "展开"}
                </Button>
              ) : null}
            </div>
          );
        }
      },
      {
        title: "备注",
        dataIndex: "description",
        key: "description",
        render: (value: string | null | undefined) => value || "-"
      },
      {
        title: "更新时间",
        dataIndex: "updated_at",
        key: "updated_at",
        render: (value: string) => formatBeijingDateTime(value, "YYYY-MM-DD HH:mm")
      },
      {
        title: "操作",
        key: "actions",
        fixed: "right",
        width: 180,
        render: (_, record) => (
          <Space size="small">
            <Button type="link" onClick={() => setModalState({ open: true, template: record })}>
              编辑
            </Button>
            <Popconfirm
              title="确认删除该提示词？"
              okText="删除"
              cancelText="取消"
              onConfirm={() => handleDelete(record.id)}
            >
              <Button type="link" danger loading={deleteMutation.isPending && deleteMutation.variables === record.id}>
                删除
              </Button>
            </Popconfirm>
          </Space>
        )
      }
    ],
    [deleteMutation.isPending, deleteMutation.variables, expandedRows]
  );

  const { columns, components } = useResizableColumns<PromptTemplate>(baseColumns, "prompt_templates_table_columns");

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <div>
          <Text type="secondary">提示词模板可在任务配置中复用，删除模板不会影响已保存任务。</Text>
        </div>
        <Button type="primary" onClick={() => setModalState({ open: true, template: null })}>
          新建提示词
        </Button>
      </div>
      <Table
        className="prompt-templates-table"
        components={components}
        rowKey={(record) => record.id}
        loading={isLoading}
        dataSource={data ?? []}
        columns={columns}
        pagination={false}
        scroll={{ x: "max-content" }}
        locale={{
          emptyText: (
            <div>
              <Tag color="blue">暂无提示词</Tag>
              <div>点击右上角“新建提示词”即可创建模板</div>
            </div>
          )
        }}
      />
      <PromptTemplateModal
        open={modalState.open}
        initialValues={modalState.template}
        confirmLoading={createMutation.isPending || updateMutation.isPending}
        onSubmit={handleSubmit}
        onCancel={closeModal}
      />
    </>
  );
}

export default PromptTemplatesPage;
