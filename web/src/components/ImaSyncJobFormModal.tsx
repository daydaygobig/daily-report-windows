import { useEffect, useMemo, useState } from "react";
import { Button, Form, Input, Modal, Select, Space, Switch, Tooltip, message } from "antd";
import { QuestionCircleOutlined, ReloadOutlined } from "@ant-design/icons";
import {
  fetchImaKnowledgeBases,
  fetchImaKnowledgeFolders,
  fetchImaNoteFolders,
  type ImaOption,
  type ImaSyncJob,
  type ImaSyncJobPayload,
  type ImaTargetType
} from "../services/ima";

type ImaSyncJobFormValues = {
  name: string;
  is_enabled: boolean;
  ima_account_id?: number;
  target_type: ImaTargetType;
  note_folder_id?: string;
  knowledge_base_id?: string;
  knowledge_folder_id?: string;
  local_sync_path: string;
  recursive_enabled: boolean;
  allowed_extensions: ("md" | "txt")[];
  schedule_frequency: "daily" | "weekly";
  schedule_weekday?: number;
  schedule_time: string;
  webhook_id?: number;
};

type WebhookOption = {
  label: string;
  value: number;
};

type AccountOption = {
  label: string;
  value: number;
};

type Props = {
  open: boolean;
  initialValues?: ImaSyncJob | null;
  confirmLoading?: boolean;
  webhookOptions: WebhookOption[];
  accountOptions: AccountOption[];
  onCancel: () => void;
  onSubmit: (payload: ImaSyncJobPayload) => void | Promise<void>;
};

const ROOT_KNOWLEDGE_FOLDER_OPTION: ImaOption = { label: "根目录", value: "root" };

const weekdayOptions = [
  { label: "周一", value: 0 },
  { label: "周二", value: 1 },
  { label: "周三", value: 2 },
  { label: "周四", value: 3 },
  { label: "周五", value: 4 },
  { label: "周六", value: 5 },
  { label: "周日", value: 6 }
];

const defaultValues: ImaSyncJobFormValues = {
  name: "",
  is_enabled: true,
  ima_account_id: undefined,
  target_type: "knowledge_base",
  note_folder_id: undefined,
  knowledge_base_id: undefined,
  knowledge_folder_id: "root",
  local_sync_path: "",
  recursive_enabled: true,
  allowed_extensions: ["md", "txt"],
  schedule_frequency: "daily",
  schedule_weekday: 0,
  schedule_time: "08:00",
  webhook_id: undefined
};

const buildDisplayKnowledgeFolderOption = (
  folderId?: string | null,
  folderName?: string | null
): ImaOption | null => {
  const normalizedId = (folderId ?? "").trim();
  if (!normalizedId || normalizedId === ROOT_KNOWLEDGE_FOLDER_OPTION.value) {
    return null;
  }
  const normalizedLabel = (folderName ?? "").trim();
  return {
    value: normalizedId,
    label: normalizedLabel || normalizedId
  };
};

const mergeKnowledgeFolderOptions = (list: ImaOption[], fallbackOption?: ImaOption | null): ImaOption[] => {
  const order: string[] = [];
  const optionMap = new Map<string, ImaOption>();
  const pushOption = (option?: ImaOption | null) => {
    if (!option?.value) {
      return;
    }
    if (!optionMap.has(option.value)) {
      order.push(option.value);
    }
    optionMap.set(option.value, option);
  };
  pushOption(ROOT_KNOWLEDGE_FOLDER_OPTION);
  pushOption(fallbackOption);
  list.forEach((item) => pushOption(item));
  return order.map((value) => optionMap.get(value)!);
};

const toFormValues = (job?: ImaSyncJob | null): ImaSyncJobFormValues => ({
  name: job?.name ?? "",
  is_enabled: job?.is_enabled ?? true,
  ima_account_id: job?.ima_account_id ?? undefined,
  target_type: job?.target_type ?? "knowledge_base",
  note_folder_id: job?.note_folder_id ?? undefined,
  knowledge_base_id: job?.knowledge_base_id ?? undefined,
  knowledge_folder_id: job?.knowledge_folder_id ?? "root",
  local_sync_path: job?.local_sync_path ?? "",
  recursive_enabled: job?.recursive_enabled ?? true,
  allowed_extensions: job?.allowed_extensions?.length ? job.allowed_extensions : ["md", "txt"],
  schedule_frequency: job?.schedule_frequency ?? "daily",
  schedule_weekday: job?.schedule_weekday ?? 0,
  schedule_time: job?.schedule_time ?? "08:00",
  webhook_id: job?.webhook_id ?? undefined
});

