import { useState } from "react";
import {
  Button,
  Card,
  Col,
  Descriptions,
  InputNumber,
  message,
  Radio,
  Row,
  Space,
  Tag,
  Typography,
  Alert,
  Divider,
  Switch,
} from "antd";
import { ArrowLeftOutlined, TeamOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { api, unwrap } from "../api/client";

// 团建规划：独立于旅游的模式，核心是「场地+活动+餐饮+人均预算」
export default function TeamBuild() {
  const navigate = useNavigate();
  const [teamType, setTeamType] = useState("聚餐");
  const [people, setPeople] = useState(30);
  const [duration, setDuration] = useState(3);
  const [budget, setBudget] = useState<number | null>(5000);
  const [outdoor, setOutdoor] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any | null>(null);

  const types = [
    { value: "聚餐", label: "聚餐" },
    { value: "桌游轰趴", label: "桌游轰趴" },
    { value: "烧烤", label: "烧烤" },
    { value: "拓展", label: "拓展" },
    { value: "郊游", label: "郊游" },
    { value: "会议", label: "会议" },
  ];

  const submit = async () => {
    setLoading(true);
    try {
      const data = await unwrap<any>(
        api.post("/teambuild/plan", {
          team_type: teamType,
          people,
          duration_hours: duration,
          budget: budget || 0,
          outdoor,
        })
      );
      setResult(data);
      message.success("团建方案已生成");
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 800, margin: "0 auto" }}>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/")}>
          返回
        </Button>
        <Typography.Title level={4} style={{ margin: 0 }}>
          <TeamOutlined style={{ marginRight: 8, color: "#fa8c16" }} />
          团建规划
        </Typography.Title>
        <Tag color="orange">独立模式 · 秒出方案</Tag>
      </Space>

      <Card title="填写团建需求" style={{ marginBottom: 16 }}>
        <Row gutter={[16, 16]}>
          <Col span={24}>
            <Typography.Text strong>团建类型：</Typography.Text>
            <Radio.Group value={teamType} onChange={(e) => setTeamType(e.target.value)} style={{ marginTop: 8 }}>
              <Space wrap>
                {types.map((t) => (
                  <Radio.Button key={t.value} value={t.value}>
                    {t.label}
                  </Radio.Button>
                ))}
              </Space>
            </Radio.Group>
          </Col>
          <Col span={8}>
            <Typography.Text strong>人数：</Typography.Text>
            <InputNumber min={1} max={500} value={people} onChange={(v) => setPeople(v || 1)} style={{ width: "100%", marginTop: 8 }} />
          </Col>
          <Col span={8}>
            <Typography.Text strong>时长（小时）：</Typography.Text>
            <InputNumber min={0.5} max={12} step={0.5} value={duration} onChange={(v) => setDuration(v || 1)} style={{ width: "100%", marginTop: 8 }} />
          </Col>
          <Col span={8}>
            <Typography.Text strong>总预算（元，可空）：</Typography.Text>
            <InputNumber min={0} max={1000000} value={budget} onChange={(v) => setBudget(v)} placeholder="不限" style={{ width: "100%", marginTop: 8 }} />
          </Col>
          <Col span={24}>
            <Space>
              <Typography.Text strong>偏好户外：</Typography.Text>
              <Switch checked={outdoor} onChange={setOutdoor} />
            </Space>
          </Col>
        </Row>
        <Button type="primary" size="large" block icon={<ThunderboltOutlined />} loading={loading} onClick={submit} style={{ marginTop: 20 }}>
          立即生成团建方案
        </Button>
      </Card>

      {result && (
        <Card title={`团建方案：${result.team_type}（${result.people} 人 · ${result.duration_hours} 小时）`}>
          <Alert type="info" showIcon message={result.note} style={{ marginBottom: 16 }} />

          {/* 场地 */}
          <Typography.Text strong>🏢 推荐场地：</Typography.Text>
          <div style={{ marginTop: 8, marginBottom: 16 }}>
            <Space wrap>
              {result.venues.map((v: string) => (
                <Tag key={v} color="blue">{v}</Tag>
              ))}
            </Space>
          </div>

          {/* 活动 */}
          <Typography.Text strong>🎯 活动项目：</Typography.Text>
          <div style={{ marginTop: 8, marginBottom: 16 }}>
            <Space wrap>
              {result.activities.map((a: string) => (
                <Tag key={a} color="green">{a}</Tag>
              ))}
            </Space>
          </div>

          {/* 餐饮 */}
          <Typography.Text strong>🍽️ 餐饮方案：</Typography.Text>
          <Typography.Paragraph style={{ marginTop: 8 }}>{result.food}</Typography.Paragraph>

          {/* 时间安排 */}
          <Divider />
          <Typography.Text strong>⏰ 时间安排：</Typography.Text>
          <div style={{ marginTop: 8 }}>
            {result.schedule.map((s: string, i: number) => (
              <div key={i} style={{ fontSize: 13, lineHeight: 1.8 }}>{s}</div>
            ))}
          </div>

          {/* 预算明细 */}
          <Divider />
          <Typography.Text strong>💰 预算明细：</Typography.Text>
          <Descriptions column={2} size="small" style={{ marginTop: 12 }}>
            <Descriptions.Item label="场地费">{result.budget.venue} 元</Descriptions.Item>
            <Descriptions.Item label="餐饮费">{result.budget.food} 元</Descriptions.Item>
            <Descriptions.Item label="活动费">{result.budget.activity} 元</Descriptions.Item>
            <Descriptions.Item label="人均">
              <Typography.Text strong style={{ color: "#fa8c16" }}>
                ¥{result.budget.per_person}/人
              </Typography.Text>
            </Descriptions.Item>
            <Descriptions.Item label="总费用">
              <Typography.Text strong>¥{result.budget.total}</Typography.Text>
            </Descriptions.Item>
            {result.budget.budget_limit > 0 && (
              <Descriptions.Item label="预算上限">¥{result.budget.budget_limit}</Descriptions.Item>
            )}
          </Descriptions>

          {result.budget.over ? (
            <Alert
              type="warning"
              showIcon
              style={{ marginTop: 12 }}
              message={`超出预算 ${(result.budget.over_ratio * 100).toFixed(0)}%，可减少人数或换类型`}
            />
          ) : result.budget.budget_limit > 0 ? (
            <Alert type="success" showIcon style={{ marginTop: 12 }} message="预算内，方案可行" />
          ) : null}

          {result.tips?.length > 0 && (
            <div style={{ marginTop: 12 }}>
              {result.tips.map((t: string, i: number) => (
                <Typography.Text key={i} type="warning" style={{ display: "block", fontSize: 12 }}>
                  💡 {t}
                </Typography.Text>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
