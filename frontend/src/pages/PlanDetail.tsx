import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Button,
  Card,
  Col,
  Descriptions,
  Image,
  Input,
  message,
  Modal,
  Progress,
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
  EditOutlined,
  PlusOutlined,
  DeleteOutlined,
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

// 格式化路线数据（距离/耗时）
function fmtRoute(route: any): string {
  if (!route) return "";
  const km = (route.distance / 1000).toFixed(1);
  const min = Math.round(route.duration / 60);
  return `${km}km · 约${min}分钟`;
}

// 单个景点的展示项（图片 + 名称 + 地址 + 营业时间 + 到下一点路线）
function SpotItem({ spot, tagColor, tagText }: { spot: any; tagColor: string; tagText: string }) {
  return (
    <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
      {spot.photo && (
        <Image
          src={spot.photo}
          alt={spot.spot}
          width={110}
          height={74}
          style={{ borderRadius: 8, objectFit: "cover", flexShrink: 0, border: "1px solid #f0f0f0" }}
        />
      )}
      <div style={{ flex: 1 }}>
        <Space size={8} wrap>
          <Tag color={tagColor} style={{ marginRight: 0 }}>{tagText}</Tag>
          <Typography.Text strong style={{ fontSize: 14 }}>{spot.spot}</Typography.Text>
          {spot.rating && (
            <Tag color="gold" style={{ marginRight: 0 }}>⭐ {spot.rating}</Tag>
          )}
        </Space>
        {spot.address && (
          <div style={{ color: "#8c8c8c", fontSize: 12, marginTop: 4 }}>
            📍 {spot.address}
          </div>
        )}
        {spot.opentime && (
          <div style={{ color: "#d48806", fontSize: 12, marginTop: 2 }}>
            🕐 营业时间：{spot.opentime}
          </div>
        )}
        {spot.route && (
          <div style={{ color: "#1677ff", fontSize: 12, marginTop: 2 }}>
            🚗 至下一点：{fmtRoute(spot.route)}
          </div>
        )}
      </div>
    </div>
  );
}

// 餐饮项展示
function MealItem({ label, meal }: { label: string; meal: any }) {
  return (
    <div style={{ display: "flex", gap: 10, alignItems: "flex-start", minWidth: 220 }}>
      {meal.photo && (
        <Image
          src={meal.photo}
          alt={meal.name}
          width={80}
          height={56}
          style={{ borderRadius: 8, objectFit: "cover", flexShrink: 0, border: "1px solid #f0f0f0" }}
        />
      )}
      <div style={{ flex: 1 }}>
        <Space size={4}>
          <Tag color="gold" style={{ marginRight: 0 }}>{label}</Tag>
          <Typography.Text strong style={{ fontSize: 13 }}>{meal.name}</Typography.Text>
          {meal.rating && <Tag color="gold" style={{ marginRight: 0 }}>⭐ {meal.rating}</Tag>}
        </Space>
        {meal.address && (
          <div style={{ color: "#8c8c8c", fontSize: 12, marginTop: 2 }}>📍 {meal.address}</div>
        )}
        {meal.opentime && (
          <div style={{ color: "#d48806", fontSize: 12, marginTop: 2 }}>🕐 {meal.opentime}</div>
        )}
      </div>
    </div>
  );
}

