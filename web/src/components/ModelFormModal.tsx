import { useEffect, useMemo, useState } from "react";
import { Alert, AutoComplete, Button, Form, Image, Input, InputNumber, Modal, Select, Space, Switch, message } from "antd";
import type { Model, ModelCreatePayload, ModelUpdatePayload } from "../services/models";
import { fetchRemoteModels, testModelConnection } from "../services/models";

type ThinkingLevel = "none" | "low" | "medium" | "high" | "xhigh";
type MaxTokensParam = "max_tokens" | "max_completion_tokens" | "none";

type ModelFormValues = {
  name: string;
  provider: string;
  base_url?: string;
  api_key?: string;
  max_tokens?: number | null;
  temperature?: number | null;
  top_p?: number | null;
  max_tokens_param?: MaxTokensParam;
  thinking_level?: ThinkingLevel;
  force_image_base64?: boolean;
  extra?: string;
  request_standard: "openai" | "gemini" | "anthropic" | "openai_images";
  model_type: "text" | "image";
};

type ModelFormModalProps = {
  open: boolean;
  initialValues?: Model | null;
  confirmLoading?: boolean;
  onCancel: () => void;
  onSubmit: (payload: ModelCreatePayload | ModelUpdatePayload) => void | Promise<void>;
};

const DEFAULT_EXTRA_OBJECT: Record<string, unknown> = {};
const DEFAULT_EXTRA_JSON = JSON.stringify(DEFAULT_EXTRA_OBJECT);
const OPENAI_EXTRA_EXAMPLE = JSON.stringify({ payload: { temperature: 0.3 }, headers: { Authorization: "Bearer xxx" } });
const GEMINI_QUERY_EXAMPLE = JSON.stringify({ query_params: { key: "<API_KEY>" } });
const GEMINI_AUTH_HEADER_EXAMPLE = JSON.stringify({ auth_header: "Authorization" });

const defaultValues: ModelFormValues = {
  name: "",
  provider: "",
  base_url: "",
  api_key: "",
  max_tokens: undefined,
  temperature: undefined,
  top_p: undefined,
  max_tokens_param: "max_tokens",
  thinking_level: "none",
  force_image_base64: false,
  extra: JSON.stringify(DEFAULT_EXTRA_OBJECT, null, 2),
  request_standard: "openai",
  model_type: "text"
};

const cloneObject = <T,>(value: T): T => JSON.parse(JSON.stringify(value));

const ensureJsonObject = (value?: Record<string, unknown>): Record<string, unknown> => {
  if (!value || Object.keys(value).length === 0) {
    return cloneObject(DEFAULT_EXTRA_OBJECT);
  }
  return cloneObject(value);
};

const extractThinkingLevel = (extraObj?: Record<string, unknown>): ThinkingLevel => {
  const savedThinkingLevel = extraObj?.thinking_level;
  if (
    savedThinkingLevel === "low" ||
    savedThinkingLevel === "medium" ||
    savedThinkingLevel === "high" ||
    savedThinkingLevel === "xhigh"
  ) {
    return savedThinkingLevel;
  }
  const payload =
    extraObj?.payload && typeof extraObj.payload === "object" && !Array.isArray(extraObj.payload)
      ? (extraObj.payload as Record<string, unknown>)
      : undefined;
  const thinking =
    payload?.thinking && typeof payload.thinking === "object" && !Array.isArray(payload.thinking)
      ? (payload.thinking as Record<string, unknown>)
      : undefined;
  const type = thinking?.type;
  return type === "low" || type === "medium" || type === "high" || type === "xhigh" ? type : "none";
};

const extractMaxTokensParam = (extraObj?: Record<string, unknown>): MaxTokensParam => {
  const value = extraObj?.max_tokens_param;
  if (value === "max_completion_tokens" || value === "none") {
    return value;
  }
  return "max_tokens";
};

const extractForceImageBase64 = (extraObj?: Record<string, unknown>): boolean => {
  const payload =
    extraObj?.payload && typeof extraObj.payload === "object" && !Array.isArray(extraObj.payload)
      ? (extraObj.payload as Record<string, unknown>)
      : undefined;
  return payload?.response_format === "b64_json";
};

