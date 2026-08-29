import { useState } from "react";
import { Button, Card, Form, Input, message, Tabs, Typography, Space, Tag, Divider } from "antd";
import { EnvironmentOutlined, LockOutlined, UserOutlined, AuditOutlined } from "@ant-design/icons";
import { api, unwrap } from "../api/client";
import { useAuth } from "../store/auth";
import DynamicBackground from "../components/DynamicBackground";

// 登录/注册页：品牌区 + 表单区 + 一键登录按钮
export default function Login() {
  const { setAuth } = useAuth();
  const [loading, setLoading] = useState(false);

  // 登录成功后：写 store + localStorage，并强制整页跳转（最可靠）
  const doLogin = (username: string, password: string) => {
    setLoading(true);
    api
      .post("/auth/login", { username, password })
      .then((resp) => {
        const data = resp.data.data;
        setAuth(data.access_token, data.role, username);
        message.success("登录成功，正在进入…");
        // 强制跳转，确保即使浏览器缓存旧代码也能进入系统
        setTimeout(() => {
          window.location.href = "/";
        }, 300);
      })
      .catch((e: any) => {
        message.error(e.message || "登录失败");
      })
      .finally(() => setLoading(false));
  };

  const onLogin = (values: any) => {
    doLogin(values.username, values.password);
  };

  const onRegister = async (values: any) => {
    setLoading(true);
    try {
      await unwrap(api.post("/auth/register", { username: values.username, password: values.password }));
      message.success("注册成功，请登录");
    } catch (e: any) {
      message.error(e.message || "注册失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        height: "100vh",
        display: "flex",
        position: "relative",
        background: "transparent",
      }}
    >
      {/* 动态壁纸背景 */}
      <DynamicBackground />

      {/* 品牌区 */}
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "0 80px",
          color: "#fff",
          position: "relative",
          zIndex: 1,
        }}
      >
        <EnvironmentOutlined style={{ fontSize: 60, marginBottom: 24 }} />
        <Typography.Title style={{ color: "#fff", fontSize: 42, marginBottom: 16 }}>
          文旅多 Agent 行程规划系统
        </Typography.Title>
        <Typography.Paragraph style={{ color: "rgba(255,255,255,0.85)", fontSize: 18, maxWidth: 500 }}>
          输入一句自然语言需求，AI Agent 团队自动完成偏好解析、网页调研、舆情评估、日程编排与预算计算。
        </Typography.Paragraph>
        <Space>
          <Tag color="rgba(255,255,255,0.2)" style={{ color: "#fff" }}>8 个协作 Agent</Tag>
          <Tag color="rgba(255,255,255,0.2)" style={{ color: "#fff" }}>断点续传</Tag>
          <Tag color="rgba(255,255,255,0.2)" style={{ color: "#fff" }}>人机协作审核</Tag>
        </Space>
      </div>

      {/* 表单区 */}
      <div style={{ width: 440, display: "flex", alignItems: "center", justifyContent: "center", padding: 40, position: "relative", zIndex: 1 }}>
        <Card style={{ width: "100%", boxShadow: "0 8px 24px rgba(0,0,0,0.15)" }}>
          <Tabs
            centered
            items={[
              {
                key: "login",
                label: "登录",
                children: (
                  <Form onFinish={onLogin} size="large">
                    <Form.Item name="username" rules={[{ required: true, message: "请输入用户名" }]}>
                      <Input prefix={<UserOutlined />} placeholder="用户名" />
                    </Form.Item>
                    <Form.Item name="password" rules={[{ required: true, message: "请输入密码" }]}>
                      <Input.Password prefix={<LockOutlined />} placeholder="密码" />
                    </Form.Item>
                    <Button type="primary" htmlType="submit" loading={loading} block>
                      登录
                    </Button>
                  </Form>
                ),
              },
              {
                key: "register",
                label: "注册",
                children: (
                  <Form onFinish={onRegister} size="large">
                    <Form.Item name="username" rules={[{ required: true, min: 3, message: "至少 3 个字符" }]}>
                      <Input prefix={<UserOutlined />} placeholder="用户名（顾问账号）" />
                    </Form.Item>
                    <Form.Item name="password" rules={[{ required: true, min: 6, message: "至少 6 位" }]}>
                      <Input.Password prefix={<LockOutlined />} placeholder="密码" />
                    </Form.Item>
                    <Button type="primary" htmlType="submit" loading={loading} block>
                      注册顾问账号
                    </Button>
                  </Form>
                ),
              },
            ]}
          />
          <Divider plain style={{ margin: "16px 0" }}>
            <span style={{ color: "#999", fontSize: 12 }}>一键登录演示账号</span>
          </Divider>
          <Space direction="vertical" style={{ width: "100%" }} size={8}>
            <Button
              block
              size="large"
              icon={<UserOutlined />}
              loading={loading}
              onClick={() => doLogin("advisor_demo", "wenlv123")}
            >
              以「旅行顾问」身份进入（创建行程）
            </Button>
            <Button
              block
              size="large"
              type="primary"
              icon={<AuditOutlined />}
              loading={loading}
              onClick={() => doLogin("supervisor_demo", "wenlv123")}
            >
              以「主管」身份进入（审核行程）
            </Button>
          </Space>
        </Card>
      </div>
    </div>
  );
}
