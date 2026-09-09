import { useEffect, useMemo, useState } from "react";
import { Button, Card, Form, Input, InputNumber, Select, Space, Switch, Typography, message } from "antd";
import { downloadSystemLog } from "../services/system";
import { getErrorMessage } from "../services/apiClient";
import {
  fetchChatRecordSettings,
  testChatRecordSettings,
  updateChatRecordSettings,
  type ChatRecordProvider,
  type ChatRecordSettings,
  type ChatRecordSettingsPayload
} from "../services/chatRecords";

type SettingsFormValues = ChatRecordSettingsPayload & {
  weflow_token?: string;
};

function toFormValues(settings: ChatRecordSettings): SettingsFormValues {
  return {
    provider: settings.provider,
    chatlog_base_url: settings.chatlog_base_url,
    chatlog_timeout_sec: settings.chatlog_timeout_sec,
    chatlog_decrypt_before_fetch: settings.chatlog_decrypt_before_fetch,
    chatlog_decrypt_cache_enabled: settings.chatlog_decrypt_cache_enabled,
    chatlog_decrypt_timeout_sec: settings.chatlog_decrypt_timeout_sec,
    chatlog_decrypt_cache_buffer_sec: settings.chatlog_decrypt_cache_buffer_sec,
    chatlog_work_dir: settings.chatlog_work_dir,
    weflow_base_url: settings.weflow_base_url,
    weflow_page_limit: settings.weflow_page_limit,
    weflow_page_timeout_sec: settings.weflow_page_timeout_sec,
    weflow_empty_page_retry: settings.weflow_empty_page_retry,
    weflow_token: undefined
  };
}

function normalizePayload(values: SettingsFormValues): ChatRecordSettingsPayload {
  const token = values.weflow_token?.trim();
  const payload: ChatRecordSettingsPayload = {
    provider: values.provider,
    chatlog_base_url: values.chatlog_base_url,
    chatlog_timeout_sec: values.chatlog_timeout_sec,
    chatlog_decrypt_before_fetch: values.chatlog_decrypt_before_fetch,
    chatlog_decrypt_cache_enabled: values.chatlog_decrypt_cache_enabled,
    chatlog_decrypt_timeout_sec: values.chatlog_decrypt_timeout_sec,
    chatlog_decrypt_cache_buffer_sec: values.chatlog_decrypt_cache_buffer_sec,
    chatlog_work_dir: values.chatlog_work_dir,
    weflow_base_url: values.weflow_base_url,
    weflow_page_limit: values.weflow_page_limit,
    weflow_page_timeout_sec: values.weflow_page_timeout_sec,
    weflow_empty_page_retry: values.weflow_empty_page_retry
  };
  if (token) {
    payload.weflow_token = token;
  }
  return payload;
}

