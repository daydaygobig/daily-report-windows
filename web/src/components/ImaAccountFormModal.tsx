import { useDeferredValue, useMemo } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Button, Form, Input, Modal, Select, Space, Switch, message } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import {
  fetchImaKnowledgeBasesPreview,
  fetchImaKnowledgeFoldersPreview,
  fetchImaNoteFoldersPreview,
  testImaSettingsPreview,
  type ImaAccount,
  type ImaAccountPayload,
  type ImaCredentialPreview,
  type ImaOption,
  type ImaTargetType
} from "../services/ima";

type ImaAccountFormValues = {
  name: string;
  client_id: string;
  api_key: string;
  is_enabled: boolean;
  is_default: boolean;
  remark?: string;
  default_target_type: ImaTargetType;
  default_note_folder_id?: string;
  default_knowledge_base_id?: string;
  default_knowledge_folder_id?: string;
};

type Props = {
  open: boolean;
  initialValues?: ImaAccount | null;
  confirmLoading?: boolean;
  onCancel: () => void;
  onSubmit: (payload: ImaAccountPayload) => void | Promise<void>;
};

const defaultValues: ImaAccountFormValues = {
  name: "",
  client_id: "",
  api_key: "",
  is_enabled: true,
  is_default: false,
  remark: "",
  default_target_type: "knowledge_base",
  default_note_folder_id: undefined,
  default_knowledge_base_id: undefined,
  default_knowledge_folder_id: "root"
};

const toFormValues = (account?: ImaAccount | null): ImaAccountFormValues => ({
  name: account?.name ?? "",
  client_id: account?.client_id ?? "",
  api_key: account?.api_key ?? "",
  is_enabled: account?.is_enabled ?? true,
  is_default: account?.is_default ?? false,
  remark: account?.remark ?? "",
  default_target_type: account?.default_target_type ?? "knowledge_base",
  default_note_folder_id: account?.default_note_folder_id ?? undefined,
  default_knowledge_base_id: account?.default_knowledge_base_id ?? undefined,
  default_knowledge_folder_id: account?.default_knowledge_folder_id ?? "root"
});