function ImaSyncJobFormModal({
  open,
  initialValues,
  confirmLoading,
  webhookOptions,
  accountOptions,
  onCancel,
  onSubmit
}: Props) {
  const [form] = Form.useForm<ImaSyncJobFormValues>();
  const targetType = Form.useWatch("target_type", form);
  const accountId = Form.useWatch("ima_account_id", form);
  const knowledgeBaseId = Form.useWatch("knowledge_base_id", form);
  const scheduleFrequency = Form.useWatch("schedule_frequency", form);
  const [noteFolders, setNoteFolders] = useState<ImaOption[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<ImaOption[]>([]);
  const [knowledgeFolders, setKnowledgeFolders] = useState<ImaOption[]>([ROOT_KNOWLEDGE_FOLDER_OPTION]);
  const [loadingState, setLoadingState] = useState({
    noteFolders: false,
    knowledgeBases: false,
    knowledgeFolders: false
  });

  const title = initialValues ? "编辑ima同步作业" : "新增ima同步作业";

  const loadNoteFolders = async (nextAccountId?: number) => {
    if (!nextAccountId) {
      setNoteFolders([]);
      return;
    }
    try {
      setLoadingState((prev) => ({ ...prev, noteFolders: true }));
      setNoteFolders(await fetchImaNoteFolders(nextAccountId));
    } catch (error) {
      const err = error as Error;
      message.error(err.message || "加载笔记本失败");
    } finally {
      setLoadingState((prev) => ({ ...prev, noteFolders: false }));
    }
  };

  const loadKnowledgeBases = async (nextAccountId?: number) => {
    if (!nextAccountId) {
      setKnowledgeBases([]);
      return;
    }
    try {
      setLoadingState((prev) => ({ ...prev, knowledgeBases: true }));
      setKnowledgeBases(await fetchImaKnowledgeBases(nextAccountId));
    } catch (error) {
      const err = error as Error;
      message.error(err.message || "加载知识库失败");
    } finally {
      setLoadingState((prev) => ({ ...prev, knowledgeBases: false }));
    }
  };

  const loadKnowledgeFolders = async (
    nextKnowledgeBaseId?: string,
    nextAccountId?: number,
    forceRefresh: boolean = false
  ) => {
    if (!nextAccountId || !nextKnowledgeBaseId) {
      setKnowledgeFolders([ROOT_KNOWLEDGE_FOLDER_OPTION]);
      return;
    }
    try {
      setLoadingState((prev) => ({ ...prev, knowledgeFolders: true }));
      const list = await fetchImaKnowledgeFolders(nextKnowledgeBaseId, nextAccountId, forceRefresh);
      setKnowledgeFolders((prev) => {
        const selectedValue = form.getFieldValue("knowledge_folder_id");
        const selectedFallback =
          selectedValue && selectedValue !== ROOT_KNOWLEDGE_FOLDER_OPTION.value
            ? prev.find((item) => item.value === selectedValue) ??
              buildDisplayKnowledgeFolderOption(initialValues?.knowledge_folder_id, initialValues?.knowledge_folder_name) ??
              { label: selectedValue, value: selectedValue }
            : null;
        return mergeKnowledgeFolderOptions(list, selectedFallback);
      });
    } catch (error) {
      const err = error as Error;
      message.error(err.message || "加载知识库文件夹失败");
      setKnowledgeFolders((prev) =>
        mergeKnowledgeFolderOptions([], prev.find((item) => item.value === form.getFieldValue("knowledge_folder_id")))
      );
    } finally {
      setLoadingState((prev) => ({ ...prev, knowledgeFolders: false }));
    }
  };

  useEffect(() => {
    if (!open) {
      return;
    }
    form.resetFields();
    form.setFieldsValue(toFormValues(initialValues));
    setKnowledgeFolders(
      mergeKnowledgeFolderOptions(
        [],
        buildDisplayKnowledgeFolderOption(initialValues?.knowledge_folder_id, initialValues?.knowledge_folder_name)
      )
    );
    const initialAccountId = initialValues?.ima_account_id;
    if (initialAccountId) {
      void loadNoteFolders(initialAccountId);
      void loadKnowledgeBases(initialAccountId);
      if (initialValues?.knowledge_base_id) {
        void loadKnowledgeFolders(initialValues.knowledge_base_id, initialAccountId);
      } else {
        setKnowledgeFolders([ROOT_KNOWLEDGE_FOLDER_OPTION]);
      }
    } else {
      setNoteFolders([]);
      setKnowledgeBases([]);
      setKnowledgeFolders([ROOT_KNOWLEDGE_FOLDER_OPTION]);
    }
  }, [form, initialValues, open]);

  useEffect(() => {
    if (!open || !initialValues || initialValues.target_type !== "knowledge_base") {
      return;
    }
    const storedFolderId = (initialValues.knowledge_folder_id ?? "").trim();
    if (!storedFolderId || storedFolderId === ROOT_KNOWLEDGE_FOLDER_OPTION.value) {
      return;
    }
    const currentKnowledgeBaseId = form.getFieldValue("knowledge_base_id");
    if (currentKnowledgeBaseId !== initialValues.knowledge_base_id) {
      return;
    }
    const currentFolderId = form.getFieldValue("knowledge_folder_id");
    if (currentFolderId && currentFolderId !== ROOT_KNOWLEDGE_FOLDER_OPTION.value) {
      return;
    }
    setKnowledgeFolders((prev) =>
      mergeKnowledgeFolderOptions(
        prev,
        buildDisplayKnowledgeFolderOption(initialValues.knowledge_folder_id, initialValues.knowledge_folder_name)
      )
    );
    form.setFieldValue("knowledge_folder_id", storedFolderId);
  }, [form, initialValues, knowledgeFolders, open]);

  const knowledgeFolderOptions = useMemo(
    () => (knowledgeFolders.length ? knowledgeFolders : [ROOT_KNOWLEDGE_FOLDER_OPTION]),
    [knowledgeFolders]
  );

  const handleOk = async () => {
    const values = await form.validateFields();
    const noteFolder = noteFolders.find((item) => item.value === values.note_folder_id);
    const knowledgeBase = knowledgeBases.find((item) => item.value === values.knowledge_base_id);
    const knowledgeFolder = knowledgeFolderOptions.find((item) => item.value === values.knowledge_folder_id);
    const payload: ImaSyncJobPayload = {
      name: values.name.trim(),
      is_enabled: values.is_enabled,
      ima_account_id: values.ima_account_id!,
      target_type: values.target_type,
      note_folder_id: values.target_type === "note" ? values.note_folder_id ?? null : null,
      note_folder_name: values.target_type === "note" ? noteFolder?.label ?? "" : "",
      knowledge_base_id: values.target_type === "knowledge_base" ? values.knowledge_base_id ?? null : null,
      knowledge_base_name: values.target_type === "knowledge_base" ? knowledgeBase?.label ?? "" : "",
      knowledge_folder_id:
        values.target_type === "knowledge_base"
          ? values.knowledge_folder_id === "root"
            ? null
            : values.knowledge_folder_id ?? null
          : null,
      knowledge_folder_name:
        values.target_type === "knowledge_base" ? knowledgeFolder?.label ?? "根目录" : "",
      local_sync_path: values.local_sync_path.trim(),
      recursive_enabled: values.recursive_enabled,
      allowed_extensions: values.allowed_extensions?.length ? values.allowed_extensions : ["md"],
      schedule_frequency: values.schedule_frequency,
      schedule_weekday: values.schedule_frequency === "weekly" ? values.schedule_weekday ?? 0 : 0,
      schedule_time: values.schedule_time.trim() || "08:00",
      webhook_id: values.webhook_id ?? null
    };
    await onSubmit(payload);
  };

  const recursiveLabel = (
    <Space size={6}>
      <span>是否递归扫描子目录</span>
      <Tooltip
        title={
          <div style={{ maxWidth: 360 }}>
            开启后，会继续扫描当前同步根目录下面的子文件夹。
            <br />
            <br />
            例如你配置的是：
            <br />
            <code>C:\日报输出\新茧知识库</code>
            <br />
            如果这个目录下面还有：
            <br />
            <code>3月知识库</code>、<code>周报</code>
            <br />
            那么开启后会把这些子目录里的文件也一起同步；
            <br />
            关闭后只扫描最外层目录。
            <br />
            <br />
            不管开关是否开启，都只会扫描这条 ima 同步作业指定的根目录，不会跑到别的目录。
          </div>
        }
      >
        <QuestionCircleOutlined style={{ color: "#8c8c8c" }} />
      </Tooltip>
    </Space>
  );

  return (
    <Modal
      open={open}
      title={title}
      destroyOnHidden
      width={760}
      confirmLoading={confirmLoading}
      onCancel={() => {
        form.resetFields();
        onCancel();
      }}
      onOk={() => void handleOk()}
    >
      <Form form={form} layout="vertical" initialValues={defaultValues}>
        <Form.Item label="作业名称" name="name" rules={[{ required: true, message: "请输入作业名称" }]}>
          <Input placeholder="例如：新茧知识库自动同步" />
        </Form.Item>

        <Form.Item label="启用状态" name="is_enabled" valuePropName="checked">
          <Switch />
        </Form.Item>

        <Form.Item label="ima账号" name="ima_account_id" rules={[{ required: true, message: "请选择 ima 账号" }]}>
          <Select
            allowClear
            showSearch
            options={accountOptions}
            optionFilterProp="label"
            placeholder="请先选择要同步到哪个 ima 账号"
            onChange={(value) => {
              form.setFieldsValue({
                note_folder_id: undefined,
                knowledge_base_id: undefined,
                knowledge_folder_id: "root"
              });
              void loadNoteFolders(value);
              void loadKnowledgeBases(value);
              setKnowledgeFolders([{ label: "根目录", value: "root" }]);
            }}
          />
        </Form.Item>

        <Form.Item label="同步目标" name="target_type" rules={[{ required: true, message: "请选择同步目标" }]}>
          <Select
            options={[
              { label: "ima 笔记", value: "note" },
              { label: "ima 知识库", value: "knowledge_base" }
            ]}
          />
        </Form.Item>

        {targetType === "note" ? (
          <Form.Item label="目标笔记本" name="note_folder_id" rules={[{ required: true, message: "请选择目标笔记本" }]}>
            <Select
              allowClear
              showSearch
              options={noteFolders}
              optionFilterProp="label"
              loading={loadingState.noteFolders}
              disabled={!accountId}
              dropdownRender={(menu) => (
                <>
                  {menu}
                  <div style={{ padding: 8 }}>
                    <Button
                      type="link"
                      block
                      icon={<ReloadOutlined />}
                      disabled={!accountId}
                      onClick={() => void loadNoteFolders(accountId)}
                    >
                      刷新笔记本
                    </Button>
                  </div>
                </>
              )}
            />
          </Form.Item>
        ) : (
          <>
            <Form.Item
              label="目标知识库"
              name="knowledge_base_id"
              rules={[{ required: true, message: "请选择目标知识库" }]}
            >
              <Select
                allowClear
                showSearch
                options={knowledgeBases}
                optionFilterProp="label"
                loading={loadingState.knowledgeBases}
                disabled={!accountId}
                onChange={(value) => {
                  form.setFieldValue("knowledge_folder_id", "root");
                  void loadKnowledgeFolders(value, accountId);
                }}
                dropdownRender={(menu) => (
                  <>
                    {menu}
                    <div style={{ padding: 8 }}>
                      <Button
                        type="link"
                        block
                        icon={<ReloadOutlined />}
                        disabled={!accountId}
                        onClick={() => void loadKnowledgeBases(accountId)}
                      >
                        刷新知识库
                      </Button>
                    </div>
                  </>
                )}
              />
            </Form.Item>
            <Form.Item label="目标文件夹" name="knowledge_folder_id" preserve={false}>
              <Select
                allowClear
                showSearch
                options={knowledgeFolderOptions}
                optionFilterProp="label"
                disabled={!accountId || !knowledgeBaseId}
                loading={loadingState.knowledgeFolders}
                dropdownRender={(menu) => (
                  <>
                    {menu}
                    <div style={{ padding: 8 }}>
                      <Button
                        type="link"
                        block
                        icon={<ReloadOutlined />}
                        disabled={!accountId || !knowledgeBaseId}
                        onClick={() => void loadKnowledgeFolders(knowledgeBaseId, accountId, true)}
                      >
                        刷新文件夹
                      </Button>
                    </div>
                  </>
                )}
              />
            </Form.Item>
          </>
        )}

        <Form.Item label="本地同步路径" name="local_sync_path" rules={[{ required: true, message: "请填写本地同步路径" }]}>
          <Input placeholder="例如：model_outputs/新茧知识库 或 C:\\日报输出\\新茧知识库" />
        </Form.Item>

        <Form.Item label={recursiveLabel} name="recursive_enabled" valuePropName="checked">
          <Switch />
        </Form.Item>

        <Form.Item label="允许同步的文件格式" name="allowed_extensions" rules={[{ required: true, message: "请选择文件格式" }]}>
          <Select
            mode="multiple"
            options={[
              { label: "Markdown (.md)", value: "md" },
              { label: "纯文本 (.txt)", value: "txt" }
            ]}
          />
        </Form.Item>

        <Form.Item label="同步频率" name="schedule_frequency">
          <Select
            options={[
              { label: "每天", value: "daily" },
              { label: "每周", value: "weekly" }
            ]}
          />
        </Form.Item>

        {scheduleFrequency === "weekly" ? (
          <Form.Item label="每周执行日" name="schedule_weekday" preserve={false}>
            <Select options={weekdayOptions} />
          </Form.Item>
        ) : null}

        <Form.Item
          label="同步时间"
          name="schedule_time"
          rules={[
            { required: true, message: "请输入同步时间" },
            { pattern: /^\d{2}:\d{2}$/, message: "时间格式需为 HH:mm" }
          ]}
        >
          <Input placeholder="08:00" />
        </Form.Item>

        <Form.Item label="失败告警 Webhook" name="webhook_id" extra="仅自动同步作业失败时推送到对应飞书 Webhook。">
          <Select allowClear placeholder="可选，选择一个飞书 Webhook" options={webhookOptions} />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default ImaSyncJobFormModal;
