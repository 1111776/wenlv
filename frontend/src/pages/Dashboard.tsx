import { useEffect, useMemo, useState } from "react";
import {
  Card,
  Col,
  Row,
  Tag,
  Typography,
  Space,
  Button,
  Progress,
  List,
  Empty,
  message,
} from "antd";
import {
  EnvironmentOutlined,
  AuditOutlined,
  FileDoneOutlined,
  LoadingOutlined,
  RightOutlined,
  PlusOutlined,
  RocketOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import dayjs from "dayjs";
import { api, unwrap } from "../api/client";
import { useAuth } from "../store/auth";

const STATUS_META: Record<string, { color: string; label: string }> = {
  planning: { color: "blue", label: "排队中" },
  running: { color: "processing", label: "执行中" },
  suspended: { color: "warning", label: "待审核" },
  recovering: { color: "orange", label: "恢复中" },
  completed: { color: "success", label: "已完成" },
  failed: { color: "error", label: "失败" },
  cancelled: { color: "default", label: "已取消" },
};

// 工作台：统计概览 + 最近行程 + 快捷入口
export default function Dashboard() {
  const { role } = useAuth();
  const navigate = useNavigate();
  const [plans, setPlans] = useState<any[]>([]);

  const roleLabel =
    role === "advisor" ? "旅行顾问" : role === "supervisor" ? "主管管理员" : "游客";
  const isConsultant = role === "advisor" || role === "tourist";

  const load = async () => {
    try {
      const data = await unwrap<any>(api.get("/plans"));
      setPlans(data.items || []);
    } catch (e: any) {
      message.error(e.message);
    }
  };

  useEffect(() => {
    load();
    const timer = setInterval(load, 4000);
    return () => clearInterval(timer);
  }, []);

  const stats = useMemo(() => {
    const total = plans.length;
    const running = plans.filter((p) => p.status === "running" || p.status === "planning").length;
    const review = plans.filter((p) => p.status === "suspended").length;
    const done = plans.filter((p) => p.status === "completed").length;
    return { total, running, review, done };
  }, [plans]);

  const recent = plans.slice(0, 6);

  return (
    <div>
      {/* 欢迎横幅 */}
      <Card
        style={{
          marginBottom: 16,
          border: "none",
          borderRadius: 16,
          background: "linear-gradient(120deg, #1677ff 0%, #3a8cff 45%, #0a3d91 100%)",
          boxShadow: "0 8px 24px rgba(22,119,255,0.25)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <Typography.Title level={3} style={{ color: "#fff", margin: 0, letterSpacing: 0.5 }}>
              欢迎回来，{roleLabel}
            </Typography.Title>
            <Typography.Paragraph style={{ color: "rgba(255,255,255,0.85)", margin: "10px 0 0", fontSize: 15 }}>
              基于 8 个 AI Agent 协作的文旅资源调研与个性化行程规划系统
            </Typography.Paragraph>
          </div>
          {isConsultant && (
            <Button
              type="primary"
              icon={<RocketOutlined />}
              size="large"
              style={{ background: "#fff", color: "#1677ff", border: "none" }}
              onClick={() => navigate("/plans/new")}
            >
              立即创建行程
            </Button>
          )}
          {role === "supervisor" && (
            <Button
              size="large"
              icon={<AuditOutlined />}
              style={{ background: "#fff", color: "#1677ff", border: "none" }}
              onClick={() => navigate("/reviews")}
            >
              去审核台
            </Button>
          )}
        </div>
      </Card>

      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card hoverable onClick={() => navigate("/plans")}>
            <StatCard icon={<EnvironmentOutlined />} label="全部行程" value={stats.total} color="#1677ff" bg="#e6f0ff" />
          </Card>
        </Col>
        <Col span={6}>
          <Card hoverable onClick={() => navigate("/plans")}>
            <StatCard icon={<LoadingOutlined />} label="执行中" value={stats.running} color="#faad14" bg="#fff7e6" />
          </Card>
        </Col>
        <Col span={6}>
          <Card hoverable onClick={() => navigate(role === "supervisor" ? "/reviews" : "/plans")}>
            <StatCard icon={<AuditOutlined />} label="待审核" value={stats.review} color="#ff4d4f" bg="#fff1f0" />
          </Card>
        </Col>
        <Col span={6}>
          <Card hoverable onClick={() => navigate("/plans")}>
            <StatCard icon={<FileDoneOutlined />} label="已完成" value={stats.done} color="#52c41a" bg="#f6ffed" />
          </Card>
        </Col>
      </Row>

      {/* 最近行程 */}
      <Card
        title="最近行程"
        extra={
          <Button type="link" onClick={() => navigate("/plans")}>
            查看全部 <RightOutlined />
          </Button>
        }
      >
        {recent.length === 0 ? (
          <Empty description="暂无行程" style={{ padding: 40 }}>
            {isConsultant && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate("/plans/new")}>
                创建第一个行程
              </Button>
            )}
          </Empty>
        ) : (
          <List
            dataSource={recent}
            renderItem={(p: any) => {
              const meta = STATUS_META[p.status] || { color: "default", label: p.status };
              const done = p.progress?.done ?? 0;
              const total = p.progress?.total ?? 0;
              const percent = total > 0 ? Math.round((done / total) * 100) : 0;
              return (
                <List.Item
                  key={p.id}
                  style={{ cursor: "pointer" }}
                  onClick={() => navigate(`/plans/${p.id}`)}
                  actions={[<RightOutlined key="go" />]}
                >
                  <List.Item.Meta
                    title={
                      <Space>
                        <Typography.Text ellipsis style={{ maxWidth: 420 }}>
                          {p.query}
                        </Typography.Text>
                        <Tag color={meta.color}>{meta.label}</Tag>
                      </Space>
                    }
                    description={
                      <Space size="large">
                        <span style={{ fontSize: 12, color: "#999" }}>
                          {dayjs(p.created_at).format("MM-DD HH:mm")}
                        </span>
                        <span style={{ fontSize: 12, color: "#999" }}>
                          进度 {done}/{total}
                        </span>
                      </Space>
                    }
                  />
                  <div style={{ width: 160 }}>
                    <Progress
                      percent={percent}
                      size="small"
                      status={p.status === "failed" ? "exception" : undefined}
                    />
                  </div>
                </List.Item>
              );
            }}
          />
        )}
      </Card>
    </div>
  );
}

function StatCard({ icon, label, value, color, bg }: { icon: any; label: string; value: number; color: string; bg: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
      <div className="icon-pill" style={{ color, background: bg }}>
        {icon}
      </div>
      <div>
        <div className="stat-number" style={{ color }}>{value}</div>
        <div style={{ color: "#8c8c8c", fontSize: 13 }}>{label}</div>
      </div>
    </div>
  );
}