function ImaAccountFormModal({ open, initialValues, confirmLoading, onCancel, onSubmit }: Props) {
  const [form] = Form.useForm<ImaAccountFormValues>();
  const targetType = Form.useWatch("default_target_type", form);
  const rawClientId = Form.useWatch("client_id", form);
  const rawApiKey = Form.useWatch("api_key", form);
  const knowledgeBaseId = Form.useWatch("default_knowledge_base_id", form);
  const clientId = useDeferredValue((rawClientId ?? "").trim());
  const apiKey = useDeferredValue((rawApiKey ?? "").trim());
  const previewReady = Boolean(clientId && apiKey);
  const previewPayload = useMemo<ImaCredentialPreview>(
    () => ({
      client_id: clientId,
      api_key: apiKey
    }),
    [apiKey, clientId]
  );

  const noteFoldersQuery = useQuery({
    queryKey: ["ima-account-note-folders-preview", clientId, apiKey],
    queryFn: () => fetchImaNoteFoldersPreview(previewPayload),
    enabled: open && targetType === "note" && previewReady,
    retry: false,
    staleTime: 30_000
  });
  const knowledgeBasesQuery = useQuery({
    queryKey: ["ima-account-knowledge-bases-preview", clientId, apiKey],
    queryFn: () => fetchImaKnowledgeBasesPreview(previewPayload),
    enabled: open && targetType === "knowledge_base" && previewReady,
    retry: false,
    staleTime: 30_000
  });
  const knowledgeFoldersQuery = useQuery({
    queryKey: ["ima-account-knowledge-folders-preview", clientId, apiKey, knowledgeBaseId],
    queryFn: () =>
      fetchImaKnowledgeFoldersPreview({
        ...previewPayload,
        knowledge_base_id: knowledgeBaseId ?? ""
      }),
    enabled: open && targetType === "knowledge_base" && previewReady && Boolean(knowledgeBaseId),
    retry: false,
    staleTime: 30_000
  });

  const testMutation = useMutation({
    mutationFn: (payload: ImaCredentialPreview) => testImaSettingsPreview(payload),
    onSuccess: (result) => {
      message.success(result.message);
    },
    onError: (error) => {
      const err = error as Error;
      message.error(err.message || "测试连接失败");
    }
  });

  const knowledgeFolderOptions = useMemo<ImaOption[]>(
    () =>
      knowledgeBaseId && knowledgeFoldersQuery.data?.length
        ? [{ label: "根目录", value: "root" }, ...knowledgeFoldersQuery.data.filter((item) => item.value !== "root")]
        : [{ label: "根目录", value: "root" }],
    [knowledgeBaseId, knowledgeFoldersQuery.data]
  );

  const refreshOptions = async () => {
    if (!previewReady) {
      message.warning("请先填写 Client ID 和 API Key");
      return;
    }
    if (targetType === "note") {
      await noteFoldersQuery.refetch();
      return;
    }
    await knowledgeBasesQuery.refetch();
    if (form.getFieldValue("default_knowledge_base_id")) {
      await knowledgeFoldersQuery.refetch();
    }
  };

  const handleOk = async () => {
    const values = await form.validateFields();
    const selectedNoteFolder = noteFoldersQuery.data?.find((item) => item.value === values.default_note_folder_id);
    const selectedKnowledgeBase = knowledgeBasesQuery.data?.find(
      (item) => item.value === values.default_knowledge_base_id
    );
    const selectedKnowledgeFolder = knowledgeFolderOptions.find((item) => item.value === values.default_knowledge_folder_id);
    const payload: ImaAccountPayload = {
      name: values.name.trim(),
      client_id: values.client_id.trim(),
      api_key: values.api_key.trim(),
      is_enabled: values.is_enabled,
      is_default: values.is_default,
      remark: values.remark?.trim() || null,
      default_target_type: values.default_target_type,
      default_note_folder_id: values.default_target_type === "note" ? values.default_note_folder_id ?? null : null,
      default_note_folder_name: values.default_target_type === "note" ? selectedNoteFolder?.label ?? "" : "",
      default_knowledge_base_id:
        values.default_target_type === "knowledge_base" ? values.default_knowledge_base_id ?? null : null,
      default_knowledge_base_name:
        values.default_target_type === "knowledge_base" ? selectedKnowledgeBase?.label ?? "" : "",
      default_knowledge_folder_id:
        values.default_target_type === "knowledge_base"
          ? values.default_knowledge_folder_id === "root"
            ? null
            : values.default_knowledge_folder_id ?? null
          : null,
      default_knowledge_folder_name:
        values.default_target_type === "knowledge_base" ? selectedKnowledgeFolder?.label ?? "根目录" : ""
    };
    await onSubmit(payload);
  };

  return (
    <Modal
      open={open}
      title={initialValues ? "编辑ima账号" : "新增ima账号"}
      destroyOnHidden
      width={760}
      confirmLoading={confirmLoading}
      onCancel={() => {
        form.resetFields();
        onCancel();
      }}
      onOk={() => void handleOk()}
    >
      <Form form={form} layout="vertical" initialValues={toFormValues(initialValues)} preserve={false}>
        <Form.Item label="账号名称" name="name" rules={[{ required: true, message: "请输入账号名称" }]}>
          <Input placeholder="例如：主号知识库 / 微信读书同步账号" />
        </Form.Item>

        <Form.Item label="Client ID" name="client_id" rules={[{ required: true, message: "请输入 Client ID" }]}>
          <Input placeholder="请输入 ima Client ID" />
        </Form.Item>

        <Form.Item label="API Key" name="api_key" rules={[{ required: true, message: "请输入 API Key" }]}>
          <Input.Password placeholder="请输入 ima API Key" />
        </Form.Item>

        <Form.Item label="备注" name="remark" extra="可记录 API Key 有效期、账号用途等信息，列表里会展示。">
          <Input.TextArea placeholder="例如：2026-06-30 到期 / 新茧项目账号" autoSize={{ minRows: 2, maxRows: 4 }} />
        </Form.Item>

        <Form.Item label="启用状态" name="is_enabled" valuePropName="checked">
          <Switch />
        </Form.Item>

        <Form.Item label="设为默认账号" name="is_default" valuePropName="checked">
          <Switch />
        </Form.Item>

        <Form.Item label="默认同步目标" name="default_target_type">
          <Select
            options={[
              { label: "ima 笔记", value: "note" },
              { label: "ima 知识库", value: "knowledge_base" }
            ]}
          />
        </Form.Item>

        {targetType === "note" ? (
          <Form.Item
            label="默认笔记本"
            name="default_note_folder_id"
            rules={[{ required: true, message: "请选择默认笔记本" }]}
          >
            <Select
              allowClear
              showSearch
              placeholder={previewReady ? "请选择笔记本" : "请先填写 Client ID 和 API Key"}
              disabled={!previewReady}
              loading={noteFoldersQuery.isLoading}
              options={noteFoldersQuery.data ?? []}
              optionFilterProp="label"
            />
          </Form.Item>
        ) : (
          <>
            <Form.Item
              label="默认知识库"
              name="default_knowledge_base_id"
              rules={[{ required: true, message: "请选择默认知识库" }]}
            >
              <Select
                allowClear
                showSearch
                placeholder={previewReady ? "请选择知识库" : "请先填写 Client ID 和 API Key"}
                disabled={!previewReady}
                loading={knowledgeBasesQuery.isLoading}
                options={knowledgeBasesQuery.data ?? []}
                optionFilterProp="label"
                onChange={(value) => {
                  form.setFieldValue("default_knowledge_folder_id", "root");
                  if (value && previewReady) {
                    void knowledgeFoldersQuery.refetch();
                  }
                }}
              />
            </Form.Item>

            <Form.Item label="默认文件夹" name="default_knowledge_folder_id">
              <Select
                allowClear
                showSearch
                placeholder={previewReady ? "请选择知识库文件夹" : "请先填写 Client ID 和 API Key"}
                disabled={!previewReady || !knowledgeBaseId}
                loading={knowledgeFoldersQuery.isLoading}
                options={knowledgeFolderOptions}
                optionFilterProp="label"
              />
            </Form.Item>
          </>
        )}

        <Form.Item style={{ marginBottom: 0 }}>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => void refreshOptions()}>
              刷新选项
            </Button>
            <Button
              loading={testMutation.isPending}
              onClick={() =>
                testMutation.mutate({
                  client_id: (form.getFieldValue("client_id") ?? "").trim(),
                  api_key: (form.getFieldValue("api_key") ?? "").trim()
                })
              }
            >
              测试连接
            </Button>
          </Space>
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default ImaAccountFormModal;
