import { useEffect, useMemo, useState } from "react";
import { Button, Form, Input, Modal, Select, Space, Switch, Typography, message } from "antd";
import { testWebhookImage, type Webhook, type WebhookCreatePayload, type WebhookUpdatePayload } from "../services/webhooks";

type WebhookFormValues = {
  name: string;
  url?: string;
  headers?: string;
  card_mode: Webhook["card_mode"];
  card_header_enabled: boolean;
  card_header_title?: string;
  card_header_subtitle?: string;
  card_header_color?: string;
  image_render_engine: Webhook["image_render_engine"];
  feishu_app_id?: string;
  feishu_app_secret?: string;
};

type WebhookFormModalProps = {
  open: boolean;
  initialValues?: Webhook | null;
  confirmLoading?: boolean;
  onCancel: () => void;
  onSubmit: (payload: WebhookCreatePayload | WebhookUpdatePayload) => void | Promise<void>;
};

const defaultValues: WebhookFormValues = {
  name: "",
  url: "",
  headers: "",
  card_mode: "markdown",
  card_header_enabled: false,
  card_header_title: "",
  card_header_subtitle: "",
  card_header_color: "blue",
  image_render_engine: "satori",
  feishu_app_id: "",
  feishu_app_secret: ""
};

const COLOR_OPTIONS = [
  { value: "blue", label: "蓝色（blue）" },
  { value: "wathet", label: "天蓝（wathet）" },
  { value: "turquoise", label: "青绿（turquoise）" },
  { value: "green", label: "绿色（green）" },
  { value: "yellow", label: "黄色（yellow）" },
  { value: "orange", label: "橙色（orange）" },
  { value: "red", label: "红色（red）" },
  { value: "carmine", label: "洋红（carmine）" },
  { value: "violet", label: "紫罗兰（violet）" },
  { value: "purple", label: "紫色（purple）" },
  { value: "indigo", label: "靛青（indigo）" },
  { value: "grey", label: "灰色（grey）" },
  { value: "default", label: "默认（default）" }
];

const CARD_MODE_OPTIONS = [
  { label: "Markdown 卡片（默认）", value: "markdown" },
  { label: "模板模式（敬请期待）", value: "template", disabled: true },
  { label: "JSON 卡片（敬请期待）", value: "custom_json", disabled: true }
];

const toFormValues = (webhook: Webhook): WebhookFormValues => ({
  name: webhook.name,
  url: "",
  headers: webhook.headers ? JSON.stringify(webhook.headers, null, 2) : "",
  card_mode: webhook.card_mode ?? "markdown",
  card_header_enabled: webhook.card_header_enabled ?? false,
  card_header_title: webhook.card_header_title ?? "",
  card_header_subtitle: webhook.card_header_subtitle ?? "",
  card_header_color: webhook.card_header_color ?? "blue",
  image_render_engine: webhook.image_render_engine ?? "satori",
  feishu_app_id: webhook.feishu_app_id ?? "",
  feishu_app_secret: ""
});

const { Text } = Typography;