const removeImageResponseFormat = (extraObj?: Record<string, unknown>) => {
  if (!extraObj?.payload || typeof extraObj.payload !== "object" || Array.isArray(extraObj.payload)) {
    return;
  }
  const payload = { ...(extraObj.payload as Record<string, unknown>) };
  delete payload.response_format;
  if (Object.keys(payload).length > 0) {
    extraObj.payload = payload;
  } else {
    delete extraObj.payload;
  }
};

const removeThinkingLevel = (extraObj?: Record<string, unknown>) => {
  if (!extraObj) {
    return;
  }
  delete extraObj.thinking_level;
  if (!extraObj.payload || typeof extraObj.payload !== "object" || Array.isArray(extraObj.payload)) {
    return;
  }
  const payload = extraObj.payload as Record<string, unknown>;
  if (!payload.thinking || typeof payload.thinking !== "object" || Array.isArray(payload.thinking)) {
    return;
  }
  const thinking = { ...(payload.thinking as Record<string, unknown>) };
  delete thinking.type;
  if (Object.keys(thinking).length > 0) {
    payload.thinking = thinking;
  } else {
    delete payload.thinking;
  }
};

const removeMaxTokensParam = (extraObj?: Record<string, unknown>) => {
  if (!extraObj) {
    return;
  }
  delete extraObj.max_tokens_param;
};

const applyFormOptions = (obj: Record<string, unknown>, values: ModelFormValues) => {
  if (values.max_tokens_param && values.max_tokens_param !== "max_tokens") {
    obj.max_tokens_param = values.max_tokens_param;
  } else {
    delete obj.max_tokens_param;
  }
  if (values.thinking_level && values.thinking_level !== "none") {
    obj.thinking_level = values.thinking_level;
  } else {
    delete obj.thinking_level;
  }
  if (values.model_type === "image") {
    const payload =
      obj.payload && typeof obj.payload === "object" && !Array.isArray(obj.payload)
        ? { ...(obj.payload as Record<string, unknown>) }
        : {};
    if (values.force_image_base64) {
      payload.response_format = "b64_json";
    } else {
      delete payload.response_format;
    }
    if (Object.keys(payload).length > 0) {
      obj.payload = payload;
    } else {
      delete obj.payload;
    }
  }
};

const toFormValues = (model: Model): ModelFormValues => {
  const extraObj =
    model.extra && typeof model.extra === "object" && !Array.isArray(model.extra)
      ? JSON.parse(JSON.stringify(model.extra))
      : undefined;
  const thinkingLevel = extractThinkingLevel(extraObj);
  const maxTokensParam = extractMaxTokensParam(extraObj);
  const forceImageBase64 = model.model_type === "image" && extractForceImageBase64(extraObj);
  removeThinkingLevel(extraObj);
  removeMaxTokensParam(extraObj);
  if (model.model_type === "image") {
    removeImageResponseFormat(extraObj);
  }

  const extraString =
    extraObj && Object.keys(extraObj).length > 0
      ? JSON.stringify(extraObj, null, 2)
      : JSON.stringify(DEFAULT_EXTRA_OBJECT, null, 2);

  return {
    name: model.name,
    provider: model.provider,
    base_url: model.base_url ?? "",
    api_key: model.api_key ?? "",
    max_tokens: model.max_tokens ?? undefined,
    temperature: model.temperature ?? undefined,
    top_p: model.top_p ?? undefined,
    max_tokens_param: maxTokensParam,
    thinking_level: thinkingLevel,
    force_image_base64: forceImageBase64,
    extra: extraString,
    request_standard:
      (model.request_standard as "openai" | "gemini" | "anthropic" | "openai_images") ?? "openai",
    model_type: model.model_type ?? "text"
  };
};

const getServerErrorMessage = (error: unknown, fallback: string) => {
  const err = error as { response?: { data?: { detail?: { message?: string } } }; message?: string };
  return err.response?.data?.detail?.message || err.message || fallback;
};