// 行程详情：Agent 流程 + 网页任务 + 预算 + 报告 + 实时推送
export default function PlanDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [agents, setAgents] = useState<any>(null);
  const [planFile, setPlanFile] = useState<string>("");
  const [report, setReport] = useState<any>(null);
  const [lastEvent, setLastEvent] = useState<string>("");
  const [editOpen, setEditOpen] = useState(false);
  const [editPlan, setEditPlan] = useState<any[]>([]);
  const [saving, setSaving] = useState(false);

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

  // 打开编辑：深拷贝当前 daily_plan
  const openEdit = () => {
    const dp = agents?.itinerary?.daily_plan || [];
    setEditPlan(JSON.parse(JSON.stringify(dp)));
    setEditOpen(true);
  };

  // 保存修改：提交完整 daily_plan
  const saveEdit = async () => {
    setSaving(true);
    try {
      await unwrap(api.patch(`/plans/${id}/itinerary`, { daily_plan: editPlan }));
      message.success("行程已修改");
      setEditOpen(false);
      load();
    } catch (e: any) {
      message.error(e.message || "保存失败");
    } finally {
      setSaving(false);
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
          {/* 编辑按钮 */}
          <div style={{ marginBottom: 16, display: "flex", justifyContent: "flex-end" }}>
            <Button type="primary" icon={<EditOutlined />} onClick={openEdit}>
              编辑行程
            </Button>
          </div>
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
                    children: <SpotItem spot={day.morning} tagColor="blue" tagText="上午" />,
                  },
                  {
                    color: "green",
                    dot: <EnvironmentOutlined />,
                    children: <SpotItem spot={day.afternoon} tagColor="green" tagText="下午" />,
                  },
                  {
                    color: "purple",
                    dot: <EnvironmentOutlined />,
                    children: <SpotItem spot={day.evening} tagColor="purple" tagText="晚上" />,
                  },
                ]}
              />
              {/* 餐饮安排 */}
              {day.meals && (
                <Card
                  size="small"
                  style={{ marginTop: 12, background: "#fffbe6", border: "1px solid #ffe58f" }}
                >
                  <Typography.Text strong style={{ color: "#d48806" }}>
                    🍽️ 餐饮安排
                  </Typography.Text>
                  <div style={{ marginTop: 8, display: "flex", gap: 24, flexWrap: "wrap" }}>
                    {day.meals.breakfast && (
                      <MealItem label="早餐" meal={day.meals.breakfast} />
                    )}
                    {day.meals.lunch && (
                      <MealItem label="午餐" meal={day.meals.lunch} />
                    )}
                    {day.meals.dinner && (
                      <MealItem label="晚餐" meal={day.meals.dinner} />
                    )}
                  </div>
                </Card>
              )}
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
      children: <StatusBoard agents={agents} />,
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
              {agents.preferences.party.elders ? ` ${agents.preferences.party.elders} 老` : ""}
            </Descriptions.Item>
          )}
          {agents.preferences?.party?.elder_status && (
            <Descriptions.Item label="老人状态">
              {agents.preferences.party.elder_status}
            </Descriptions.Item>
          )}
        </Descriptions>
      </Card>

      <Card>
        <Tabs items={tabItems} />
      </Card>

      {/* 编辑行程 Modal */}
      <Modal
        title="编辑行程计划"
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={saveEdit}
        okText="保存修改"
        confirmLoading={saving}
        width={760}
      >
        <Typography.Paragraph type="secondary">
          删除不想要的景点，或在某一天添加新的景点（名称 + 地址），保存后立即生效，无需重新生成。
        </Typography.Paragraph>
        {editPlan.map((day: any, di: number) => (
          <Card
            key={di}
            size="small"
            title={`第 ${day.day} 天`}
            style={{ marginBottom: 12 }}
            extra={
              <Button
                size="small"
                type="dashed"
                icon={<PlusOutlined />}
                onClick={() => {
                  const newPlan = [...editPlan];
                  const segs = ["morning", "afternoon", "evening"];
                  // 找一个空位添加，默认加上午
                  newPlan[di].morning = {
                    spot: "新景点",
                    address: "",
                    type: "",
                    route: null,
                    opentime: "",
                    rating: "",
                    photo: "",
                  };
                  setEditPlan(newPlan);
                }}
              >
                加景点
              </Button>
            }
          >
            {["morning", "afternoon", "evening"].map((seg) => {
              const spot = day[seg];
              if (!spot || !spot.spot) return null;
              return (
                <div
                  key={seg}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "6px 0",
                    borderBottom: "1px solid #f5f5f5",
                  }}
                >
                  <Tag style={{ width: 48, textAlign: "center", marginRight: 0 }}>
                    {seg === "morning" ? "上午" : seg === "afternoon" ? "下午" : "晚上"}
                  </Tag>
                  <Input
                    size="small"
                    value={spot.spot}
                    onChange={(e) => {
                      const np = [...editPlan];
                      np[di][seg].spot = e.target.value;
                      setEditPlan(np);
                    }}
                    style={{ width: 220 }}
                  />
                  <Input
                    size="small"
                    value={spot.address}
                    placeholder="地址（可选）"
                    onChange={(e) => {
                      const np = [...editPlan];
                      np[di][seg].address = e.target.value;
                      setEditPlan(np);
                    }}
                    style={{ flex: 1 }}
                  />
                  <Button
                    size="small"
                    danger
                    type="text"
                    icon={<DeleteOutlined />}
                    onClick={() => {
                      const np = [...editPlan];
                      np[di][seg] = { spot: "", address: "", type: "", route: null, opentime: "", rating: "", photo: "" };
                      setEditPlan(np);
                    }}
                  />
                </div>
              );
            })}
          </Card>
        ))}
      </Modal>
    </div>
  );
}

