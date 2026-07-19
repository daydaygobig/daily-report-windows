import { useEffect, useMemo, useState } from "react";
import { Button, Form, Input, Modal, Radio, Select, Space, Switch, Typography, message } from "antd";
import type { GithubConfig, GithubRepoInfo } from "../services/githubConfigs";
import { testGithubToken } from "../services/githubConfigs";

type GithubConfigFormValues = {
  name: string;
  owner: string;
  repo: string;
  branch: string;
  path_prefix?: string;
  filename_template: string;
  pages_base_url?: string;
  view_url_mode: "github_pages" | "custom_template";
  view_url_template?: string;
  is_default: boolean;
  description?: string;
  token?: string;
};

type GithubConfigFormModalProps = {
  open: boolean;
  initialValues?: GithubConfig | null;
  confirmLoading?: boolean;
  onCancel: () => void;
  onSubmit: (values: GithubConfigFormValues) => Promise<void> | void;
};

const DEFAULT_TEMPLATE = "微信群日报_{YYYY-MM-DD}.html";
const { Text } = Typography;

function GithubConfigFormModal({ open, initialValues, confirmLoading, onCancel, onSubmit }: GithubConfigFormModalProps) {
  const [form] = Form.useForm<GithubConfigFormValues>();
  const [testing, setTesting] = useState(false);
  const [repoOptions, setRepoOptions] = useState<GithubRepoInfo[]>([]);
  const viewUrlMode = Form.useWatch("view_url_mode", form);

  const isEditMode = Boolean(initialValues);

  useEffect(() => {
    if (!open) {
      return;
    }
    if (initialValues) {
      form.setFieldsValue({
        name: initialValues.name,
        owner: initialValues.owner,
        repo: initialValues.repo,
        branch: initialValues.branch,
        path_prefix: initialValues.path_prefix ?? undefined,
        filename_template: initialValues.filename_template ?? DEFAULT_TEMPLATE,
        pages_base_url: initialValues.pages_base_url ?? undefined,
        view_url_mode: initialValues.view_url_mode ?? "github_pages",
        view_url_template: initialValues.view_url_template ?? undefined,
        is_default: initialValues.is_default,
        description: initialValues.description ?? undefined,
        token: initialValues.token ?? undefined
      });
    } else {
      form.resetFields();
      form.setFieldsValue({
        branch: "main",
        filename_template: DEFAULT_TEMPLATE,
        view_url_mode: "github_pages",
        is_default: false
      });
    }
    setRepoOptions([]);
  }, [open, initialValues, form]);

  const handleTestToken = async () => {
    const token = form.getFieldValue("token");
    if (!token && !isEditMode) {
      message.warning("请先填写 Token");
      return;
    }
    try {
      setTesting(true);
      const result = await testGithubToken(token || "", form.getFieldValue("owner"));
      setRepoOptions(result.repos ?? []);
      if (result.repos?.length) {
        message.success(`Token 有效，可访问 ${result.repos.length} 个仓库`);
      } else {
        message.info("Token 校验成功，但未返回仓库列表，请确认权限");
      }
    } catch (error) {
      message.error((error as Error).message || "Token 校验失败");
    } finally {
      setTesting(false);
    }
  };

  const repoSelectOptions = useMemo(
    () =>
      repoOptions.map((repo) => ({
        label: `${repo.full_name}（默认分支：${repo.default_branch}）`,
        value: repo.full_name,
        repo
      })),
    [repoOptions]
  );

  const applyRepoSelection = (fullName: string) => {
    const selected = repoOptions.find((item) => item.full_name === fullName);
    if (!selected) {
      return;
    }
    form.setFieldsValue({
      owner: selected.owner,
      repo: selected.repo,
      branch: selected.default_branch,
      pages_base_url: selected.pages_base_url
    });
  };

  const handleFinish = async (values: GithubConfigFormValues) => {
    await onSubmit({
      ...values,
      token: values.token?.trim() || (isEditMode ? undefined : values.token)
    });
    if (!isEditMode) {
      form.resetFields();
      setRepoOptions([]);
    }
  };

  const showGuide = () => {
    Modal.info({
      title: "配置说明",
      width: 520,
      content: (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div>
            <strong>1. 找到 Developer settings（个人设置里）</strong>
            <ol style={{ paddingLeft: 18, marginTop: 4 }}>
              <li>登录 GitHub，点击右上角头像 → Settings。</li>
              <li>在左侧菜单滑到最底部，点击「&lt;&gt; Developer settings」。</li>
              <li>进入后选择「Personal access tokens」→「Fine-grained tokens」。</li>
            </ol>
          </div>
          <div>
            <strong>2. 生成 Fine-grained PAT</strong>
            <ol style={{ paddingLeft: 18, marginTop: 4 }}>
              <li>点击「Generate new token」，填一个 Token 名称（例：日报部署）。</li>
              <li>Repository access 选择「Only select repositories」，勾选要部署的仓库。</li>
              <li>在 Repository permissions 中，Contents 选「Read and write」，Metadata 选「Read-only」。</li>
              <li>点击页面底部「Generate token」，立即复制出现的 github_pat 开头的字符串（只显示一次）。</li>
            </ol>
          </div>
          <div>
            <strong>3. 在本表单中使用</strong>
            <ol style={{ paddingLeft: 18, marginTop: 4 }}>
              <li>把复制的 Token 粘贴到「GitHub Token」，点击「测试 Token」。</li>
              <li>测试成功后，在「Token 可访问仓库」下拉中选择刚授权的仓库，下方会自动填入 owner/repo/branch。</li>
              <li>文件名模板支持 {"{YYYY-MM-DD}"}/{"{YYYYMMDD}"}/{"{YYYY-MM-DD HH:MM}"} 以及 {"{job_id}"}/{"{task_id}"}，例如 <code>群聊日报_{"{YYYY-MM-DD}"}.html</code>。</li>
              <li>如果执行历史需要跳转到自定义域，使用「查看页面链接」配置；它不影响 GitHub 上传路径。</li>
            </ol>
          </div>
        </div>
      )
    });
  };

  return (
    <Modal
      open={open}
      title={isEditMode ? "编辑 GitHub 配置" : "新增 GitHub 配置"}
      onCancel={() => {
        form.resetFields();
        onCancel();
      }}
      onOk={() => form.submit()}
      confirmLoading={confirmLoading}
      okText="保存"
    >
      <Form<GithubConfigFormValues> layout="vertical" form={form} onFinish={handleFinish}>
        <div style={{ textAlign: "right", marginBottom: 8 }}>
          <Button type="link" size="small" onClick={showGuide}>
            查看配置说明
          </Button>
        </div>
        <Form.Item
          name="name"
          label="配置名称"
          rules={[
            { required: true, message: "请输入配置名称" },
            { max: 120, message: "名称不超过 120 个字符" }
          ]}
        >
          <Input placeholder="如：日报-主仓库" />
        </Form.Item>
        <Form.Item
          name="token"
          label="GitHub Token"
          tooltip="仅用于 API 调用验证，不会在前端回显。编辑模式下留空表示沿用旧 Token。"
          rules={isEditMode ? [] : [{ required: true, message: "请输入 Token" }]}
        >
          <Input.Password placeholder={isEditMode ? "已从数据库加载，可点击小眼睛查看" : "输入 Fine-grained PAT"} />
        </Form.Item>
        <Form.Item label="Token 可访问仓库">
          <Space style={{ width: "100%" }}>
            <Button onClick={handleTestToken} loading={testing}>
              测试 Token
            </Button>
            <Select
              allowClear
              placeholder="选择测试返回的仓库自动填充"
              options={repoSelectOptions}
              onChange={(value) => value && applyRepoSelection(value)}
              style={{ flex: 1 }}
              showSearch
              optionFilterProp="label"
            />
          </Space>
        </Form.Item>
        <Form.Item
          name="owner"
          label="仓库所有者"
          rules={[{ required: true, message: "请输入 owner" }]}
        >
          <Input placeholder="GitHub 用户或组织" />
        </Form.Item>
        <Form.Item
          name="repo"
          label="仓库名称"
          rules={[{ required: true, message: "请输入 repo" }]}
        >
          <Input placeholder="仓库名，例如 daily-reports" />
        </Form.Item>
        <Form.Item name="branch" label="分支">
          <Input placeholder="默认 main，可根据 Pages 设置填写 gh-pages 等" />
        </Form.Item>
        <Form.Item name="path_prefix" label="路径前缀" tooltip="可选，例如 reports/task_16（无需以 / 开头）">
          <Input placeholder="可选，留空表示仓库根目录" />
        </Form.Item>
        <Form.Item name="pages_base_url" label="Pages 基础链接" tooltip="可选，默认为 https://owner.github.io/repo/">
          <Input placeholder="https://<owner>.github.io/<repo>/" />
        </Form.Item>
        <Form.Item
          name="view_url_mode"
          label="查看页面链接"
          tooltip="控制执行历史中“查看页面”的跳转地址；不影响文件上传到 GitHub 的仓库路径。自定义模板里的日期会跟作业的 GitHub 文件名日期参数偏移联动。"
        >
          <Radio.Group
            options={[
              { label: "使用默认 GitHub Pages 链接", value: "github_pages" },
              { label: "使用自定义链接模板", value: "custom_template" }
            ]}
          />
        </Form.Item>
        {viewUrlMode === "custom_template" ? (
          <Form.Item
            name="view_url_template"
            label="自定义查看页面链接模板"
            tooltip="可不写 https://，系统会自动补齐。支持日期占位符、{filename}、{repo_path}、{job_id}、{task_id}、{execution_id}、{job_name}、{task_name}。"
            extra={
              <Text type="secondary">
                示例：xh.xinjianhub.cn/星火群日报_{"{YYYY-MM-DD}"}.html
              </Text>
            }
            rules={[{ required: true, message: "请输入自定义查看页面链接模板" }]}
          >
            <Input placeholder="xh.xinjianhub.cn/星火群日报_{YYYY-MM-DD}.html" />
          </Form.Item>
        ) : null}
        <Form.Item name="is_default" label="设为默认" valuePropName="checked">
          <Switch />
        </Form.Item>
        <Form.Item name="description" label="备注">
          <Input.TextArea placeholder="可选备注" autoSize={{ minRows: 2, maxRows: 4 }} />
        </Form.Item>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
          测试成功后，可在“任务作业”表单中直接选择此配置。
        </Typography.Paragraph>
      </Form>
    </Modal>
  );
}

export default GithubConfigFormModal;
