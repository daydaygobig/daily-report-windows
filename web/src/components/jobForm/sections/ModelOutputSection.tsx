/**
 * 备份模型返回结果分区（含 ima 同步配置）。从 JobFormModal 拆出，逻辑原样搬移。
 */
import { Button, Form, Input, InputNumber, Select, Switch, Typography } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import type { ImaResources } from "../useImaResources";
import { getTemplateTooltip, renderTemplateExample } from "../constants";

const { Text } = Typography;

function ModelOutputSection({ ima }: { ima: ImaResources }) {
  const form = Form.useFormInstance();
  const modelOutputBackupEnabled = Form.useWatch("model_output_backup_enabled", form);
  const imaSyncEnabled = Form.useWatch("ima_sync_enabled", form);
  const imaUseDefaultAccount = Form.useWatch("ima_use_default_account", form);
  const imaAccountId = Form.useWatch("ima_account_id", form);
  const imaUseDefaultTarget = Form.useWatch("ima_use_default_target", form);
  const imaTargetType = Form.useWatch("ima_target_type", form);
  const imaKnowledgeBaseId = Form.useWatch("ima_knowledge_base_id", form);
  const isWeeklyReport = Form.useWatch("schedule_type", form) === "weekly_report";
  const effectiveImaAccountId = imaUseDefaultAccount ? ima.defaultImaAccountId : imaAccountId;
  const imaTargetActiveView = modelOutputBackupEnabled && imaSyncEnabled;

  return (
    <>
      <Form.Item
        name="model_output_backup_enabled"
        label="备份模型返回结果"
        valuePropName="checked"
        tooltip="开启后会将模型原始输出另存为 Markdown 或 TXT 文件。"
      >
        <Switch />
      </Form.Item>
      {modelOutputBackupEnabled ? (
        <>
          <Form.Item
            name="model_output_path"
            label="保存路径"
            tooltip="相对路径将基于本地备份目录（默认 backups/model_outputs），路径会被保存方便下次使用。"
            extra="示例：model_outputs/测试群 或 /Users/me/reports/model_outputs"
          >
            <Input placeholder="例如：model_outputs/测试群" />
          </Form.Item>
          <Form.Item
            name="model_output_formats"
            label="文件格式"
            rules={[{ required: true, message: "请选择文件格式" }]}
          >
            <Select
              mode="multiple"
              placeholder="请选择格式（可多选）"
              options={[
                { label: "Markdown (.md)", value: "md" },
                { label: "纯文本 (.txt)", value: "txt" }
              ]}
            />
          </Form.Item>
          <Form.Item
            name="model_output_filename_template"
            label="文件命名模板"
            tooltip={getTemplateTooltip()}
            extra={renderTemplateExample("示例：模型输出_{week_start}_{week_end} → 模型输出_2025-11-03_2025-11-09.md")}
          >
            <Input placeholder="模型输出_{YYYY-MM-DD}" />
          </Form.Item>
          {!isWeeklyReport ? (
            <Form.Item
              name="model_output_filename_date_offset_days"
              label="文件名日期参数偏移（天）"
              tooltip="基准为作业执行完成时间（与 GitHub 部署一致），-1 表示将文件名日期定位到前一天。"
            >
              <InputNumber min={-7} max={7} style={{ width: "100%" }} />
            </Form.Item>
          ) : null}
          <Form.Item
            name="ima_sync_enabled"
            label="同步到 ima"
            valuePropName="checked"
            tooltip="这是新增的附加同步动作。默认关闭；同步失败不会影响原有作业成功状态。"
          >
            <Switch />
          </Form.Item>
          {imaTargetActiveView ? (
            <>
              <Form.Item
                name="ima_use_default_account"
                label="使用默认ima账号"
                valuePropName="checked"
                tooltip="开启后使用“ima账号管理/ima知识库同步设置”里的默认账号；关闭后可为当前作业指定单独的 ima 账号。"
              >
                <Switch
                  onChange={() => {
                    form.setFieldsValue({
                      ima_account_id: undefined,
                      ima_note_folder_id: undefined,
                      ima_knowledge_base_id: undefined,
                      ima_knowledge_folder_id: "root"
                    });
                  }}
                />
              </Form.Item>
              {!imaUseDefaultAccount ? (
                <Form.Item
                  name="ima_account_id"
                  label="ima账号"
                  rules={[{ required: true, message: "请选择 ima 账号" }]}
                >
                  <Select
                    allowClear
                    showSearch
                    placeholder="请选择要使用的 ima 账号"
                    options={ima.imaAccountOptions}
                    optionFilterProp="label"
                    onChange={(value) => {
                      form.setFieldsValue({
                        ima_account_id: value,
                        ima_note_folder_id: undefined,
                        ima_knowledge_base_id: undefined,
                        ima_knowledge_folder_id: "root"
                      });
                      void ima.loadImaNoteFolders(value);
                      void ima.loadImaKnowledgeBases(value);
                      ima.setImaKnowledgeFolders([{ label: "根目录", value: "root" }]);
                    }}
                  />
                </Form.Item>
              ) : (
                <Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
                  {ima.defaultImaAccountId
                    ? "当前作业会使用系统默认 ima 账号。若需改用其他账号，可关闭“使用默认 ima 账号”后单独指定。"
                    : "当前还没有配置默认 ima 账号。若继续使用默认账号模式，运行时会因为缺少默认账号而无法同步。"}
                </Text>
              )}
              <Form.Item
                name="ima_use_default_target"
                label="使用默认 ima 配置"
                valuePropName="checked"
                tooltip="开启后使用当前账号在“ima账号管理”里配置的默认目标和默认文件夹。"
              >
                <Switch />
              </Form.Item>
              {!imaUseDefaultTarget ? (
                <>
                  <Form.Item
                    name="ima_target_type"
                    label="同步目标类型"
                    rules={[{ required: true, message: "请选择同步目标类型" }]}
                  >
                    <Select
                      options={[
                        { label: "ima 笔记", value: "note" },
                        { label: "ima 知识库", value: "knowledge_base" }
                      ]}
                    />
                  </Form.Item>
                  {imaTargetType === "note" ? (
                    <Form.Item
                      name="ima_note_folder_id"
                      label="目标笔记本"
                      rules={[{ required: true, message: "请选择目标笔记本" }]}
                    >
                      <Select
                        allowClear
                        showSearch
                        placeholder={effectiveImaAccountId ? "请选择目标笔记本" : "请先选择 ima 账号"}
                        options={ima.imaNoteFolderOptions}
                        optionFilterProp="label"
                        disabled={!effectiveImaAccountId}
                        loading={ima.imaLoading.noteFolders}
                        dropdownRender={(menu) => (
                          <>
                            {menu}
                            <div style={{ padding: 8 }}>
                              <Button
                                type="link"
                                block
                                icon={<ReloadOutlined />}
                                disabled={!effectiveImaAccountId}
                                onClick={() => void ima.loadImaNoteFolders(effectiveImaAccountId)}
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
                        name="ima_knowledge_base_id"
                        label="目标知识库"
                        rules={[{ required: true, message: "请选择目标知识库" }]}
                      >
                        <Select
                          allowClear
                          showSearch
                          placeholder={effectiveImaAccountId ? "请选择目标知识库" : "请先选择 ima 账号"}
                          options={ima.imaKnowledgeBaseOptions}
                          optionFilterProp="label"
                          disabled={!effectiveImaAccountId}
                          loading={ima.imaLoading.knowledgeBases}
                          onChange={() => form.setFieldValue("ima_knowledge_folder_id", "root")}
                          dropdownRender={(menu) => (
                            <>
                              {menu}
                              <div style={{ padding: 8 }}>
                                <Button
                                  type="link"
                                  block
                                  icon={<ReloadOutlined />}
                                  disabled={!effectiveImaAccountId}
                                  onClick={() => void ima.loadImaKnowledgeBases(effectiveImaAccountId)}
                                >
                                  刷新知识库
                                </Button>
                              </div>
                            </>
                          )}
                        />
                      </Form.Item>
                      <Form.Item name="ima_knowledge_folder_id" label="目标文件夹">
                        <Select
                          allowClear
                          showSearch
                          placeholder={effectiveImaAccountId ? "请选择目标文件夹" : "请先选择 ima 账号"}
                          options={ima.imaKnowledgeFolderOptions}
                          optionFilterProp="label"
                          disabled={!effectiveImaAccountId || !imaKnowledgeBaseId}
                          loading={ima.imaLoading.knowledgeFolders}
                          dropdownRender={(menu) => (
                            <>
                              {menu}
                              <div style={{ padding: 8 }}>
                                <Button
                                  type="link"
                                  block
                                  icon={<ReloadOutlined />}
                                  disabled={!effectiveImaAccountId || !imaKnowledgeBaseId}
                                  onClick={() => void ima.loadImaKnowledgeFolders(imaKnowledgeBaseId, effectiveImaAccountId)}
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
                </>
              ) : (
                <Text type="secondary">
                  将使用“ima知识库同步设置”页面里的默认目标和默认目录。未配置或同步失败都不会影响现有作业主流程。
                </Text>
              )}
            </>
          ) : null}
        </>
      ) : null}
    </>
  );
}

export default ModelOutputSection;