function WebhookFormModal({ open, initialValues, confirmLoading, onCancel, onSubmit }: WebhookFormModalProps) {
  const [form] = Form.useForm<WebhookFormValues>();
  const [testingUpload, setTestingUpload] = useState(false);
  const [testingPush, setTestingPush] = useState(false);
  const isEdit = Boolean(initialValues);
  const title = useMemo(() => (isEdit ? "编辑 Webhook" : "新增 Webhook"), [isEdit]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const values = initialValues ? toFormValues(initialValues) : defaultValues;
    form.resetFields();
    form.setFieldsValue(values);
  }, [open, initialValues, form]);

  const modeValue = Form.useWatch("card_mode", form);
  const headerEnabled = Form.useWatch("card_header_enabled", form);

  const handleFinish = (values: WebhookFormValues) => {
    let parsedHeaders: Record<string, unknown> | null | undefined;
    if (values.headers && values.headers.trim()) {
      try {
        parsedHeaders = JSON.parse(values.headers);
      } catch (error) {
        form.setFields([{ name: "headers", errors: ["headers 字段需为合法 JSON"] }]);
        return;
      }
    } else if (!isEdit) {
      parsedHeaders = null;
    }

    const enableHeader = values.card_mode === "markdown" && headerEnabled;
    const commonPayload = {
      headers: parsedHeaders,
      card_mode: values.card_mode,
      card_header_enabled: enableHeader,
      card_header_title: enableHeader ? values.card_header_title?.trim() || null : null,
      card_header_subtitle: enableHeader ? values.card_header_subtitle?.trim() || null : null,
      card_header_color: enableHeader ? values.card_header_color ?? "blue" : null,
      image_render_engine: values.image_render_engine ?? "satori",
      feishu_app_id: values.feishu_app_id?.trim() || null,
      feishu_app_secret: values.feishu_app_secret?.trim() || null
    };

    if (isEdit) {
      const payload: WebhookUpdatePayload = {
        name: values.name.trim() || undefined,
        ...commonPayload
      };
      const url = values.url?.trim();
      if (url) {
        payload.url = url;
      }
      onSubmit(payload);
    } else {
      const url = values.url?.trim();
      if (!url) {
        form.setFields([{ name: "url", errors: ["请输入 Webhook URL"] }]);
        return;
      }
      const payload: WebhookCreatePayload = {
        name: values.name.trim(),
        url,
        ...commonPayload
      };
      onSubmit(payload);
    }
  };

  const handleImageTest = async (sendImage: boolean) => {
    if (!initialValues?.id) {
      message.warning("请先保存 Webhook，再测试图片上传。");
      return;
    }
    const values = form.getFieldsValue();
    try {
      if (sendImage) {
        setTestingPush(true);
      } else {
        setTestingUpload(true);
      }
      const result = await testWebhookImage(initialValues.id, {
        app_id: values.feishu_app_id?.trim() || undefined,
        app_secret: values.feishu_app_secret?.trim() || undefined,
        send_image: sendImage
      });
      if (result.ok) {
        message.success(result.image_key ? `${result.message}：${result.image_key}` : result.message);
      } else {
        message.error(result.message);
      }
    } catch (error) {
      const err = error as Error;
      message.error(err.message || "图片测试失败");
    } finally {
      setTestingUpload(false);
      setTestingPush(false);
    }
  };

  return (
    <Modal
      open={open}
      title={title}
      destroyOnHidden
      onCancel={() => {
        form.resetFields();
        onCancel();
      }}
      onOk={() => form.submit()}
      confirmLoading={confirmLoading}
    >
      <Form<WebhookFormValues>
        layout="vertical"
        form={form}
        initialValues={defaultValues}
        onFinish={handleFinish}
      >
        <Form.Item
          label="Webhook 名称"
          name="name"
          rules={[
            { required: true, message: "请输入名称" },
            { max: 120, message: "名称长度需小于 120 个字符" }
          ]}
        >
          <Input placeholder="例如：飞书日报提醒" />
        </Form.Item>
        <Form.Item
          label="Webhook URL"
          name="url"
          rules={isEdit ? [] : [{ required: true, message: "请输入 Webhook URL" }]}
          extra={isEdit ? "留空则沿用现有 URL" : undefined}
        >
          <Input placeholder={isEdit ? "留空保持不变" : "https://open.feishu.cn/xxx"} />
        </Form.Item>
        <Form.Item label="Headers (JSON)" name="headers">
          <Input.TextArea placeholder='可选，例 {"Authorization":"Bearer token"}' autoSize={{ minRows: 3, maxRows: 6 }} />
        </Form.Item>
        <Form.Item label="卡片模式" name="card_mode">
          <Select options={CARD_MODE_OPTIONS} />
        </Form.Item>
        <Form.Item
          label="自定义标题 / 副标题 / 主题色"
          name="card_header_enabled"
          valuePropName="checked"
          extra="仅在 Markdown 卡片模式下生效。"
        >
          <Switch disabled={modeValue !== "markdown"} />
        </Form.Item>
        {modeValue === "markdown" ? (
          <>
            <Form.Item
              label="卡片标题"
              name="card_header_title"
              extra="可选，支持 {task_name} / {job_name} 占位符；留空则使用作业名称。"
            >
              <Input placeholder="例如：{task_name} · {job_name}" disabled={!headerEnabled} />
            </Form.Item>
            <Form.Item
              label="卡片副标题"
              name="card_header_subtitle"
              extra="可选，支持 {task_name} / {job_name} 占位符。"
            >
              <Input placeholder="例如：执行时间 {job_name}" disabled={!headerEnabled} />
            </Form.Item>
            <Form.Item label="主题色" name="card_header_color" extra="仅在启用自定义标题时生效。">
              <Select options={COLOR_OPTIONS} disabled={!headerEnabled} />
            </Form.Item>
            <Text type="secondary">提示：正文内容依旧使用 Markdown 渲染，支持多级标题与引用。</Text>
          </>
        ) : (
          <Text type="secondary">模板 / JSON 模式将在后续版本开放配置。</Text>
        )}
        <Form.Item
          label="图片渲染引擎"
          name="image_render_engine"
          tooltip="话题卡片图片推送时使用；默认 Satori，SVG 和 Typst 作为可选方案。"
        >
          <Select
            options={[
              { label: "Satori", value: "satori" },
              { label: "SVG", value: "svg" },
              { label: "Typst", value: "typst" }
            ]}
          />
        </Form.Item>
        <Form.Item
          label="飞书应用 App ID"
          name="feishu_app_id"
          tooltip="用于上传图片到飞书，和当前 Webhook 绑定。"
        >
          <Input placeholder="cli_xxx" />
        </Form.Item>
        <Form.Item
          label="飞书应用 App Secret"
          name="feishu_app_secret"
          tooltip="保存后后端会加密存储；编辑时不会回显，留空表示沿用已保存的密钥。"
          extra={isEdit && initialValues?.has_feishu_app_secret ? "已保存密钥；如需更换请重新填写。" : undefined}
        >
          <Input.Password placeholder={isEdit ? "留空保持不变" : "请输入 App Secret"} />
        </Form.Item>
        <Space>
          <Button disabled={!isEdit} loading={testingUpload} onClick={() => void handleImageTest(false)}>
            测试图片上传
          </Button>
          <Button disabled={!isEdit} loading={testingPush} onClick={() => void handleImageTest(true)}>
            测试图片推送
          </Button>
        </Space>
      </Form>
    </Modal>
  );
}

export default WebhookFormModal;
