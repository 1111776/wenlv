import { useMemo } from "react";
import { Layout, Menu, Avatar, Space, Typography, Dropdown } from "antd";
import {
  EnvironmentOutlined,
  AuditOutlined,
  LogoutOutlined,
  UserOutlined,
  DashboardOutlined,
  UnorderedListOutlined,
  PlusCircleOutlined,
  ReadOutlined,
  ApartmentOutlined,
} from "@ant-design/icons";
import { useNavigate, useLocation, Outlet } from "react-router-dom";
import { useAuth } from "../store/auth";
import DynamicBackground from "../components/DynamicBackground";

const { Header, Sider, Content } = Layout;

// 专业后台布局：分组侧边栏 + 顶栏用户信息
export default function AppLayout() {
  const { role, username, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // 根据角色生成分组菜单
  const menuItems = useMemo(() => {
    const items: any[] = [
      {
        type: "group",
        label: "总览",
        children: [
          { key: "/", icon: <DashboardOutlined />, label: "工作台" },
        ],
      },
      {
        type: "group",
        label: "行程管理",
        children: [
          { key: "/plans", icon: <UnorderedListOutlined />, label: "行程列表" },
          { key: "/plans/new", icon: <PlusCircleOutlined />, label: "新建行程" },
        ],
      },
    ];
    if (role === "supervisor") {
      items.push({
        type: "group",
        label: "审批协作",
        children: [
          { key: "/reviews", icon: <AuditOutlined />, label: "审核台" },
        ],
      });
    }
    items.push({
      type: "group",
      label: "记忆",
      children: [
        { key: "/memory", icon: <ApartmentOutlined />, label: "记忆图谱" },
      ],
    });
    items.push({
      type: "group",
      label: "帮助",
      children: [
        { key: "/about", icon: <ReadOutlined />, label: "系统说明" },
      ],
    });
    return items;
  }, [role]);

  const roleLabel = role === "advisor" ? "旅行顾问" : "主管管理员";

  // 高亮当前菜单
  const selectedKey = useMemo(() => {
    const p = location.pathname;
    if (p.startsWith("/plans/new")) return "/plans/new";
    if (p.startsWith("/plans/")) return "/plans";
    if (p.startsWith("/reviews")) return "/reviews";
    if (p.startsWith("/memory")) return "/memory";
    if (p.startsWith("/about")) return "/about";
    return "/";
  }, [location.pathname]);

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider theme="dark" width={220}>
        <div
          style={{
            height: 64,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 8,
            color: "#fff",
            fontSize: 16,
            fontWeight: 600,
            borderBottom: "1px solid rgba(255,255,255,0.1)",
          }}
        >
          <EnvironmentOutlined style={{ fontSize: 22, color: "#1677ff" }} />
          <span>文旅行程规划</span>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>

      <Layout>
        <Header
          style={{
            background: "#fff",
            padding: "0 24px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            borderBottom: "1px solid #f0f0f0",
            height: 64,
          }}
        >
          <Typography.Title level={4} style={{ margin: 0 }}>
            {roleLabel}工作台
          </Typography.Title>
          <Dropdown
            menu={{
              items: [
                { key: "logout", icon: <LogoutOutlined />, label: "退出登录", onClick: logout },
              ],
            }}
          >
            <Space style={{ cursor: "pointer" }}>
              <Avatar style={{ backgroundColor: "#1677ff" }} icon={<UserOutlined />} />
              <span>{username}</span>
              <span style={{ color: "#999", fontSize: 12 }}>{roleLabel}</span>
            </Space>
          </Dropdown>
        </Header>

        <Content style={{ padding: 24, position: "relative" }}>
          <DynamicBackground variant="light" position="absolute" />
          <div style={{ position: "relative", zIndex: 1 }}>
            <Outlet />
          </div>
        </Content>
      </Layout>
    </Layout>
  );
}
