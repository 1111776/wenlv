import { useState } from "react";
import {
  Button,
  Card,
  Col,
  DatePicker,
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
import dayjs from "dayjs";
import { api, unwrap } from "../api/client";

// 新建行程：引导式表单
export default function PlanNew() {
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const [autoDays, setAutoDays] = useState<number | null>(null);

  // 监听日期变化，自动算天数
  const onDateChange = () => {
    const start = form.getFieldValue("start_date");
    const end = form.getFieldValue("end_date");
    if (start && end) {
      const days = end.diff(start, "day") + 1;
      if (days > 0) {
        setAutoDays(days);
        form.setFieldsValue({ days: days });
      }
    }
  };

  const onSubmit = async (values: any) => {
    setLoading(true);
    try {
      const payload: any = {
        query: values.query,
        origin: values.origin,
        destination: values.destination,
        days: values.days,
        budget_limit: values.budget_limit,
        tags: values.tags || [],
      };
      // 日期转字符串（后端存 YYYY-MM-DD）
      if (values.start_date) payload.start_date = values.start_date.format("YYYY-MM-DD");
      if (values.end_date) payload.end_date = values.end_date.format("YYYY-MM-DD");
      if (values.adults || values.children || values.elders) {
        payload.party = {
          adults: values.adults || 1,
          children: values.children || 0,
          elders: values.elders || 0,
          elder_status: values.elder_status || null,
        };
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
                <Form.Item name="origin" label="出发地">
                  <Input placeholder="例如：北京" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="destination" label="目的地">
                  <Input placeholder="云南" />
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
                <Form.Item name="start_date" label="出发日期">
                  <DatePicker style={{ width: "100%" }} onChange={onDateChange} placeholder="选择出发日期" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="end_date" label="返程日期">
                  <DatePicker style={{ width: "100%" }} onChange={onDateChange} placeholder="选择返程日期" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="days" label="天数（选日期自动算）">
                  <InputNumber min={1} max={30} style={{ width: "100%" }} placeholder="7" />
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
                <Form.Item name="elders" label="老人">
                  <InputNumber min={0} max={20} style={{ width: "100%" }} placeholder="0" />
                </Form.Item>
              </Col>
            </Row>

            <Row gutter={16}>
              <Col span={8}>
                <Form.Item name="elder_status" label="老人生活状态">
                  <Select
                    allowClear
                    placeholder="选择状态（可选）"
                    options={[
                      { value: "健康", label: "健康" },
                      { value: "行动不便", label: "行动不便" },
                      { value: "需轮椅", label: "需轮椅" },
                      { value: "慢病需注意", label: "慢病需注意" },
                      { value: "需常休息", label: "需常休息" },
                    ]}
                  />
                </Form.Item>
              </Col>
              <Col span={16}>
                <Form.Item name="tags" label="兴趣爱好（自由填写）">
                  <Select
                    mode="tags"
                    placeholder="输入后回车，可填任意兴趣，如：滑雪 / 摄影 / 温泉 / 徒步"
                    tokenSeparators={[",", "，"]}
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
