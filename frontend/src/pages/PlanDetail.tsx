import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Button,
  Card,
  Col,
  Descriptions,
  message,
  Row,
  Space,
  Table,
  Tabs,
  Tag,
  Timeline,
  Typography,
} from "antd";
import {
  ArrowLeftOutlined,
  EnvironmentOutlined,
  CarOutlined,
  CoffeeOutlined,
  HomeOutlined,
} from "@ant-design/icons";
import { api, unwrap } from "../api/client";
import { subscribePlan } from "../api/ws";
import AgentFlow from "../components/AgentFlow";
import Markdown from "../components/Markdown";

// 任务状态徽章
const TASK_STATUS: Record<string, { color: string; label: string }> = {
  pending: { color: "default", label: "待执行" },
  running: { color: "processing", label: "执行中" },
  completed: { color: "success", label: "已完成" },
  blocked: { color: "error", label: "已拦截" },
  failed: { color: "warning", label: "失败" },
};

// 行程详情：Agent 流程 + 网页任务 + 预算 + 报告 + 实时推送
export default function PlanDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [agents, setAgents] = useState<any>(null);
  const [planFile, setPlanFile] = useState<string>("");
  const [report, setReport] = useState<any>(null);
  const [lastEvent, setLastEvent] = useState<string>("");

  const load = async () => {
    try {
      const data = await unwrap<any>(api.get(`/plans/${id}/agents`));
      setAgents(data);
      if (data.status === "completed" && !data.rejected) {
        const r = await unwrap<any>(api.get(`/plans/${id}/report`)).catch(() => null);
        setReport(r);
      }
      const f = await unwrap<any>(api.get(`/plans/${id}/plan-file`)).catch(() => ({ markdown: "" }));
      setPlanFile(f.markdown);
    } catch (e: any) {
      message.error(e.message);
    }
  };

  useEffect(() => {
    load();
    const timer = setInterval(load, 3000);

    // WebSocket 实时推送
    const close = subscribePlan(id!, (evt) => {
      setLastEvent(`${evt.event}@${evt.ts || ""}`);
      load(); // 事件触发立即刷新
    });

    return () => {
      clearInterval(timer);
      close();
    };
  }, [id]);

  if (!agents) return <Card loading style={{ minHeight: 300 }} />;

  const statusMeta: Record<string, { color: string; label: string }> = {
    planning: { color: "blue", label: "排队中" },
    running: { color: "processing", label: "执行中" },
    suspended: { color: "warning", label: "待审核" },
    recovering: { color: "orange", label: "恢复中" },
    completed: { color: "success", label: "已完成" },
    failed: { color: "error", label: "失败" },
    cancelled: { color: "default", label: "已取消" },
  };
  const sm = statusMeta[agents.status] || { color: "default", label: agents.status };

  const tabItems = [
    {
      key: "itinerary",
      label: "📅 行程计划",
      children: agents.itinerary?.daily_plan ? (
        <div>
          {/* 路线串联 */}
          {agents.itinerary.route && (
            <Card size="small" style={{ marginBottom: 16, background: "#f0f7ff" }}>
              <Space>
                <EnvironmentOutlined style={{ color: "#1677ff" }} />
                <Typography.Text strong>推荐路线：</Typography.Text>
                <Typography.Text>{agents.itinerary.route}</Typography.Text>
              </Space>
            </Card>
          )}
          {/* 每日时间线 */}
          {agents.itinerary.daily_plan.map((day: any) => (
            <Card
              key={day.day}
              size="small"
              title={<Typography.Text strong>第 {day.day} 天</Typography.Text>}
              style={{ marginBottom: 12 }}
            >
              <Timeline
                items={[
                  {
                    color: "blue",
                    dot: <EnvironmentOutlined />,
                    children: (
                      <div>
                        <Typography.Text strong>{day.morning.spot}</Typography.Text>
                        <div style={{ color: "#999", fontSize: 12 }}>{day.morning.time} · {day.morning.desc}</div>
                        <Tag color="blue" style={{ marginTop: 4 }}>{day.morning.transport}</Tag>
                      </div>
                    ),
                  },
                  {
                    color: "green",
                    dot: <EnvironmentOutlined />,
                    children: (
                      <div>
                        <Typography.Text strong>{day.afternoon.spot}</Typography.Text>
                        <div style={{ color: "#999", fontSize: 12 }}>{day.afternoon.time} · {day.afternoon.desc}</div>
                        <Tag color="green" style={{ marginTop: 4 }}>{day.afternoon.transport}</Tag>
                      </div>
                    ),
                  },
                  {
                    color: "purple",
                    dot: <EnvironmentOutlined />,
                    children: (
                      <div>
                        <Typography.Text strong>{day.evening.spot}</Typography.Text>
                        <div style={{ color: "#999", fontSize: 12 }}>{day.evening.time} · {day.evening.desc}</div>
                        <Tag color="purple" style={{ marginTop: 4 }}>{day.evening.transport}</Tag>
                      </div>
                    ),
                  },
                ]}
              />
              <Space style={{ marginTop: 8 }} size="large">
                <span><HomeOutlined /> {day.hotel}</span>
                {day.meals && <span><CoffeeOutlined /> {day.meals.join(" / ")}</span>}
              </Space>
            </Card>
          ))}
        </div>
      ) : (
        <Typography.Text type="secondary">行程计划生成中…</Typography.Text>
      ),
    },
    {
      key: "flow",
      label: "Agent 执行流程",
      children: (
        <div>
          <AgentFlow agents={agents.agents} />
          <Table
            rowKey="page_no"
            dataSource={agents.tasks || []}
            columns={[
              { title: "页", dataIndex: "page_no", width: 60 },
              { title: "调研主题", dataIndex: "title" },
              { title: "来源", dataIndex: "url", ellipsis: true },
              {
                title: "状态",
                dataIndex: "status",
                width: 100,
                render: (s: string) => {
                  const m = TASK_STATUS[s] || { color: "default", label: s };
                  return <Tag color={m.color}>{m.label}</Tag>;
                },
              },
              {
                title: "结果",
                dataIndex: "result",
                width: 120,
                render: (r: any) =>
                  r?.blocked ? (
                    <Tag color="error">拦截: {r.pattern || r.category}</Tag>
                  ) : r?.sentiment ? (
                    <Tag color={r.sentiment === "negative" ? "error" : r.sentiment === "positive" ? "success" : "default"}>
                      {r.sentiment}
                    </Tag>
                  ) : (
                    "-"
                  ),
              },
            ]}
            pagination={false}
            size="small"
          />
        </div>
      ),
    },
    {
      key: "report",
      label: "📄 最终报告",
      children: report ? (
        <div>
          <Markdown content={report.markdown} />
        </div>
      ) : (
        <Typography.Text type="secondary">
          {agents.status === "completed" ? "报告生成中或已驳回" : "报告将在行程完成后生成"}
        </Typography.Text>
      ),
    },
    {
      key: "plan-file",
      label: "📋 状态看板",
      children: <Markdown content={planFile} />,
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/")}>
          返回
        </Button>
        <Typography.Title level={4} style={{ margin: 0 }}>
          行程详情
        </Typography.Title>
        <Tag color={sm.color}>{sm.label}</Tag>
        {agents.rejected && <Tag color="error">已驳回</Tag>}
      </Space>

      <Card style={{ marginBottom: 16 }}>
        <Descriptions column={3} size="small">
          <Descriptions.Item label="需求">
            {agents.preferences?.destination ? `${agents.preferences.destination} · ` : ""}
            原始需求
          </Descriptions.Item>
          <Descriptions.Item label="断点">{agents.resume_from || "-"}</Descriptions.Item>
          <Descriptions.Item label="预算">
            {agents.total_budget ? `¥${Number(agents.total_budget).toLocaleString()}` : "-"}
            {agents.budget_limit ? ` / 上限 ¥${Number(agents.budget_limit).toLocaleString()}` : ""}
          </Descriptions.Item>
          {agents.preferences?.days && (
            <Descriptions.Item label="天数">{agents.preferences.days} 天</Descriptions.Item>
          )}
          {agents.preferences?.party && (
            <Descriptions.Item label="出行人">
              {agents.preferences.party.adults} 大 {agents.preferences.party.children} 小
            </Descriptions.Item>
          )}
        </Descriptions>
      </Card>

      <Card>
        <Tabs items={tabItems} />
      </Card>
    </div>
  );
}
