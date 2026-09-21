/**
 * 图片卡片配置分区。从 JobFormModal 拆出，逻辑原样搬移。
 */
import { Button, Form, Input, InputNumber, Popover, Select, Space, Switch, Typography } from "antd";
import { QuestionCircleOutlined } from "@ant-design/icons";
import { DEFAULT_IMAGE_SPLIT_PROMPT } from "../../../services/promptTemplates";
import type { PromptTemplate } from "../../../services/promptTemplates";

function ImageCardSection({
  imagePromptTemplateOptions,
  loading,
  htmlEngineEnabled = false
}: {
  imagePromptTemplateOptions: { label: string; value: number }[];
  loading: boolean;
  htmlEngineEnabled?: boolean;
}) {
  const form = Form.useFormInstance();
  const imageSplitEnabled = Form.useWatch("image_split_enabled", form);

  return (
    <>
      <Form.Item
        name="image_prompt_template_id"
        label={htmlEngineEnabled ? "关系图生图提示词模板" : "图片提示词模板"}
        tooltip={
          htmlEngineEnabled
            ? "本地 HTML 引擎已开启：整卡由 HTML 排版渲染，该模板用于人物关系图的生图提示词（画型/节点/连线占位符由系统按卡片数据自动填充）。出卡时会自动产出小红书 3:4 分页图（与整卡同目录 pages/ 下）。"
            : "该模板只负责每张图片的视觉风格和排版要求，会与拆分后的每个 Markdown 内容块组合后发送给图片模型。"
        }
        rules={[{ required: true, message: "请选择图片提示词模板" }]}
      >
        <Select
          options={imagePromptTemplateOptions}
          loading={loading}
          placeholder={loading ? "加载中..." : "请选择图片提示词模板"}
          optionFilterProp="label"
          showSearch
        />
      </Form.Item>
      <Form.Item
        name="image_split_enabled"
        label="逐话题生成"
        valuePropName="checked"
        tooltip="开启后，文本模型用固定标识分隔每个话题，系统为每个话题生成一张图片；关闭后，整份模型结果只生成一张图片。"
      >
        <Switch />
      </Form.Item>
      {imageSplitEnabled ? (
        <>
          <Form.Item
            name="image_split_prompt"
            label={
              <Space size={4}>
                <span>内容拆分规则</span>
                <Popover
                  placement="rightTop"
                  trigger="click"
                  title="内容拆分规则说明"
                  content={
                    <div style={{ width: 460, maxWidth: "70vw", userSelect: "text", cursor: "text" }}>
                      <Typography.Paragraph style={{ marginBottom: 8 }}>
                        该规则用于拆分内容并逐块生图，无符合内容时跳过生图。
                      </Typography.Paragraph>
                      <pre
                        style={{
                          margin: "8px 0 0",
                          padding: 12,
                          borderRadius: 6,
                          background: "#f5f5f5",
                          whiteSpace: "pre-wrap",
                          userSelect: "text"
                        }}
                      >{`${"${block_start}"}\n${"${block_end}"}`}</pre>
                      <Typography.Text type="secondary">
                        前者标记内容开始，中间为AI生成的话题内容，后者标记内容结束，自定义时必须保留。
                      </Typography.Text>
                    </div>
                  }
                >
                  <QuestionCircleOutlined style={{ color: "#8c8c8c", cursor: "pointer" }} />
                </Popover>
              </Space>
            }
            rules={[
              { required: true, message: "请输入内容拆分规则" },
              {
                validator: (_, value?: string) =>
                  value?.includes("${block_start}") && value?.includes("${block_end}")
                    ? Promise.resolve()
                    : Promise.reject(new Error("内容拆分规则必须同时包含 ${block_start} 和 ${block_end}"))
              }
            ]}
          >
            <Input.TextArea autoSize={{ minRows: 8, maxRows: 16 }} />
          </Form.Item>
          <Space style={{ marginTop: -12, marginBottom: 16 }}>
            <Button type="link" onClick={() => form.setFieldValue("image_split_prompt", DEFAULT_IMAGE_SPLIT_PROMPT)}>
              恢复默认
            </Button>
          </Space>
        </>
      ) : null}
      {htmlEngineEnabled ? (
        <Typography.Text type="secondary" style={{ display: "block", marginTop: -8, marginBottom: 16 }}>
          本地 HTML 引擎已开启：整卡由 HTML 排版渲染，图片比例 / 分辨率不适用；出卡时自动产出小红书 3:4 分页图（2160x2880，与整卡同目录 pages/ 下）。
        </Typography.Text>
      ) : (
        <>
          <Form.Item
            name="image_aspect_ratio"
            label="图片比例"
            tooltip="自适应由图片接口决定；指定比例后，系统会结合分辨率换算为实际像素尺寸。"
            rules={[{ required: true, message: "请选择图片比例" }]}
          >
            <Select
              options={[
                { label: "自适应", value: "auto" },
                { label: "方图 1:1", value: "1:1" },
                { label: "横版 3:2", value: "3:2" },
                { label: "竖版 2:3", value: "2:3" },
                { label: "竖屏 9:16", value: "9:16" }
              ]}
            />
          </Form.Item>
          <Form.Item
            name="image_resolution"
            label="分辨率"
            tooltip="分辨率越高，生成时间、接口费用和飞书上传体积通常越大；最终是否支持由图片模型供应商决定。"
            rules={[{ required: true, message: "请选择分辨率" }]}
          >
            <Select
              options={[
                { label: "自适应", value: "auto" },
                { label: "1K", value: "1k" },
                { label: "2K", value: "2k" },
                { label: "4K", value: "4k" }
              ]}
            />
          </Form.Item>
        </>
      )}
      <Form.Item
        name="max_image_count"
        label="单次最多生成图片"
        tooltip="在调用图片接口前校验。识别出的内容超过上限时，本次作业直接失败，避免意外产生过多费用。"
        rules={[{ required: true, message: "请输入单次最多生成图片数" }]}
      >
        <InputNumber min={1} max={20} style={{ width: "100%" }} />
      </Form.Item>
    </>
  );
}

export default ImageCardSection;
