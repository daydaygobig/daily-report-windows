/**
 * 话题卡片配置分区。从 JobFormModal 拆出，逻辑原样搬移。
 */
import { Form, Input, InputNumber, Select, Switch } from "antd";

function TopicCardSection() {
  const form = Form.useFormInstance();
  const topicTextLayout = Form.useWatch("topic_text_layout", form);
  const topicImageEnabled = Form.useWatch("topic_image_enabled", form);
  const topicImageLayout = Form.useWatch("topic_image_layout", form);
  const topicImageBackupEnabled = Form.useWatch("topic_image_backup_enabled", form);

  return (
    <>
      <Form.Item
        name="topic_text_layout"
        label="文字布局"
        tooltip="控制飞书文字消息怎么发：逐话题就是一张卡一条消息；合并就是多个话题放在一条消息里；自动会按阈值决定。"
        rules={[{ required: true, message: "请选择文字布局" }]}
      >
        <Select
          options={[
            { label: "逐话题", value: "per_topic" },
            { label: "合并", value: "merged" },
            { label: "自动", value: "auto" }
          ]}
        />
      </Form.Item>
      {topicTextLayout === "auto" ? (
        <Form.Item
          name="topic_text_merge_threshold"
          label="文字自动合并阈值"
          tooltip="话题数量超过这个值时，文字消息自动合并成一条。"
          rules={[{ required: true, message: "请输入文字自动合并阈值" }]}
        >
          <InputNumber min={1} max={20} style={{ width: "100%" }} />
        </Form.Item>
      ) : null}
      <Form.Item
        name="topic_image_enabled"
        label="图片推送"
        valuePropName="checked"
        tooltip="开启后会把同一份话题卡片数据渲染成 PNG 图片，再上传到飞书并用当前 Webhook 推送图片。"
      >
        <Switch />
      </Form.Item>
      {topicImageEnabled ? (
        <>
          <Form.Item
            name="topic_image_layout"
            label="图片布局"
            tooltip="单张表示每个话题一张图；合集表示多个话题合成一张长图；自动会按阈值决定。"
            rules={[{ required: true, message: "请选择图片布局" }]}
          >
            <Select
              options={[
                { label: "单张", value: "single" },
                { label: "合集", value: "collection" },
                { label: "自动", value: "auto" }
              ]}
            />
          </Form.Item>
          {topicImageLayout === "auto" ? (
            <Form.Item
              name="topic_image_merge_threshold"
              label="图片自动合集阈值"
              tooltip="话题数量超过这个值时，图片自动合成一张长图。"
              rules={[{ required: true, message: "请输入图片自动合集阈值" }]}
            >
              <InputNumber min={1} max={20} style={{ width: "100%" }} />
            </Form.Item>
          ) : null}
          <Form.Item
            name="topic_image_backup_enabled"
            label="本地保存"
            valuePropName="checked"
            tooltip="开启后每次推送时，会把卡片 PNG 图片和对应 Markdown 文本自动保存到本地文件夹（按日期分目录）。"
          >
            <Switch />
          </Form.Item>
          {topicImageBackupEnabled ? (
            <Form.Item
              name="topic_image_backup_path"
              label="保存路径"
              tooltip="相对路径将基于本地备份目录（默认 backups/topic_cards），路径会被保存方便下次使用。"
              extra="示例：topic_cards/案例图 或 D:/自媒体/职场案例卡片"
            >
              <Input placeholder="留空则保存到 backups/topic_cards/日期/" />
            </Form.Item>
          ) : null}
        </>
      ) : null}
    </>
  );
}

export default TopicCardSection;
