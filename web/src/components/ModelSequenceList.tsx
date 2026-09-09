/**
 * 模型执行顺序编辑列表：文本模型与图片模型两处 Form.List 的公共实现。
 * 差异（选项、文案）全部由 props 表达，结构与交互保持一致。
 */
import { Button, Form, InputNumber, Select, Space, Tooltip, Typography } from "antd";
import { ArrowDownOutlined, ArrowUpOutlined, DeleteOutlined, InfoCircleOutlined, PlusOutlined } from "@ant-design/icons";

type Option<T = string | number> = { label: string; value: T };

type ModelSequenceListProps = {
  /** Form.List 字段名 */
  name: "model_sequence" | "image_model_sequence";
  /** 实体名："模型" / "图片模型"，用于派生列头、校验文案与按钮文案 */
  entityLabel: string;
  title: string;
  tooltip: string;
  options: Option<number>[];
};

function ModelSequenceList({ name, entityLabel, title, tooltip, options }: ModelSequenceListProps) {
  return (
    <Form.List name={name}>
      {(fields, { add, remove, move }) => (
        <div style={{ marginBottom: 16 }}>
          <Space align="center" style={{ marginBottom: 8 }}>
            <Typography.Text strong>{title}</Typography.Text>
            <Tooltip title={tooltip}>
              <InfoCircleOutlined />
            </Tooltip>
          </Space>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "48px minmax(260px, 1fr) 150px 116px",
              gap: 8,
              marginBottom: 6,
              color: "rgba(0, 0, 0, 0.45)",
              fontSize: 12
            }}
          >
            <span>顺序</span>
            <span>{entityLabel}</span>
            <span>最多执行次数</span>
            <span>操作</span>
          </div>
          <div style={{ display: "grid", gap: 8 }}>
            {fields.map((field, index) => (
              <div
                key={field.key}
                style={{
                  display: "grid",
                  gridTemplateColumns: "48px minmax(260px, 1fr) 150px 116px",
                  gap: 8,
                  alignItems: "center"
                }}
              >
                <Typography.Text type="secondary">#{index + 1}</Typography.Text>
                <Form.Item
                  {...field}
                  name={[field.name, "model_id"]}
                  rules={[{ required: true, message: `请选择${entityLabel}` }]}
                  style={{ marginBottom: 0 }}
                >
                  <Select
                    showSearch
                    placeholder={index === 0 ? `请选择主${entityLabel}` : `请选择备用${entityLabel}`}
                    options={options}
                    optionFilterProp="label"
                  />
                </Form.Item>
                <Form.Item
                  {...field}
                  name={[field.name, "max_attempts"]}
                  rules={[{ required: true, message: "请输入次数" }]}
                  style={{ marginBottom: 0 }}
                >
                  <InputNumber min={1} placeholder="次数" style={{ width: "100%" }} />
                </Form.Item>
                <Space size={4}>
                  <Tooltip title="上移">
                    <Button size="small" icon={<ArrowUpOutlined />} disabled={index === 0} onClick={() => move(index, index - 1)} />
                  </Tooltip>
                  <Tooltip title="下移">
                    <Button size="small" icon={<ArrowDownOutlined />} disabled={index === fields.length - 1} onClick={() => move(index, index + 1)} />
                  </Tooltip>
                  <Tooltip title="删除">
                    <Button size="small" icon={<DeleteOutlined />} disabled={fields.length <= 1} onClick={() => remove(field.name)} />
                  </Tooltip>
                </Space>
              </div>
            ))}
          </div>
          <Button
            type="dashed"
            icon={<PlusOutlined />}
            style={{ marginTop: 10 }}
            onClick={() => add({ model_id: undefined, max_attempts: 2 })}
          >
            添加备用{entityLabel}
          </Button>
        </div>
      )}
    </Form.List>
  );
}

export default ModelSequenceList;
export type { Option };
