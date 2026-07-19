import { useEffect, useMemo, useState } from "react";
import { Layout, Menu, Typography } from "antd";
import type { MenuProps } from "antd";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import {
  DashboardOutlined,
  ApiOutlined,
  RobotOutlined,
  ClusterOutlined,
  HistoryOutlined,
  AlertOutlined,
  SettingOutlined,
  BookOutlined,
  GithubOutlined,
  FolderOpenOutlined,
  FileSearchOutlined
} from "@ant-design/icons";
import DashboardPage from "./pages/DashboardPage";
import ModelsPage from "./pages/ModelsPage";
import WebhooksPage from "./pages/WebhooksPage";
import TasksPage from "./pages/TasksPage";
import ExecutionsPage from "./pages/ExecutionsPage";
import AlertsPage from "./pages/AlertsPage";
import SettingsPage from "./pages/SettingsPage";
import Logo from "./components/Logo";
import PromptTemplatesPage from "./pages/PromptTemplatesPage";
import GithubConfigsPage from "./pages/GithubConfigsPage";
import GithubDeploymentsPage from "./pages/GithubDeploymentsPage";
import ImaAccountsPage from "./pages/ImaAccountsPage";
import ImaSettingsPage from "./pages/ImaSettingsPage";
import ImaSyncRecordsPage from "./pages/ImaSyncRecordsPage";
import DiskIoRecordsPage from "./pages/DiskIoRecordsPage";
import DiskInspectionJobsPage from "./pages/DiskInspectionJobsPage";
import DiskInspectionRunsPage from "./pages/DiskInspectionRunsPage";

const { Header, Content, Sider } = Layout;

type NavItem = {
  key: string;
  icon?: React.ReactNode;
  label: string;
  path?: string;
  legacyPaths?: string[];
  children?: NavItem[];
};

const navItems: NavItem[] = [
  { key: "dashboard", icon: <DashboardOutlined />, label: "总览", path: "/dashboard" },
  { key: "models", icon: <RobotOutlined />, label: "模型", path: "/models" },
  { key: "prompt-templates", icon: <BookOutlined />, label: "提示词管理", path: "/prompts" },
  { key: "webhooks", icon: <ApiOutlined />, label: "Webhook", path: "/webhooks" },
  { key: "tasks", icon: <ClusterOutlined />, label: "任务&作业", path: "/tasks" },
  { key: "executions", icon: <HistoryOutlined />, label: "执行历史", path: "/executions" },
  {
    key: "github",
    icon: <GithubOutlined />,
    label: "GitHub 管理",
    children: [
      { key: "github-configs", label: "GitHub 配置", path: "/github/configs", legacyPaths: ["/github-configs"] },
      { key: "github-deployments", label: "部署记录", path: "/github/deployments" }
    ]
  },
  {
    key: "ima",
    icon: <FolderOpenOutlined />,
    label: "ima知识库管理",
    children: [
      { key: "ima-accounts", label: "ima账号管理", path: "/ima/accounts" },
      { key: "ima-settings", label: "ima知识库同步设置", path: "/ima/settings" },
      { key: "ima-records", label: "ima同步记录", path: "/ima/records" }
    ]
  },
  {
    key: "logs",
    icon: <FileSearchOutlined />,
    label: "日志",
    children: [
      { key: "logs-inspection-jobs", label: "巡检任务", path: "/logs/inspection-jobs" },
      { key: "logs-disk", label: "磁盘日志", path: "/logs/disk" },
      { key: "logs-inspection-runs", label: "巡检日志", path: "/logs/inspection-runs" }
    ]
  },
  { key: "alerts", icon: <AlertOutlined />, label: "告警", path: "/alerts" },
  { key: "settings", icon: <SettingOutlined />, label: "系统设置", path: "/settings" }
];

type FlatNav = {
  key: string;
  path?: string;
  legacyPaths?: string[];
  parentKey?: string;
};

const flattenNavItems = (items: NavItem[], parentKey?: string): FlatNav[] =>
  items.flatMap((item) => {
    const current: FlatNav = {
      key: item.key,
      path: item.path,
      legacyPaths: item.legacyPaths,
      parentKey,
    };
    if (item.children && item.children.length > 0) {
      return [current, ...flattenNavItems(item.children, item.key)];
    }
    return [current];
  });

function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const flatNav = useMemo(() => flattenNavItems(navItems), []);
  const selectedEntry = useMemo(() => {
    const pathname = location.pathname;
    return flatNav.find((item) => {
      const paths = [item.path, ...(item.legacyPaths ?? [])].filter(Boolean) as string[];
      return paths.some((path) => pathname.startsWith(path));
    });
  }, [flatNav, location.pathname]);
  const selectedKey = selectedEntry?.key ?? "dashboard";
  const [openKeys, setOpenKeys] = useState<string[]>(selectedEntry?.parentKey ? [selectedEntry.parentKey] : []);

  useEffect(() => {
    setOpenKeys(selectedEntry?.parentKey ? [selectedEntry.parentKey] : []);
  }, [selectedEntry?.parentKey]);

  const menuItemsForAntd: MenuProps["items"] = useMemo(() => {
    const buildItems = (items: NavItem[]): MenuProps["items"] =>
      items.map((item) => {
        if (item.children && item.children.length > 0) {
          return {
            key: item.key,
            icon: item.icon,
            label: item.label,
            children: buildItems(item.children),
          };
        }
        return {
          key: item.key,
          icon: item.icon,
          label: item.label,
          onClick: () => item.path && navigate(item.path),
        };
      });
    return buildItems(navItems);
  }, [navigate]);

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider theme="light">
        <div className="logo"><Logo /></div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          openKeys={openKeys}
          onOpenChange={(keys) => setOpenKeys(keys as string[])}
          items={menuItemsForAntd}
        />
      </Sider>
      <Layout>
        <Header style={{ background: "#fff", padding: "0 24px", display: "flex", alignItems: "center" }}>
          <Typography.Title level={3} style={{ margin: 0, color: "#2f54eb" }}>
            <span role="img" aria-label="news" style={{ marginRight: 8 }}>🗞️</span>
            群聊日报智能助手
          </Typography.Title>
        </Header>
        <Content style={{ margin: "24px", background: "#fff", padding: "24px", minHeight: 280, display: "flex", flexDirection: "column" }}>
          <div style={{ flex: 1 }}>
            <Routes>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/models" element={<ModelsPage />} />
              <Route path="/prompts" element={<PromptTemplatesPage />} />
              <Route path="/webhooks" element={<WebhooksPage />} />
              <Route path="/tasks/*" element={<TasksPage />} />
              <Route path="/executions" element={<ExecutionsPage />} />
              <Route path="/github/configs" element={<GithubConfigsPage />} />
              <Route path="/github/deployments" element={<GithubDeploymentsPage />} />
              <Route path="/github-configs" element={<GithubConfigsPage />} />
              <Route path="/ima/accounts" element={<ImaAccountsPage />} />
              <Route path="/ima/settings" element={<ImaSettingsPage />} />
              <Route path="/ima/records" element={<ImaSyncRecordsPage />} />
              <Route path="/logs/disk" element={<DiskIoRecordsPage />} />
              <Route path="/logs/inspection-jobs" element={<DiskInspectionJobsPage />} />
              <Route path="/logs/inspection-runs" element={<DiskInspectionRunsPage />} />
              <Route path="/alerts" element={<AlertsPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Routes>
          </div>
        </Content>
      </Layout>
    </Layout>
  );
}

export default App;
