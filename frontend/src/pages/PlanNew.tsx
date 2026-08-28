import { useState } from "react";
import {
  Button,
  Card,
  Col,
  Form,
  Input,
  InputNumber,
  message,
  Row,
  Select,
  Space,
  Steps,
  Typography,
  Alert,
} from "antd";
import { RocketOutlined, ArrowLeftOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { api, unwrap } from "../api/client";

// 新建行程：引导式表单
export default function PlanNew() {
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [createdId, setCreatedId] = useState<string | null>(null);

  const onSubmit = async (values: any) => {
    setLoading(true);
    try {
      const payload: any = {
        query: values.query,
        destination: values.destination,
        days: values.days,
        budget_limit: values.budget_limit,
        tags: values.tags || [],
      };
      if (values.adults || values.children) {
        payload.party = { adults: values.adults || 1, children: values.children || 0 };
      }
      const data = await unwrap<any>(api.post("/plans", payload));
      setCreatedId(data.plan_id);
      message.success("行程已提交，Agent 团队开始工作");
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 720, margin: "0 auto" }}>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/plans")}>
          返回列表
        </Button>
        <Typography.Title level={4} style={{ margin: 0 }}>
          新建行程
        </Typography.Title>
      </Space>

      <Steps
        style={{ marginBottom: 24 }}
        size="small"
        current={0}
        items={[
          { title: "填写需求" },
          { title: "Agent 自动调研" },
          { title: "生成行程报告" },
        ]}
      />

      {createdId ? (
        <Card>
          <Alert
            type="success"
            showIcon
            message="行程创建成功！"
            description={`行程 ID：${createdId}。8 个 Agent 正在协作处理，您可以前往行程列表实时查看进度。`}
            action={
              <Space direction="vertical">
                <Button type="primary" onClick={() => navigate(`/plans/${createdId}`)}>
                  查看实时进度
                </Button>
                <Button onClick={() => navigate("/plans")}>返回列表</Button>
              </Space>
            }
          />
        </Card>
      ) : (
        <Card>
          <Form form={form} layout="vertical" onFinish={onSubmit}>
            <Form.Item
              name="query"
              label={
                <Space>
                  需求描述
                  <Typography.Text type="secondary">（必填，一句话描述你的旅行需求）</Typography.Text>
                </Space>
              }
              rules={[{ required: true, message: "请输入需求描述" }]}
            >
              <Input.TextArea
                rows={4}
                placeholder="例如：7天云南家庭游，2大1小，预算15000，偏自然风光，少购物"
              />
            </Form.Item>

            <Row gutter={16}>
              <Col span={8}>
                <Form.Item name="destination" label="目的地">
                  <Input placeholder="云南" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="days" label="天数">
                  <InputNumber min={1} max={30} style={{ width: "100%" }} placeholder="7" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="budget_limit" label="预算上限（元）">
                  <InputNumber min={1} style={{ width: "100%" }} placeholder="15000" />
                </Form.Item>
              </Col>
            </Row>

            <Row gutter={16}>
              <Col span={8}>
                <Form.Item name="adults" label="成人">
                  <InputNumber min={1} max={20} style={{ width: "100%" }} placeholder="2" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="children" label="儿童">
                  <InputNumber min={0} max={20} style={{ width: "100%" }} placeholder="1" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="tags" label="兴趣标签">
                  <Select
                    mode="tags"
                    placeholder="自然风光 / 美食 / 亲子"
                    options={[
                      { value: "自然风光", label: "自然风光" },
                      { value: "人文历史", label: "人文历史" },
                      { value: "美食", label: "美食" },
                      { value: "亲子", label: "亲子" },
                      { value: "少购物", label: "少购物" },
                    ]}
                  />
                </Form.Item>
              </Col>
            </Row>

            <Button type="primary" htmlType="submit" size="large" block icon={<RocketOutlined />} loading={loading}>
              提交给 Agent 团队
            </Button>
          </Form>
        </Card>
      )}
    </div>
  );
}
