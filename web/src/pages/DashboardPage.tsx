import { Card, Col, List, Row, Space, Statistic, Tag, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { fetchExecutions } from "../services/executions";
import { fetchTasks, type Task } from "../services/tasks";
import { fetchSystemStatus } from "../services/system";
import { formatDateTime } from "../utils/datetime";

dayjs.extend(relativeTime);

type ScheduledJob = {
  taskName: string;
  jobName: string;
  nextRunAt: dayjs.Dayjs | null;
  executionTime?: string | null;
};

function DashboardPage() {
  const { data } = useQuery({ queryKey: ["system-status"], queryFn: fetchSystemStatus, refetchInterval: 60_000 });
  const { data: executionsPage, isLoading: executionsLoading } = useQuery({
    queryKey: ["executions", "dashboard"],
    queryFn: () => fetchExecutions({ page: 1, page_size: 5 }),
    refetchInterval: 60_000
  });
  const { data: tasksData, isLoading: tasksLoading } = useQuery<Task[]>({
    queryKey: ["tasks", "dashboard"],
    queryFn: fetchTasks,
    staleTime: 60_000
  });
  const tasks = tasksData ?? [];
  const now = dayjs();
  const executions = executionsPage?.items ?? [];

  const chatRecordStatus = data?.chat_record_status ?? data?.chatlog_status;
  const chatRecordProvider = data?.chat_record_provider === "weflow" ? "WeFlow" : "ChatLog";
  const chatlogColor = chatRecordStatus === "ok" ? "green" : chatRecordStatus === "unreachable" ? "red" : "orange";
  const serverClock = data?.server_time ? formatDateTime(data.server_time) : "-";
  const jobsFlat: ScheduledJob[] = tasks.flatMap((task) =>
    task.jobs.map((job) => ({
      taskName: task.name,
      jobName: job.name,
      nextRunAt: job.next_run_at ? dayjs(job.next_run_at) : null,
      executionTime: job.execution_time ?? null
    }))
  );
  const upcomingJobs: ScheduledJob[] = jobsFlat
    .filter((job) => job.nextRunAt)
    .sort((a, b) => a.nextRunAt!.valueOf() - b.nextRunAt!.valueOf());

  const todayPlans = upcomingJobs.filter((job) => job.nextRunAt!.isSame(now, "day"));
  const nextExecutions = upcomingJobs.slice(0, 5);

  const renderScheduleList = (items: ScheduledJob[]) => (
    <List
      dataSource={items}
      loading={tasksLoading}
      locale={{ emptyText: "暂无计划" }}
      renderItem={(item) => {
        const statusTag = item.nextRunAt && item.nextRunAt.isAfter(now) ? (
          <Tag color="blue">待执行</Tag>
        ) : (
          <Tag color="default">已过期</Tag>
        );
        const timeText = item.nextRunAt ? formatDateTime(item.nextRunAt.toISOString()) : "-";
        return (
          <List.Item>
            <Space direction="vertical" size={4} style={{ width: "100%" }}>
              <Space size="small">
                <Typography.Text strong>{item.taskName}</Typography.Text>
                <Typography.Text type="secondary">·</Typography.Text>
                <Typography.Text>{item.jobName}</Typography.Text>
              </Space>
              <Space size="small">
                <Typography.Text type="secondary">执行时间：{timeText}</Typography.Text>
                {statusTag}
              </Space>
            </Space>
          </List.Item>
        );
      }}
    />
  );

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Row gutter={[16, 16]}>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title="任务数量" value={data?.tasks ?? 0} />
            <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
              已配置的群聊总结任务
            </Typography.Paragraph>
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title="作业数量" value={data?.jobs ?? 0} />
            <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
              定时执行的时间窗口
            </Typography.Paragraph>
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title="今日执行数" value={data?.executions_today ?? 0} />
            <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
              以服务器时间为准
            </Typography.Paragraph>
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title="聊天记录接口状态"
              valueRender={() => <Tag color={chatlogColor}>{chatRecordProvider} · {chatRecordStatus ?? "未知"}</Tag>}
            />
            <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
              数据服务健康检查
            </Typography.Paragraph>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Card>
            <Typography.Title level={5} style={{ marginBottom: 16 }}>
              今日执行计划
            </Typography.Title>
            {renderScheduleList(todayPlans)}
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card>
            <Typography.Title level={5} style={{ marginBottom: 16 }}>
              下次计划执行
            </Typography.Title>
            {renderScheduleList(nextExecutions)}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Card>
            <Typography.Title level={5} style={{ marginBottom: 16 }}>
              最近执行
            </Typography.Title>
            <List
              dataSource={executions}
              loading={executionsLoading}
              locale={{ emptyText: "暂无执行记录" }}
              renderItem={(item) => (
                <List.Item>
                  <Space direction="vertical" size={4} style={{ width: "100%" }}>
                    <Space size="small">
                      <Typography.Text>{item.task_name || `任务 #${item.task_id}`}</Typography.Text>
                      <Typography.Text type="secondary">·</Typography.Text>
                      <Typography.Text strong>{item.job_name || `作业 #${item.job_id}`}</Typography.Text>
                      <Tag color={item.status === "success" ? "green" : item.status === "failed" ? "red" : "blue"}>{item.status}</Tag>
                    </Space>
                    <Typography.Text type="secondary">{formatDateTime(item.started_at)}</Typography.Text>
                  </Space>
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card>
            <Typography.Title level={5} style={{ marginBottom: 16 }}>
              系统信息
            </Typography.Title>
            <Typography.Paragraph style={{ marginBottom: 4 }}>应用：{data?.app_name ?? "-"}</Typography.Paragraph>
            <Typography.Paragraph style={{ marginBottom: 0 }}>服务器时间：{serverClock}</Typography.Paragraph>
          </Card>
        </Col>
      </Row>
    </Space>
  );
}

export default DashboardPage;