// 人类可读的状态看板：进度条 + Agent 步骤 + 数据统计
function StatusBoard({ agents }: { agents: any }) {
  const agentList = agents?.agents || [];
  const tasks = agents?.tasks || [];
  const itinerary = agents?.itinerary;

  // 整体进度：已完成任务数 / 总任务数
  const doneCount = tasks.filter((t: any) => t.status === "completed" || t.status === "blocked").length;
  const totalCount = tasks.length || 0;
  const percent = totalCount > 0 ? Math.round((doneCount / totalCount) * 100) : 0;

  // 状态 → 中文 + 颜色
  const STATUS_TEXT: Record<string, string> = {
    completed: "已完成",
    running: "进行中",
    pending: "待执行",
    waiting: "等待审核",
    reviewing: "审核中",
    rejected: "已驳回",
    skipped: "已跳过",
  };
  const STATUS_COLOR: Record<string, string> = {
    completed: "success",
    running: "processing",
    pending: "default",
    waiting: "warning",
    reviewing: "warning",
    rejected: "error",
    skipped: "default",
  };

  const doneAgents = agentList.filter((a: any) => a.status === "completed").length;

  return (
    <div>
      {/* 总进度 */}
      <Card style={{ marginBottom: 16, background: "#f0f7ff" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <Typography.Text strong style={{ fontSize: 16 }}>
              当前进度：{agents?.status === "completed" ? "已完成" : agents?.status === "suspended" ? "待人工审核" : "执行中"}
            </Typography.Text>
            <Typography.Paragraph style={{ color: "#8c8c8c", margin: "4px 0 0" }}>
              已完成 {doneAgents}/8 个环节，调研 {doneCount}/{totalCount} 个任务
            </Typography.Paragraph>
          </div>
          <div style={{ width: 200 }}>
            <Progress percent={percent} status={agents?.status === "completed" ? "success" : "active"} />
          </div>
        </div>
      </Card>

      {/* 8 个 Agent 步骤 */}
      <Card title="8 个 Agent 执行步骤" style={{ marginBottom: 16 }}>
        <Row gutter={[12, 12]}>
          {agentList.map((a: any) => (
            <Col span={6} key={a.key}>
              <div
                style={{
                  padding: 12,
                  borderRadius: 8,
                  border: "1px solid #f0f0f0",
                  background: a.status === "completed" ? "#f6ffed" : a.status === "running" ? "#e6f0ff" : "#fff",
                }}
              >
                <div style={{ fontSize: 18, marginBottom: 6 }}>{a.icon}</div>
                <Typography.Text strong style={{ fontSize: 13 }}>{a.name}</Typography.Text>
                <div style={{ marginTop: 4 }}>
                  <Tag color={STATUS_COLOR[a.status] || "default"}>
                    {STATUS_TEXT[a.status] || a.status}
                  </Tag>
                </div>
              </div>
            </Col>
          ))}
        </Row>
      </Card>

      {/* 调研数据统计 */}
      <Card title="调研成果" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={8}>
            <div style={{ textAlign: "center", padding: 12, background: "#fafafa", borderRadius: 8 }}>
              <div className="stat-number" style={{ color: "#1677ff" }}>
                {itinerary?.poi_count ?? 0}
              </div>
              <div style={{ color: "#8c8c8c", fontSize: 13 }}>调研景点数</div>
            </div>
          </Col>
          <Col span={8}>
            <div style={{ textAlign: "center", padding: 12, background: "#fafafa", borderRadius: 8 }}>
              <div className="stat-number" style={{ color: "#faad14" }}>
                {itinerary?.restaurant_count ?? 0}
              </div>
              <div style={{ color: "#8c8c8c", fontSize: 13 }}>调研餐厅数</div>
            </div>
          </Col>
          <Col span={8}>
            <div style={{ textAlign: "center", padding: 12, background: "#fafafa", borderRadius: 8 }}>
              <div className="stat-number" style={{ color: "#52c41a" }}>
                {itinerary?.days ?? "-"}
              </div>
              <div style={{ color: "#8c8c8c", fontSize: 13 }}>行程天数</div>
            </div>
          </Col>
        </Row>
      </Card>

      {/* 已调研的景点列表 */}
      <Card title={`已调研的景点（${tasks.filter((t: any) => t.status === "completed").length} 个）`}>
        {tasks.filter((t: any) => t.status === "completed").length === 0 ? (
          <Typography.Text type="secondary">暂无已完成的调研</Typography.Text>
        ) : (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {tasks
              .filter((t: any) => t.status === "completed")
              .map((t: any) => (
                <Tag key={t.page_no} color="blue" style={{ fontSize: 13, padding: "4px 10px" }}>
                  {t.title}
                </Tag>
              ))}
          </div>
        )}
      </Card>
    </div>
  );
}
