import { useMemo } from "react";
import { Layout, Menu, Avatar, Space, Typography, Dropdown, Select } from "antd";
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
  GlobalOutlined,
} from "@ant-design/icons";
import { useNavigate, useLocation, Outlet } from "react-router-dom";
import { useAuth } from "../store/auth";
import { useI18n, LANG_OPTIONS } from "../i18n";
import DynamicBackground from "../components/DynamicBackground";

const { Header, Sider, Content } = Layout;

// 专业后台布局：分组侧边栏 + 顶栏用户信息
export default function AppLayout() {
  const { role, username, logout } = useAuth();
  const { lang, setLang, t } = useI18n();
  const navigate = useNavigate();
  const location = useLocation();

  // 根据角色生成分组菜单
  const menuItems = useMemo(() => {
    const items: any[] = [
      {
        type: "group",
        label: t("dashboard"),
        children: [
          { key: "/", icon: <DashboardOutlined />, label: t("dashboard") },
        ],
      },
      {
        type: "group",
        label: t("planList"),
        children: [
          { key: "/plans", icon: <UnorderedListOutlined />, label: t("planList") },
          { key: "/plans/new", icon: <PlusCircleOutlined />, label: t("newPlan") },
        ],
      },
    ];
    if (role === "supervisor") {
      items.push({
        type: "group",
        label: t("reviewBoard"),
        children: [
          { key: "/reviews", icon: <AuditOutlined />, label: t("reviewBoard") },
        ],
      });
    }
    items.push({
      type: "group",
      label: t("memoryGraph"),
      children: [
        { key: "/memory", icon: <ApartmentOutlined />, label: t("memoryGraph") },
      ],
    });
    items.push({
      type: "group",
      label: t("about"),
      children: [
        { key: "/about", icon: <ReadOutlined />, label: t("about") },
      ],
    });
    return items;
  }, [role, lang]);

  const roleLabel =
    role === "advisor" ? "旅行顾问" : role === "supervisor" ? "主管管理员" : "游客";

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
          <span>山海行</span>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
        {/* 左下角多国语言切换 */}
        <div style={{ position: "absolute", bottom: 16, left: 16, right: 16 }}>
          <Select
            value={lang}
            onChange={setLang}
            size="small"
            style={{ width: "100%" }}
            options={LANG_OPTIONS}
          />
        </div>
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
