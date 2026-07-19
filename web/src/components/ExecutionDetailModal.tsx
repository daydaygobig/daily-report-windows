import { useMemo, type ReactNode } from "react";
import { Button, Collapse, Descriptions, Modal, Space, Tag, Timeline, Tooltip, Typography } from "antd";
import type { Execution } from "../services/executions";
import { formatDateTime } from "../utils/datetime";

const { Paragraph, Text } = Typography;

type ExecutionDetailModalProps = {
  execution: Execution | null;
  onClose: () => void;
  onOpenDeployRecord: (recordId: number) => void;
  onOpenImaSyncRecord: (executionId: number, batchId?: string | null) => void;
};

const formatDuration = (ms?: number | null): string => {
  if (typeof ms !== "number" || ms < 0) {
    return "-";
  }
  const totalSeconds = Math.round(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  const parts: string[] = [];
  if (minutes) parts.push(`${minutes}m`);
  parts.push(`${seconds}s`);
  return `${parts.join("")}（${ms}ms）`;
};

const formatBytes = (value?: number | null): string => {
  if (value === null || value === undefined) {
    return "-";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  let amount = Number(value) || 0;
  for (const unit of units) {
    if (amount < 1024 || unit === units[units.length - 1]) {
      return unit === "B" ? `${Math.round(amount)} B` : `${amount.toFixed(2)} ${unit}`;
    }
    amount /= 1024;
  }
  return `${value} B`;
};

const renderImaStatusTag = (status?: string | null) => {
  switch (status) {
    case "success":
      return <Tag color="green">同步成功</Tag>;
    case "failed":
      return <Tag color="red">同步失败</Tag>;
    case "skipped":
      return <Tag>已跳过</Tag>;
    case "partial":
      return <Tag color="orange">部分成功</Tag>;
    default:
      return <Tag>未开启</Tag>;
  }
};

const isGithubArtifact = (item: { type?: string }) => item.type === "github" || item.type === "github_message_stats";

const githubArtifactTypeLabel = (type?: string) => {
  if (type === "github_message_stats" || type === "message_stats") {
    return "消息统计";
  }
  return "HTML 日报";
};

type GithubArtifact = NonNullable<Execution["exported_files"]>[number];
type GithubDeploymentItem = NonNullable<Execution["github_deployments"]>[number];
type GithubFileLike = {
  github_file_url?: string | null;
  pages_url?: string | null;
  url?: string | null;
  repo_path?: string | null;
  path?: string | null;
  repo?: string | null;
  repo_full_name?: string | null;
  branch?: string | null;
};
type GithubUploadView = GithubFileLike & {
  key: string;
  type?: string | null;
  label?: string | null;
  status?: string | null;
  error_msg?: string | null;
  record_id?: number | null;
};

const decodeGithubUrl = (url?: string | null) => {
  if (!url) {
    return "";
  }
  try {
    return decodeURI(url);
  } catch {
    return url;
  }
};

const buildGithubFileUrl = (item: GithubFileLike) => {
  if (item.github_file_url) {
    return item.github_file_url;
  }
  const repoPath = item.repo_path || item.path;
  const repo = item.repo || item.repo_full_name;
  if (!repo || !repoPath) {
    return undefined;
  }
  const branch = item.branch || "main";
  return `https://github.com/${repo}/blob/${encodeURIComponent(branch)}/${repoPath
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/")}`;
};

const githubUploadStatusTag = (status?: string | null, error?: string | null) => {
  if (status === "success") {
    return <Tag color="green">部署成功</Tag>;
  }
  if (status === "failed") {
    return (
      <Tooltip title={error || "部署失败"}>
        <Tag color="red">部署失败</Tag>
      </Tooltip>
    );
  }
  if (status === "running") {
    return <Tag color="blue">部署中</Tag>;
  }
  return <Tag>未触发</Tag>;
};

const toUploadType = (artifactType?: string | null) => {
  if (artifactType === "message_stats") {
    return "github_message_stats";
  }
  if (artifactType === "html_report") {
    return "github";
  }
  return artifactType || "github";
};

const githubUploadKey = (item: GithubFileLike & { type?: string | null }) =>
  `${toUploadType(item.type)}:${item.github_file_url || item.repo_path || item.path || ""}`;

const ExecutionDetailModal = ({
  execution,
  onClose,
  onOpenDeployRecord,
  onOpenImaSyncRecord,
}: ExecutionDetailModalProps) => {
  const open = Boolean(execution);
  const data = execution;

  const promptContext = data?.prompt_context ?? null;
  const usageStats = data?.prompt_usage ?? null;
  const talkerList = promptContext?.talkers?.join("、") || data?.task_name || "-";
  const chatlogRange = promptContext?.chatlog_range || "-";
  const systemInstruction = promptContext?.system_instruction || promptContext?.system_prompt || "系统未追加额外指令";
  const taskPrompt = promptContext?.task_prompt || "可查看任务设置";
  const chunkInfo =
    promptContext && typeof promptContext.chunked === "boolean"
      ? promptContext.chunked
        ? `已启用分段发送（共 ${promptContext.chunk_count ?? "-"} 段，单段上限 ${promptContext.chunk_limit ?? "-"} 字符）`
        : "未启用分段发送"
      : undefined;

  const renderUsageBreakdown = (
    stats?: Record<string, number>,
    fallback?: number | null,
    summaryLabel?: string,
    unitSuffix = "",
  ) => {
    if (!stats && (fallback === null || fallback === undefined)) {
      return "-";
    }
    const rows = [
      { label: `${summaryLabel ?? ""}总计`, value: stats?.total ?? fallback ?? "-" },
      { label: "系统提示词", value: stats?.system ?? "-" },
      { label: "任务提示词", value: stats?.task ?? "-" },
      { label: "聊天记录", value: stats?.chatlog ?? "-" },
    ];
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        {rows.map((row) => (
          <Text key={row.label}>
            {row.label}：{typeof row.value === "number" ? `${row.value}${unitSuffix}` : row.value}
          </Text>
        ))}
      </div>
    );
  };

  const renderDeployDetail = () => {
    if (!data) {
      return "-";
    }
    const uploads: GithubUploadView[] =
      data.github_deployments?.map((item: GithubDeploymentItem) => ({
        key: `deployment-${item.id}`,
        type: toUploadType(item.artifact_type),
        label: item.artifact_label,
        status: item.status,
        error_msg: item.error_msg,
        record_id: item.id,
        repo_full_name: item.repo_full_name,
        branch: item.branch,
        repo_path: item.repo_path,
        pages_url: item.pages_url,
        github_file_url: item.github_file_url,
      })) ?? [];
    const existingUploadKeys = new Set(uploads.map(githubUploadKey));

    const githubArtifacts: GithubArtifact[] = data.exported_files?.filter(isGithubArtifact) ?? [];
    githubArtifacts.forEach((item, index) => {
      const uploadKey = githubUploadKey(item);
      const sameTypeExists = uploads.some((upload) => toUploadType(upload.type) === toUploadType(item.type));
      if (!existingUploadKeys.has(uploadKey) && !(item.type === "github" && sameTypeExists)) {
        uploads.push({
          key: `artifact-${item.type ?? "github"}-${index}`,
          type: item.type,
          label: item.label,
          status: item.deployment_status || "success",
          record_id: item.deployment_record_id,
          repo: item.repo,
          branch: item.branch,
          repo_path: item.repo_path || item.path,
          path: item.path,
          url: item.url,
          github_file_url: item.github_file_url,
        });
        existingUploadKeys.add(uploadKey);
      }
    });

    const hasHtmlArtifact = uploads.some((item) => toUploadType(item.type) === "github");
    if ((data.deploy_status && data.deploy_status !== "none") || data.deploy_repo_path || data.deploy_github_file_url) {
      if (!hasHtmlArtifact) {
        uploads.unshift({
          key: "html-deploy",
          type: "github",
          label: "HTML 日报",
          status: data.deploy_status,
          error_msg: data.deploy_error,
          record_id: data.deploy_record_id,
          repo_full_name: data.deploy_repo_full_name,
          branch: data.deploy_branch,
          repo_path: data.deploy_repo_path,
          pages_url: data.deploy_url,
          github_file_url: data.deploy_github_file_url,
        });
      }
    }

    if (uploads.length === 0) {
      return "未触发部署";
    }

    const renderGithubArtifactBlock = (item: GithubUploadView) => {
      const uploadType = toUploadType(item.type);
      const isHtml = uploadType === "github";
      const fileUrl = buildGithubFileUrl(item);
      const viewUrl = isHtml ? item.pages_url || item.url : undefined;
      return (
        <div
          key={item.key}
          style={{
            border: "1px solid #f0f0f0",
            borderRadius: 6,
            padding: "10px 12px",
            background: "#fafafa",
          }}
        >
          <Space direction="vertical" size={6} style={{ display: "flex" }}>
            <Space wrap size={8}>
              <Tag color={isHtml ? "blue" : "purple"}>{githubArtifactTypeLabel(uploadType)}</Tag>
              {githubUploadStatusTag(item.status, item.error_msg)}
              {item.record_id ? (
                <Button type="link" size="small" style={{ padding: 0 }} onClick={() => onOpenDeployRecord(item.record_id!)}>
                  查看记录
                </Button>
              ) : null}
              {viewUrl ? (
                <a href={viewUrl} target="_blank" rel="noreferrer">
                  查看页面
                </a>
              ) : null}
            </Space>
            {fileUrl ? (
              <a href={fileUrl} target="_blank" rel="noreferrer" style={{ wordBreak: "break-all" }}>
                {decodeGithubUrl(fileUrl)}
              </a>
            ) : item.repo_path || item.path ? (
              <Paragraph style={{ marginBottom: 0 }} copyable={{ text: item.repo_path || item.path || "" }}>
                {item.repo_path || item.path}
              </Paragraph>
            ) : null}
          </Space>
        </div>
      );
    };
    return (
      <Space direction="vertical" size={10} style={{ display: "flex" }}>
        {uploads.map(renderGithubArtifactBlock)}
      </Space>
    );
  };

  const renderImaSyncDetail = () => {
    if (!data) {
      return "-";
    }
    const nodes: ReactNode[] = [];
    if (data.ima_sync_status === "failed" && data.ima_sync_error) {
      nodes.push(
        <Tooltip key="status" title={data.ima_sync_error}>
          {renderImaStatusTag(data.ima_sync_status)}
        </Tooltip>,
      );
    } else {
      nodes.push(<span key="status">{renderImaStatusTag(data.ima_sync_status)}</span>);
    }
    if (
      data.ima_sync_batch_id ||
      data.ima_sync_status === "failed" ||
      data.ima_sync_status === "success" ||
      data.ima_sync_status === "skipped" ||
      data.ima_sync_status === "partial"
    ) {
      nodes.push(
        <Button key="record" type="link" onClick={() => onOpenImaSyncRecord(data.id, data.ima_sync_batch_id)}>
          查看记录
        </Button>,
      );
    }
    return <Space size="small">{nodes}</Space>;
  };

  const exportedFileNodes = useMemo(() => {
    const localFiles = data?.exported_files?.filter((item) => !isGithubArtifact(item)) ?? [];
    if (localFiles.length === 0) {
      return "-";
    }
    return (
      <Space direction="vertical" size={8}>
        {localFiles.map((item, index) => (
          <div key={`${item.type ?? "file"}-${index}`}>
            <Text strong>{item.label || item.type || `文件 ${index + 1}`}</Text>
            {item.path ? (
              <Paragraph style={{ marginBottom: 4 }} copyable={{ text: item.path }}>
                {item.path}
              </Paragraph>
            ) : null}
            {item.url ? (
              <a href={item.url} target="_blank" rel="noreferrer">
                打开链接
              </a>
            ) : null}
          </div>
        ))}
      </Space>
    );
  }, [data]);

  const topicCardDetail = useMemo(() => {
    const meta = data?.topic_card_meta;
    if (!meta) {
      return null;
    }
    const cards = meta.话题列表 ?? [];
    const deliveries = meta.推送记录 ?? [];
    return (
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <Space wrap>
          <Tag color={meta.图片推送 === "已开启" ? "blue" : undefined}>图片推送：{meta.图片推送 ?? "-"}</Tag>
          <Tag>文字布局：{meta.文字布局 ?? "-"}</Tag>
          <Tag>图片布局：{meta.图片布局 ?? "-"}</Tag>
          <Tag>话题数量：{meta.话题数量 ?? cards.length}</Tag>
        </Space>
        {cards.length ? (
          <Space direction="vertical" size={8} style={{ width: "100%" }}>
            {cards.map((card, index) => (
              <div
                key={`${card.标题 ?? "话题"}-${index}`}
                style={{ border: "1px solid #f0f0f0", borderRadius: 8, padding: 12, background: "#fafafa" }}
              >
                <Text strong>{`话题 ${index + 1}：${card.标题 ?? "-"}`}</Text>
                <Space wrap style={{ display: "flex", marginTop: 8 }}>
                  <Tag color="purple">话题类型：{card.话题类型 ?? "-"}</Tag>
                  <Tag color="geekblue">版式：{card.版式 ?? "-"}</Tag>
                  <Tag color="blue">主题色：{card.主题色 ?? "-"}</Tag>
                  <Tag>讨论时段：{card.讨论时段 ?? "-"}</Tag>
                  {(card.短标签 ?? []).map((tag) => (
                    <Tag key={tag}>{tag}</Tag>
                  ))}
                </Space>
              </div>
            ))}
          </Space>
        ) : (
          <Text type="secondary">没有解析到话题卡片。</Text>
        )}
        {deliveries.length ? (
          <Collapse
            ghost
            items={[
              {
                key: "topic-card-deliveries",
                label: "图片推送记录",
                children: (
                  <Space direction="vertical" size={8} style={{ width: "100%" }}>
                    {deliveries.map((delivery, index) => (
                      <div key={`${delivery.推送渠道 ?? "渠道"}-${index}`}>
                        <Space wrap>
                          <Text strong>{delivery.推送渠道 ?? "-"}</Text>
                          <Tag color={delivery.状态 === "成功" ? "green" : delivery.状态 === "失败" ? "red" : "default"}>
                            {delivery.状态 ?? "-"}
                          </Tag>
                        </Space>
                        {delivery.错误信息 ? (
                          <Paragraph type="secondary" style={{ marginBottom: 4 }}>
                            {delivery.错误信息}
                          </Paragraph>
                        ) : null}
                        {(delivery.图片列表 ?? []).map((image, imageIndex) => (
                          <Paragraph key={`${image.图片标识 ?? "图片"}-${imageIndex}`} style={{ marginBottom: 4 }}>
                            {`图片 ${imageIndex + 1}：渲染引擎 ${image.渲染引擎 ?? "-"}，图片布局 ${
                              image.图片布局 ?? "-"
                            }，图片尺寸 ${image.图片尺寸 ?? "-"}，文件大小 ${image.文件大小 ?? "-"}，图片标识 ${
                              image.图片标识 ?? "-"
                            }`}
                          </Paragraph>
                        ))}
                      </div>
                    ))}
                  </Space>
                ),
              },
            ]}
          />
        ) : null}
      </Space>
    );
  }, [data]);

  const promptCollapseItems = useMemo(() => {
    if (!data) {
      return [];
    }
    return [
      {
        key: "prompt",
        label: "提示词详情",
        children: (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div>
              <Text strong>任务提示词</Text>
              <Paragraph style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}>{taskPrompt}</Paragraph>
            </div>
            <div>
              <Text strong>系统提示词</Text>
              <Paragraph style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}>{systemInstruction}</Paragraph>
            </div>
            <div>
              <Text strong>聊天记录</Text>
              <Paragraph style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}>
                {`群聊名称：${talkerList || "-"}\n聊天记录时间：${chatlogRange}`}
              </Paragraph>
            </div>
            {chunkInfo ? <Text type="secondary">{chunkInfo}</Text> : null}
          </div>
        ),
      },
    ];
  }, [data, systemInstruction, taskPrompt, chunkInfo, talkerList, chatlogRange]);

  const timelineItems = useMemo(() => {
    if (!data) {
      return [];
    }
    const items: { color: string; children: ReactNode }[] = [];
    if (data.job_created_at) {
      items.push({
        color: "gray",
        children: (
          <div>
            <Text strong>作业创建时间</Text>
            <div>{formatDateTime(data.job_created_at)}</div>
          </div>
        ),
      });
    }
    if (data.scheduled_at) {
      items.push({
        color: "blue",
        children: (
          <div>
            <Text strong>计划执行时间</Text>
            <div>{formatDateTime(data.scheduled_at)}</div>
            <Text type="secondary">{`作业配置执行时间：${data.job_execution_time || "-"}`}</Text>
          </div>
        ),
      });
    }
    if (data.started_at) {
      items.push({
        color: "gold",
        children: (
          <div>
            <Text strong>开始时间</Text>
            <div>{formatDateTime(data.started_at)}</div>
          </div>
        ),
      });
    }
    if (data.finished_at) {
      items.push({
        color: data.status === "failed" ? "red" : "green",
        children: (
          <div>
            <Text strong>结束时间</Text>
            <div>{formatDateTime(data.finished_at)}</div>
          </div>
        ),
      });
    }
    return items;
  }, [data]);

  return (
    <Modal
      open={open}
      width={900}
      centered
      onCancel={onClose}
      onOk={onClose}
      okText="关闭"
      cancelButtonProps={{ style: { display: "none" } }}
      destroyOnClose
      title={data ? `执行记录 #${data.id}` : "执行详情"}
    >
      {data ? (
        <Descriptions bordered column={2} size="small">
          <Descriptions.Item label="任务">
            <div style={{ display: "flex", flexDirection: "column" }}>
              <Text>{`任务名称：${data.task_name ?? "-"}`}</Text>
              <Text type="secondary">{`任务ID：${data.task_id ?? "-"}`}</Text>
            </div>
          </Descriptions.Item>
          <Descriptions.Item label="作业">
            <div style={{ display: "flex", flexDirection: "column" }}>
              <Text>{`作业名称：${data.job_name ?? "-"}`}</Text>
              <Text type="secondary">{`作业ID：${data.job_id ?? "-"}`}</Text>
            </div>
          </Descriptions.Item>
          <Descriptions.Item label="执行时间">{formatDateTime(data.started_at)}</Descriptions.Item>
          <Descriptions.Item label="执行类型">{data.is_manual ? "手动执行" : "自动执行"}</Descriptions.Item>
          <Descriptions.Item label="聊天记录">
            <div style={{ display: "flex", flexDirection: "column" }}>
              <Text>{`群聊名称：${talkerList || "-"}`}</Text>
              <Text>{`聊天记录时间：${chatlogRange}`}</Text>
            </div>
          </Descriptions.Item>
          <Descriptions.Item label="使用模型">{data.llm_model_name ?? "-"}</Descriptions.Item>
          <Descriptions.Item label="提示词 Token 数">
            {renderUsageBreakdown(usageStats?.tokens, data.prompt_tokens, "", " Token")}
          </Descriptions.Item>
          <Descriptions.Item label="提示词字符数">
            {renderUsageBreakdown(usageStats?.chars, data.prompt_chars, "", " 字符")}
          </Descriptions.Item>
          <Descriptions.Item label="回复 Token 数">
            {data?.completion_tokens !== null && data?.completion_tokens !== undefined
              ? `${data.completion_tokens} Token`
              : "-"}
          </Descriptions.Item>
          <Descriptions.Item label="耗时">{formatDuration(data.duration_ms)}</Descriptions.Item>
          <Descriptions.Item label="导出文件" span={2}>
            {exportedFileNodes}
          </Descriptions.Item>
          <Descriptions.Item label="磁盘 IO" span={2}>
            {data.disk_io ? (
              <Space direction="vertical" size={4}>
                <Space wrap>
                  <Tag color={data.disk_io.provider === "weflow" ? "blue" : "purple"}>
                    {data.disk_io.provider === "weflow" ? "WeFlow" : "ChatLog"}
                  </Tag>
                  {data.disk_io.is_warning ? <Tag color="red">异常</Tag> : <Tag color="green">正常</Tag>}
                  {data.disk_io.job_alert_threshold_bytes > 0 ? (
                    data.disk_io.job_alert_triggered ? (
                      <Tag color={data.disk_io.job_alert_sent ? "red" : "orange"}>
                        {data.disk_io.job_alert_sent ? "已触发磁盘告警" : "磁盘告警未送达"}
                      </Tag>
                    ) : (
                      <Tag color="green">未触发磁盘告警</Tag>
                    )
                  ) : null}
                  <Text>{`磁盘写入：${formatBytes(data.disk_io.disk_write_bytes)}`}</Text>
                  <Text>{`进程写入：${formatBytes(data.disk_io.total_write_bytes)}`}</Text>
                  <Text>{`进程读取：${formatBytes(data.disk_io.total_read_bytes)}`}</Text>
                  {data.disk_io.provider === "weflow" ? (
                    <Text>{data.disk_io.weflow_captured ? "WeFlow 已捕获" : "WeFlow 未捕获"}</Text>
                  ) : null}
                  {data.disk_io.provider === "chatlog" ? (
                    <Text>{`ChatLog 解密写入：${formatBytes(data.disk_io.chatlog_decrypt_write_bytes)}`}</Text>
                  ) : null}
                </Space>
                {data.disk_io.job_alert_threshold_bytes > 0 ? (
                  <Space wrap>
                    <Text>{`作业告警阈值：${formatBytes(data.disk_io.job_alert_threshold_bytes)}`}</Text>
                    <Text>{`告警推送：${
                      data.disk_io.job_alert_sent ? "已推送" : data.disk_io.job_alert_triggered ? "推送失败" : "未触发"
                    }`}</Text>
                  </Space>
                ) : null}
                <a href={`/logs/disk?execution_id=${data.id}`}>查看磁盘日志详情</a>
                {data.disk_io.warning_reason ? <Text type="secondary">{data.disk_io.warning_reason}</Text> : null}
                {data.disk_io.job_alert_error ? <Text type="secondary">{data.disk_io.job_alert_error}</Text> : null}
              </Space>
            ) : (
              <Text type="secondary">暂无磁盘 IO 记录</Text>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="GitHub 部署" span={2}>
            {renderDeployDetail()}
          </Descriptions.Item>
          <Descriptions.Item label="ima 同步" span={2}>
            {renderImaSyncDetail()}
          </Descriptions.Item>
          <Descriptions.Item label="执行状态" span={2}>
            <Tag color={data.status === "success" ? "green" : data.status === "failed" ? "red" : "blue"}>
              {data.status}
            </Tag>
          </Descriptions.Item>
          {timelineItems.length ? (
            <Descriptions.Item label="执行事件" span={2}>
              <Timeline items={timelineItems} />
            </Descriptions.Item>
          ) : null}
          {topicCardDetail ? (
            <Descriptions.Item label="话题卡片详情" span={2}>
              {topicCardDetail}
            </Descriptions.Item>
          ) : null}
          {data.summary_md ? (
            <Descriptions.Item label={data.status === "failed" ? "模型原始返回结果" : "模型返回结果"} span={2}>
              <Collapse
                ghost
                defaultActiveKey={[]}
                items={[
                  {
                    key: "summary",
                    label: data.status === "failed" ? "点击展开原始返回" : "点击展开摘要",
                    children: (
                      <Paragraph style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}>{data.summary_md}</Paragraph>
                    ),
                  },
                ]}
              />
            </Descriptions.Item>
          ) : null}
          {data.error_msg ? (
            <Descriptions.Item label="错误信息" span={2}>
              <Paragraph style={{ whiteSpace: "pre-wrap" }}>{data.error_msg}</Paragraph>
            </Descriptions.Item>
          ) : null}
        </Descriptions>
      ) : (
        <div>暂无数据</div>
      )}
      {data ? <Collapse style={{ marginTop: 16 }} items={promptCollapseItems} /> : null}
    </Modal>
  );
};

export default ExecutionDetailModal;
