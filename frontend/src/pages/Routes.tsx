import { useEffect, useState } from "react";
import { Button, Card, Col, InputNumber, message, Modal, Row, Space, Tag, Typography } from "antd";
import { ArrowLeftOutlined, EnvironmentOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { api, unwrap } from "../api/client";

// 经典线路：旅行社固定路线库，选模板秒出行程
export default function Routes() {
  const navigate = useNavigate();
  const [routes, setRoutes] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<any | null>(null);
  const [adults, setAdults] = useState(2);
  const [children, setChildren] = useState(0);
  const [elders, setElders] = useState(0);
  const [budget, setBudget] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    loadRoutes();
  }, []);

  const loadRoutes = async () => {
    setLoading(true);
    try {
      const data = await unwrap<any>(api.get("/routes"));
      setRoutes(data.items || []);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  const openDetail = async (id: number) => {
    try {
      const data = await unwrap<any>(api.get(`/routes/${id}`));
      setSelected(data);
    } catch (e: any) {
      message.error(e.message);
    }
  };

  const submit = async () => {
    if (!selected) return;
    setSubmitting(true);
    try {
      const data = await unwrap<any>(
        api.post("/plans/from-template", {
          template_id: selected.id,
          adults,
          children,
          elders,
          budget_limit: budget || undefined,
        })
      );
      message.success("行程已生成（秒出，无需等待 Agent）");
      setSelected(null);
      navigate(`/plans/${data.plan_id}`);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/")}>
          返回
        </Button>
        <Typography.Title level={4} style={{ margin: 0 }}>
          <ThunderboltOutlined style={{ marginRight: 8, color: "#faad14" }} />
          经典线路
        </Typography.Title>
        <Typography.Text type="secondary">旅行社固定线路库，选模板秒出行程，无需等待 Agent</Typography.Text>
      </Space>

      {loading ? (
        <Typography.Text type="secondary">加载中…</Typography.Text>
      ) : (
        <Row gutter={[16, 16]}>
          {routes.map((r) => (
            <Col key={r.id} xs={24} sm={12} lg={8}>
              <Card
                hoverable
                title={r.name}
                extra={<Tag color="blue">{r.days} 天</Tag>}
                onClick={() => openDetail(r.id)}
              >
                <Typography.Paragraph type="secondary" ellipsis={{ rows: 2 }}>
                  {r.description}
                </Typography.Paragraph>
                <Space wrap>
                  <Tag color="green">{r.destination}</Tag>
                  {(r.tags || []).map((t: string) => (
                    <Tag key={t}>{t}</Tag>
                  ))}
                </Space>
                <div style={{ marginTop: 8, fontSize: 13, color: "#595959" }}>
                  <EnvironmentOutlined /> {r.suitable_for || "通用"} · 参考 ¥{r.budget_ref}/人
                </div>
              </Card>
            </Col>
          ))}
        </Row>
      )}

      {/* 模板详情弹窗 */}
      <Modal
        open={!!selected}
        title={selected?.name}
        onCancel={() => setSelected(null)}
        footer={null}
        width={640}
      >
        {selected && (
          <div>
            <Typography.Paragraph type="secondary">{selected.description}</Typography.Paragraph>
            <Space wrap style={{ marginBottom: 12 }}>
              <Tag color="green">{selected.destination}</Tag>
              <Tag color="blue">{selected.days} 天</Tag>
              {selected.suitable_for && <Tag>{selected.suitable_for}</Tag>}
            </Space>

            {/* 每日行程预览 */}
            <Typography.Text strong>每日行程：</Typography.Text>
            <div style={{ marginTop: 8 }}>
              {(selected.daily_plan || []).map((d: any) => (
                <div key={d.day} style={{ marginBottom: 8, fontSize: 13 }}>
                  <Tag color="blue" style={{ marginRight: 8 }}>
                    第 {d.day} 天
                  </Tag>
                  {[d.morning, d.afternoon, d.evening].filter(Boolean).join(" → ")}
                  {d.meal && <span style={{ color: "#fa8c16" }}>（{d.meal}）</span>}
                </div>
              ))}
            </div>

            {/* 微调参数 */}
            <div style={{ marginTop: 16, borderTop: "1px solid #f0f0f0", paddingTop: 12 }}>
              <Typography.Text strong>出行人数（可微调）：</Typography.Text>
              <Space style={{ marginTop: 8 }} wrap>
                <span>成人</span>
                <InputNumber min={1} max={20} value={adults} onChange={(v) => setAdults(v || 1)} />
                <span>儿童</span>
                <InputNumber min={0} max={20} value={children} onChange={(v) => setChildren(v || 0)} />
                <span>老人</span>
                <InputNumber min={0} max={20} value={elders} onChange={(v) => setElders(v || 0)} />
                <span>预算(元)</span>
                <InputNumber min={1} max={100000} value={budget} onChange={(v) => setBudget(v)} placeholder="可选" />
              </Space>
            </div>

            <Button type="primary" block size="large" loading={submitting} onClick={submit} style={{ marginTop: 16 }}>
              <ThunderboltOutlined /> 立即生成行程（秒出）
            </Button>
          </div>
        )}
      </Modal>
    </div>
  );
}
