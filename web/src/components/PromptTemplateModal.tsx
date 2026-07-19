import { useEffect } from "react";
import { Form, Input, Modal } from "antd";
import type { PromptTemplate, PromptTemplatePayload } from "../services/promptTemplates";

type PromptTemplateModalProps = {
  open: boolean;
  initialValues?: PromptTemplate | null;
  confirmLoading?: boolean;
  onSubmit: (payload: PromptTemplatePayload) => void | Promise<void>;
  onCancel: () => void;
};

const defaultValues: PromptTemplatePayload = {
  name: "",
  content: "",
  description: ""
};

function PromptTemplateModal({ open, initialValues, confirmLoading, onSubmit, onCancel }: PromptTemplateModalProps) {
  const [form] = Form.useForm<PromptTemplatePayload>();
  const title = initialValues ? "编辑提示词" : "新建提示词";

  useEffect(() => {
    if (!open) {
      return;
    }
    form.resetFields();
    if (initialValues) {
      form.setFieldsValue({
        name: initialValues.name,
        content: initialValues.content,
        description: initialValues.description ?? ""
      });
    } else {
      form.setFieldsValue(defaultValues);
    }
  }, [open, initialValues, form]);

  return (
    <Modal
      open={open}
      title={title}
      okText="保存"
      cancelText="取消"
      confirmLoading={confirmLoading}
      onOk={() => form.submit()}
      onCancel={() => {
        form.resetFields();
        onCancel();
      }}
    >
      <Form<PromptTemplatePayload> layout="vertical" form={form} onFinish={onSubmit}>
        <Form.Item
          label="提示词名称"
          name="name"
          rules={[
            { required: true, message: "请输入提示词名称" },
            { max: 120, message: "名称需在 120 字以内" }
          ]}
        >
          <Input placeholder="例如：测试群-结构化日报" />
        </Form.Item>
        <Form.Item
          label="提示词内容"
          name="content"
          rules={[{ required: true, message: "请输入提示词内容" }]}
        >
          <Input.TextArea placeholder="请输入完整提示词" autoSize={{ minRows: 4, maxRows: 12 }} />
        </Form.Item>
        <Form.Item label="备注" name="description">
          <Input.TextArea placeholder="可选描述，方便后续查找" autoSize={{ minRows: 2, maxRows: 4 }} />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default PromptTemplateModal;