function ModelFormModal({ open, initialValues, confirmLoading, onCancel, onSubmit }: ModelFormModalProps) {
  const [form] = Form.useForm<ModelFormValues>();
  const [remoteModels, setRemoteModels] = useState<string[]>([]);
  const [modelOptionsOpen, setModelOptionsOpen] = useState(false);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [testing, setTesting] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [imagePreviewOpen, setImagePreviewOpen] = useState(false);
  const modelType = Form.useWatch("model_type", form) ?? "text";

  const isEdit = Boolean(initialValues);
  const title = useMemo(() => (isEdit ? "编辑模型" : "新增模型"), [isEdit]);

  useEffect(() => {
    if (!open) {
      setRemoteModels([]);
      setModelOptionsOpen(false);
      setAdvancedOpen(false);
      setImagePreview(null);
      setImagePreviewOpen(false);
      form.resetFields();
      return;
    }

    const values = initialValues ? toFormValues(initialValues) : defaultValues;
    form.setFieldsValue(values);
    setRemoteModels([]);
    setModelOptionsOpen(false);
    setAdvancedOpen(false);
    setImagePreview(null);
    setImagePreviewOpen(false);
  }, [open, initialValues, form]);

  const buildExtraObject = (values: ModelFormValues): Record<string, unknown> => {
    let extraObj: Record<string, unknown> | undefined;
    if (values.extra && values.extra.trim()) {
      extraObj = JSON.parse(values.extra);
    }
    const cloned = ensureJsonObject(extraObj);
    applyFormOptions(cloned, values);
    return cloned;
  };

  const handleFinish = async (values: ModelFormValues) => {
    let extraObject: Record<string, unknown>;
    try {
      extraObject = buildExtraObject(values);
    } catch {
      form.setFields([{ name: "extra", errors: ["extra 字段需为合法 JSON"] }]);
      return;
    }

    const provider = values.provider.trim();
    const baseUrl = values.base_url?.trim() ? values.base_url.trim() : undefined;
    const maxTokens = typeof values.max_tokens === "number" ? values.max_tokens : undefined;
    const temperature = typeof values.temperature === "number" ? values.temperature : undefined;
    const topP = typeof values.top_p === "number" ? values.top_p : undefined;

    const common = {
      name: values.name.trim(),
      provider,
      base_url: baseUrl ?? null,
      max_tokens: maxTokens ?? null,
      temperature: temperature ?? null,
      top_p: topP ?? null,
      extra: extraObject,
      request_standard: values.request_standard,
      model_type: values.model_type
    };

    const apiKey = values.api_key?.trim();
    if (isEdit) {
      const updatePayload: ModelUpdatePayload = {
        ...common,
        base_url: baseUrl,
        max_tokens: maxTokens,
        temperature,
        top_p: topP
      };
      if (apiKey) {
        updatePayload.api_key = apiKey;
      }
      onSubmit(updatePayload);
    } else {
      if (!apiKey) {
        form.setFields([{ name: "api_key", errors: ["请输入 API Key"] }]);
        return;
      }
      const createPayload: ModelCreatePayload = {
        ...common,
        api_key: apiKey
      };
      onSubmit(createPayload);
    }
  };

  const handleFetchRemoteModels = async () => {
    const values = form.getFieldsValue();
    const baseUrl = values.base_url?.trim();
    const apiKey = values.api_key?.trim();
    if (!baseUrl) {
      message.error("请先填写 Base URL");
      return;
    }
    if (!apiKey && !initialValues?.id) {
      message.error("请先填写 API Key");
      return;
    }
    setModelsLoading(true);
    try {
      const models = await fetchRemoteModels({
        base_url: baseUrl,
        api_key: apiKey || undefined,
        model_id: !apiKey && initialValues?.id ? initialValues.id : undefined
      });
      setRemoteModels(models);
      if (models.length === 0) {
        setModelOptionsOpen(false);
        message.info("该厂商不支持自动拉取，请手填模型ID");
      } else {
        setModelOptionsOpen(true);
        message.success("模型列表已拉取");
      }
    } catch (error: unknown) {
      setRemoteModels([]);
      setModelOptionsOpen(false);
      message.error(getServerErrorMessage(error, "该厂商不支持自动拉取，请手填模型ID"));
    } finally {
      setModelsLoading(false);
    }
  };

  const handleTestConnection = async () => {
    try {
      await form.validateFields(["name", "provider", "base_url", "extra"]);
    } catch {
      return;
    }

    const values = form.getFieldsValue();
    let extraObject: Record<string, unknown>;
    try {
      extraObject = buildExtraObject(values);
    } catch {
      form.setFields([{ name: "extra", errors: ["extra 字段需为合法 JSON"] }]);
      return;
    }

    const provider = values.provider?.trim();
    const baseUrl = values.base_url?.trim() ?? undefined;
    const apiKey = values.api_key?.trim();
    const modelId = isEdit && !apiKey ? initialValues?.id : undefined;

    if (!provider && !modelId) {
      message.error("请填写模型ID");
      return;
    }

    if (values.model_type === "image") {
      const confirmed = await new Promise<boolean>((resolve) => {
        Modal.confirm({
          title: "确认进行图片连通性测试？",
          content: "测试会真实调用一次图片接口并产生费用。系统会生成一张低质量小测试图，不会保存到本地。",
          okText: "开始测试",
          cancelText: "取消",
          onOk: () => resolve(true),
          onCancel: () => resolve(false)
        });
      });
      if (!confirmed) {
        return;
      }
    }

    setTesting(true);
    setImagePreview(null);
    setImagePreviewOpen(false);
    try {
      const result = await testModelConnection({
        provider,
        base_url: baseUrl,
        api_key: apiKey || undefined,
        max_tokens: typeof values.max_tokens === "number" ? values.max_tokens : undefined,
        temperature: typeof values.temperature === "number" ? values.temperature : undefined,
        top_p: typeof values.top_p === "number" ? values.top_p : undefined,
        extra: extraObject,
        model_id: modelId,
        request_standard: values.model_type === "image" ? "openai_images" : values.request_standard,
        model_type: values.model_type
      });
      if (values.model_type === "image") {
        if (!result.preview) {
          throw new Error("图片接口返回成功，但没有可预览的图片");
        }
        setImagePreview(result.preview);
        setImagePreviewOpen(true);
      }
      message.success("连通性测试成功");
    } catch (error: unknown) {
      message.error(getServerErrorMessage(error, "连通性测试失败"));
    } finally {
      setTesting(false);
    }
  };

  const handleCancel = () => {
    form.resetFields();
    setImagePreview(null);
    setImagePreviewOpen(false);
    onCancel();
  };

  const closeImagePreview = () => {
    setImagePreviewOpen(false);
    setImagePreview(null);
  };

  const remoteModelOptions = remoteModels.map((item) => ({
    label: item,
    value: item
  }));

  const showHelp = () => {
    Modal.info({
      title: "模型配置说明",
      width: 560,
      content: (
        <div style={{ paddingTop: 8 }}>
          <p>配置步骤：</p>
          <ol style={{ paddingLeft: 20 }}>
            <li>填写模型厂商、模型ID、Base URL 和 API Key。</li>
            <li>模型ID是真正发给厂商的 <code>model</code> 字段，例如 <code>deepseek-ai/DeepSeek-V3.2-Exp</code>。</li>
            <li>Base URL 当前会被系统直接请求，请填写完整接口地址，例如 <code>https://api.deepseek.com/chat/completions</code>。</li>
            <li>根据接口协议选择请求标准：OpenAI=Chat Completions，Gemini=generateContent，Anthropic=/v1/messages。</li>
            <li>可点击“拉取模型列表”尝试从厂商接口获取模型ID；如果厂商不支持，手填即可。</li>
            <li>最大输出 token、温度、Top P、思考级别会按请求标准自动写入实际请求体；OpenAI 兼容请求固定使用流式返回。</li>
            <li>图片模型使用 OpenAI Images 兼容接口，只填域名即可；系统会自动补齐并去重 /v1/images/generations。</li>
          </ol>
          <p style={{ marginTop: 12 }}>补充说明：</p>
          <ul style={{ paddingLeft: 20 }}>
            <li>API Key 会在本地编辑弹窗中展示，点击密码框的小眼睛即可查看。</li>
            <li>高级配置里的 <code>payload</code> 用于增加厂商特殊字段；图片模型的模型ID、提示词、尺寸、单张数量和 PNG 格式由系统锁定。</li>
            <li>如果厂商要求 <code>max_completion_tokens</code>，可在“最大输出参数名”中切换。</li>
          </ul>
        </div>
      )
    });
  };

  return (
    <>
      <Modal
      open={open}
      title={title}
      destroyOnClose
      onCancel={handleCancel}
      footer={[
        <Button key="test" onClick={handleTestConnection} loading={testing}>
          连通性测试
        </Button>,
        <Button key="cancel" onClick={handleCancel}>
          取消
        </Button>,
        <Button key="ok" type="primary" onClick={() => form.submit()} loading={confirmLoading}>
          保存
        </Button>
      ]}
    >
      <Form<ModelFormValues> form={form} layout="vertical" initialValues={defaultValues} onFinish={handleFinish}>
        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
          <Button type="link" onClick={showHelp} style={{ padding: 0 }} htmlType="button">
            查看配置说明
          </Button>
        </div>
        <Form.Item
          label="模型厂商"
          name="name"
          rules={[
            { required: true, message: "请输入模型厂商" },
            { max: 100, message: "名称长度需小于 100 个字符" }
          ]}
        >
          <Input placeholder="例如：火山方舟 Coding Plan" />
        </Form.Item>
        <Form.Item label="模型用途" name="model_type" rules={[{ required: true }]}>
          <Select
            options={[
              { label: "文本模型", value: "text" },
              { label: "图片模型", value: "image" }
            ]}
            onChange={(value) => {
              form.setFieldValue("request_standard", value === "image" ? "openai_images" : "openai");
              setImagePreview(null);
              setImagePreviewOpen(false);
            }}
          />
        </Form.Item>
        <Form.Item
          label="模型ID"
          required
          tooltip="调用时发送给厂商的真实 model 字段，例如 deepseek-ai/DeepSeek-V3.2-Exp"
        >
          <Space.Compact style={{ width: "100%" }}>
            <Form.Item
              name="provider"
              noStyle
              rules={[
                { required: true, message: "请输入模型ID" },
                { max: 50, message: "模型ID长度需小于 50 个字符" }
              ]}
            >
              <AutoComplete
                open={modelOptionsOpen && remoteModels.length > 0}
                placeholder="例如：deepseek-ai/DeepSeek-V3.2-Exp"
                options={remoteModelOptions}
                filterOption={(input, option) =>
                  String(option?.value ?? "").toLowerCase().includes(input.toLowerCase())
                }
                onDropdownVisibleChange={setModelOptionsOpen}
                onSelect={() => setModelOptionsOpen(false)}
                onFocus={() => {
                  if (remoteModels.length > 0) {
                    setModelOptionsOpen(true);
                  }
                }}
                style={{ minWidth: 0 }}
              />
            </Form.Item>
            <Button onClick={handleFetchRemoteModels} loading={modelsLoading}>
              拉取模型列表
            </Button>
          </Space.Compact>
        </Form.Item>
        <Form.Item label="Base URL" name="base_url">
          <Input
            placeholder={
              modelType === "image"
                ? "只填域名即可，例如 https://api.openai.com"
                : "完整接口地址，例如 https://api.deepseek.com/chat/completions"
            }
          />
        </Form.Item>
        {modelType === "image" ? (
          <div style={{ marginTop: -16, marginBottom: 16, color: "rgba(0, 0, 0, 0.45)" }}>
            系统会自动补齐 <code>/v1/images/generations</code>；已填写完整路径时不会重复追加。
          </div>
        ) : null}
        {modelType === "text" ? <Form.Item
          label="请求标准"
          name="request_standard"
          tooltip="决定请求体/鉴权标准。OpenAI=Chat Completions；Gemini=generateContent；Anthropic=/v1/messages。"
          extra="当前系统会直接请求填写的 Base URL；OpenAI 兼容接口请填写完整 chat/completions 地址。"
        >
          <Select
            options={[
              { label: "OpenAI", value: "openai" },
              { label: "Gemini", value: "gemini" },
              { label: "Anthropic", value: "anthropic" }
            ]}
          />
        </Form.Item> : (
          <Form.Item name="request_standard" hidden>
            <Input />
          </Form.Item>
        )}
        <Form.Item
          label="API Key"
          name="api_key"
          rules={
            isEdit
              ? [{ max: 2048, message: "API Key 长度过长" }]
              : [
                  { required: true, message: "请输入 API Key" },
                  { max: 2048, message: "API Key 长度过长" }
                ]
          }
        >
          <Input.Password placeholder={isEdit ? "已从数据库加载，可点击小眼睛查看" : "请输入密钥"} />
        </Form.Item>
        {modelType === "text" ? <><Form.Item label="最大输出 token" name="max_tokens">
          <InputNumber min={1} style={{ width: "100%" }} placeholder="可选，例如 4000" />
        </Form.Item>
        <Form.Item
          label="最大输出参数名"
          name="max_tokens_param"
          tooltip="OpenAI 兼容接口常用 max_tokens；部分接口使用 max_completion_tokens。选择“不传”时最大输出 token 只保存，不进入请求体。"
        >
          <Select
            options={[
              { label: "max_tokens（默认）", value: "max_tokens" },
              { label: "max_completion_tokens", value: "max_completion_tokens" },
              { label: "不传", value: "none" }
            ]}
          />
        </Form.Item>
        <Form.Item label="温度" name="temperature">
          <InputNumber min={0} max={100} step={0.1} precision={3} style={{ width: "100%" }} placeholder="可选，例如 0.3 或 1" />
        </Form.Item>
        <Form.Item label="Top P" name="top_p">
          <InputNumber min={0} max={100} step={0.1} precision={3} style={{ width: "100%" }} placeholder="可选，例如 0.8 或 1" />
        </Form.Item>
        <Form.Item label="思考级别" name="thinking_level" tooltip="OpenAI 官方接口写入 reasoning_effort；DeepSeek V4 兼容接口会自动写入 thinking.enabled + reasoning_effort。">
          <Select
            options={[
              { label: "无", value: "none" },
              { label: "low", value: "low" },
              { label: "medium", value: "medium" },
              { label: "high", value: "high" },
              { label: "xhigh / max", value: "xhigh" }
            ]}
          />
        </Form.Item></> : (
          <>
            <Form.Item
              label="兼容代理接口"
              name="force_image_base64"
              valuePropName="checked"
              tooltip="OpenAI 官方 GPT Image 默认返回 Base64，不需要开启。仅当第三方代理返回图片 URL，或提示“只返回了图片 URL”时开启；开启后会增加 response_format: b64_json。"
              extra="只有第三方代理返回图片 URL 时才需要开启。"
            >
              <Switch checkedChildren="已开启" unCheckedChildren="关闭" />
            </Form.Item>
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
              message="图片连通性测试会真实生成一张图片并产生费用"
              description="测试固定使用 1024×1024、低质量、无文字的简单图案；是否强制返回 Base64 由上方兼容开关控制。"
            />
          </>
        )}
        <Button type="link" style={{ padding: 0, marginBottom: 12 }} onClick={() => setAdvancedOpen((value) => !value)}>
          {advancedOpen ? "收起高级配置" : "展开高级配置"}
        </Button>
        {advancedOpen ? (
          <Form.Item
            label="高级配置 (JSON)"
            name="extra"
            tooltip={
              <span>
                支持 <code>payload</code> / <code>headers</code> / <code>query_params</code> / <code>auth_header</code> 等键；留空则默认
                <code>{DEFAULT_EXTRA_JSON}</code>
              </span>
            }
            extra={
              <div style={{ color: "#6c757d" }}>
                <div>
                  一般不用填写。这里的 <code>payload</code> 用于增加厂商特殊字段；图片返回方式由上方“兼容代理接口”开关控制。
                </div>
                示例：<code>{OPENAI_EXTRA_EXAMPLE}</code>
                <br />Gemini 代理：<code>{GEMINI_QUERY_EXAMPLE}</code> 或 <code>{GEMINI_AUTH_HEADER_EXAMPLE}</code>
              </div>
            }
          >
            <Input.TextArea placeholder={`请输入 JSON 对象，例如 ${DEFAULT_EXTRA_JSON}`} autoSize={{ minRows: 3, maxRows: 6 }} />
          </Form.Item>
        ) : null}
      </Form>
      </Modal>
      <Modal
        open={imagePreviewOpen && Boolean(imagePreview)}
        title="图片模型连通性测试结果"
        width={560}
        maskClosable={false}
        destroyOnClose
        onCancel={closeImagePreview}
        footer={[
          <Button key="close" type="primary" onClick={closeImagePreview}>
            关闭
          </Button>
        ]}
      >
        <div style={{ textAlign: "center", padding: "8px 0" }}>
          {imagePreview ? (
            <Image
              preview={false}
              src={imagePreview}
              alt="图片模型连通性测试结果"
              style={{ maxWidth: "100%", maxHeight: "60vh", objectFit: "contain" }}
            />
          ) : null}
          <div style={{ marginTop: 12, color: "rgba(0, 0, 0, 0.45)" }}>
            图片仅用于本次连通性确认，不会保存到本地。
          </div>
        </div>
      </Modal>
    </>
  );
}

export default ModelFormModal;