function SettingsPage() {
  const [form] = Form.useForm<SettingsFormValues>();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [hasWeFlowToken, setHasWeFlowToken] = useState(false);
  const provider = Form.useWatch("provider", form) as ChatRecordProvider | undefined;
  const isChatlog = (provider ?? "chatlog") === "chatlog";

  const providerLabel = useMemo(() => (isChatlog ? "ChatLog" : "WeFlow"), [isChatlog]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const settings = await fetchChatRecordSettings();
        setHasWeFlowToken(settings.has_weflow_token);
        form.setFieldsValue(toFormValues(settings));
      } catch (error) {
        message.error(getErrorMessage(error));
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [form]);

  const handleSubmit = async (values: SettingsFormValues) => {
    setSaving(true);
    try {
      const updated = await updateChatRecordSettings(normalizePayload(values));
      setHasWeFlowToken(updated.has_weflow_token);
      form.setFieldsValue({ ...toFormValues(updated), weflow_token: undefined });
      message.success("聊天记录接口配置已保存");
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    try {
      setTesting(true);
      const values = await form.validateFields();
      const result = await testChatRecordSettings(normalizePayload(values));
      if (result.ok) {
        message.success(`${providerLabel} 测试通过`);
      } else {
        message.error(result.message);
      }
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setTesting(false);
    }
  };

  const handleDownloadLog = async () => {
    try {
      const blob = await downloadSystemLog("backend");
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "backend.log";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  };

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card loading={loading} title="聊天记录接口">
        <Form<SettingsFormValues>
          layout="vertical"
          form={form}
          onFinish={handleSubmit}
          initialValues={{
            provider: "chatlog",
            chatlog_base_url: "http://127.0.0.1:5030",
            chatlog_timeout_sec: 60,
            chatlog_decrypt_before_fetch: true,
            chatlog_decrypt_cache_enabled: true,
            chatlog_decrypt_timeout_sec: 300,
            chatlog_decrypt_cache_buffer_sec: 0,
            chatlog_work_dir: "C:\\Users\\你的用户名\\Documents\\chatlog",
            weflow_base_url: "http://127.0.0.1:5031",
            weflow_page_limit: 1000,
            weflow_page_timeout_sec: 180,
            weflow_empty_page_retry: 2
          }}
        >
          <Form.Item
            label="聊天记录接口"
            name="provider"
            tooltip="选择日报系统从哪里读取聊天记录。ChatLog 是旧方案，WeFlow 是低写入新方案。"
            rules={[{ required: true, message: "请选择聊天记录接口" }]}
          >
            <Select
              options={[
                { label: "ChatLog", value: "chatlog" },
                { label: "WeFlow", value: "weflow" }
              ]}
            />
          </Form.Item>

          {isChatlog ? (
            <>
              <Form.Item
                label="ChatLog 地址"
                name="chatlog_base_url"
                tooltip="ChatLog HTTP 服务地址，通常是 http://127.0.0.1:5030。"
                rules={[{ required: true, message: "请输入 ChatLog 地址" }]}
              >
                <Input placeholder="http://127.0.0.1:5030" />
              </Form.Item>
              <Form.Item
                label="拉数据前自动解密"
                name="chatlog_decrypt_before_fetch"
                valuePropName="checked"
                tooltip="每次拉聊天记录前自动触发 chatlog 解密，确保数据最新。"
              >
                <Switch />
              </Form.Item>
              <Form.Item
                label="智能跳过重复解密"
                name="chatlog_decrypt_cache_enabled"
                valuePropName="checked"
                tooltip="根据本次查询结束时间，检查当前已解密数据是否已经覆盖；如果已覆盖，就跳过解密，避免重复写入。"
              >
                <Switch />
              </Form.Item>
              <Form.Item
                label="解密超时时间（秒）"
                name="chatlog_decrypt_timeout_sec"
                tooltip="解密接口超时时间，数据量大时建议设长一些，默认 300 秒。"
                rules={[{ required: true, message: "请输入解密超时时间" }]}
              >
                <InputNumber min={1} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item
                label="解密缓存缓冲秒数"
                name="chatlog_decrypt_cache_buffer_sec"
                tooltip="判断已解密数据是否覆盖查询窗口时额外增加的缓冲秒数，默认 0；如发现边界消息延迟，可改为 30 或 60。"
                rules={[{ required: true, message: "请输入解密缓存缓冲秒数" }]}
              >
                <InputNumber min={0} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item
                label="ChatLog 工作目录"
                name="chatlog_work_dir"
                tooltip="用于估算 ChatLog 解密库写入量。只读取文件大小和修改时间，不读取聊天正文，不触碰微信进程。"
                rules={[{ required: true, message: "请输入 ChatLog 工作目录" }]}
              >
                <Input placeholder="C:\\Users\\你的用户名\\Documents\\chatlog" />
              </Form.Item>
              <Form.Item
                label="ChatLog 请求超时（秒）"
                name="chatlog_timeout_sec"
                tooltip="调用 ChatLog 查询接口的超时时间。"
                rules={[{ required: true, message: "请输入 ChatLog 请求超时" }]}
              >
                <InputNumber min={1} style={{ width: "100%" }} />
              </Form.Item>
            </>
          ) : (
            <>
              <Form.Item
                label="WeFlow 地址"
                name="weflow_base_url"
                tooltip="WeFlow HTTP API 地址，通常是 http://127.0.0.1:5031。"
                rules={[{ required: true, message: "请输入 WeFlow 地址" }]}
              >
                <Input placeholder="http://127.0.0.1:5031" />
              </Form.Item>
              <Form.Item
                label="WeFlow Token"
                name="weflow_token"
                tooltip="WeFlow API Token，默认遮住；点击小眼睛显示明文，再次点击隐藏。保存后再次打开页面默认隐藏。"
                extra={hasWeFlowToken ? "已保存 Token；留空表示继续使用已保存的 Token。" : "尚未保存 Token，首次切换 WeFlow 时必须填写。"}
                rules={[{ required: !hasWeFlowToken, message: "请输入 WeFlow Token" }]}
              >
                <Input.Password placeholder="输入 WeFlow API Token" visibilityToggle />
              </Form.Item>
              <Form.Item
                label="每页拉取条数"
                name="weflow_page_limit"
                tooltip="WeFlow 分页读取消息数量，建议 500 到 1000。"
                rules={[{ required: true, message: "请输入每页拉取条数" }]}
              >
                <InputNumber min={1} max={10000} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item
                label="单页超时时间（秒）"
                name="weflow_page_timeout_sec"
                tooltip="WeFlow 单页请求超时时间，消息多时建议 180 秒。"
                rules={[{ required: true, message: "请输入单页超时时间" }]}
              >
                <InputNumber min={1} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item
                label="空页重试次数"
                name="weflow_empty_page_retry"
                tooltip="WeFlow 偶发返回空页时的重试次数，默认 2。"
                rules={[{ required: true, message: "请输入空页重试次数" }]}
              >
                <InputNumber min={0} max={10} style={{ width: "100%" }} />
              </Form.Item>
              <Typography.Paragraph type="secondary">
                WeFlow 模式固定不启用媒体导出，不读取图片、语音、视频文件，只把媒体消息转成占位符。
              </Typography.Paragraph>
            </>
          )}

          <Form.Item>
            <Space>
              <Button onClick={handleTest} loading={testing}>
                测试 {providerLabel}
              </Button>
              <Button type="primary" htmlType="submit" loading={saving}>
                保存配置
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>

      <Card title="日志导出">
        <Button onClick={handleDownloadLog}>下载后端日志</Button>
      </Card>
    </Space>
  );
}

export default SettingsPage;
