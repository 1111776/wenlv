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
  Switch,
  Typography,
  Alert,
} from "antd";
import { RocketOutlined, ArrowLeftOutlined, PlusOutlined, MinusCircleOutlined } from "@ant-design/icons";
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
      // query 不再由用户手填，自动按表单字段拼一个（后端 Intake 解析 + 记忆抽取用）
      const _children = (values.children_detail || []).length || values.children || 0;
      const _elders = (values.elders_detail || []).length || values.elders || 0;
      const queryParts: string[] = [];
      if (values.origin && values.destination) queryParts.push(`从${values.origin}到${values.destination}`);
      else if (values.destination) queryParts.push(`${values.destination}游`);
      if (values.days) queryParts.push(`${values.days}天`);
      queryParts.push(`${values.adults || 1}大${_children}小${_elders}老`);
      if (values.budget_limit) queryParts.push(`预算${values.budget_limit}`);
      if (values.tags && values.tags.length) queryParts.push(values.tags.join(" "));
      const query = queryParts.join("，");

      const payload: any = {
        query,
        origin: values.origin,
        destination: values.destination,
        days: values.days,
        budget_limit: values.budget_limit,
        tags: values.tags || [],
        ticket_purchase_mode: values.ticket_purchase_mode || null,
        hotel_booking_mode: values.hotel_booking_mode || null,
      };
      // 日期转字符串（后端存 YYYY-MM-DD）
      if (values.start_date) payload.start_date = values.start_date.format("YYYY-MM-DD");
      if (values.end_date) payload.end_date = values.end_date.format("YYYY-MM-DD");
      if (values.adults || values.children || values.elders) {
        const eldersDetail = (values.elders_detail || []).map((e: any) => ({
          age: e.age || 0,
          gender: e.gender || "男",
        }));
        const childrenDetail = (values.children_detail || []).map((c: any) => ({
          age: c.age || 0,
          height: c.height ?? null,
          seat: !!c.seat,
        }));
        const studentsDetail = (values.students_detail || []).map((s: any) => ({
          level: s.level || "大学本科",
        }));
        const elders = values.elders || eldersDetail.length || 0;
        const children = childrenDetail.length || values.children || 0;
        const students = studentsDetail.length || values.students || 0;
        payload.party = {
          adults: values.adults || 1,
          children,
          elders,
          students,
          elder_status: values.elder_status || null,
          adult_relation: values.adult_relation || null,
          elders_detail: eldersDetail,
          children_detail: childrenDetail,
          students_detail: studentsDetail,
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
                  <InputNumber min={1} max={35000} style={{ width: "100%" }} placeholder="15000" />
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
              <Col span={12}>
                <Form.Item name="ticket_purchase_mode" label="购票方式">
                  <Select
                    allowClear
                    placeholder="选择购票方式（可选）"
                    options={[
                      { value: "bundle", label: "一次性买票" },
                      { value: "separate", label: "分开买票" },
                    ]}
                  />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="hotel_booking_mode" label="酒店预订方式">
                  <Select
                    allowClear
                    placeholder="选择酒店预订方式（可选）"
                    options={[
                      { value: "bundle", label: "一次性订" },
                      { value: "separate", label: "分开订" },
                    ]}
                  />
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
                <Form.Item name="children" label="儿童数量" extra="下方按年龄/身高逐个添加">
                  <InputNumber min={0} max={20} style={{ width: "100%" }} placeholder="1" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="elders" label="老人数量" extra="下方按年龄/性别逐个添加">
                  <InputNumber min={0} max={20} style={{ width: "100%" }} placeholder="0" />
                </Form.Item>
              </Col>
            </Row>

            <Row gutter={16}>
              <Col span={8}>
                <Form.Item name="students" label="学生数量" extra="下方按学历逐个添加">
                  <InputNumber min={0} max={20} style={{ width: "100%" }} placeholder="0" />
                </Form.Item>
              </Col>
            </Row>

            <Form.List name="students_detail">
              {(fields, { add, remove }) => (
                <>
                  <Typography.Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
                    学生信息（学历：高铁学生票仅限全日制大中专中小学的家校往返，旅游出行不适用）
                  </Typography.Text>
                  {fields.map(({ key, name, ...restField }) => (
                    <Space key={key} align="baseline" style={{ display: "flex", marginBottom: 8 }}>
                      <Form.Item
                        {...restField}
                        name={[name, "level"]}
                        rules={[{ required: true, message: "选学历" }]}
                        style={{ marginBottom: 0 }}
                      >
                        <Select
                          placeholder="学历"
                          style={{ width: 180 }}
                          options={[
                            { value: "小学", label: "小学" },
                            { value: "初中", label: "初中" },
                            { value: "高中", label: "高中" },
                            { value: "中专", label: "中专" },
                            { value: "大专", label: "大专" },
                            { value: "大学本科", label: "大学本科" },
                            { value: "硕士研究生", label: "硕士研究生" },
                            { value: "博士研究生", label: "博士研究生" },
                          ]}
                        />
                      </Form.Item>
                      <MinusCircleOutlined onClick={() => remove(name)} />
                    </Space>
                  ))}
                  <Button type="dashed" onClick={() => add({ level: "大学本科" })} icon={<PlusOutlined />} block>
                    添加一位学生
                  </Button>
                </>
              )}
            </Form.List>

            <Form.List name="children_detail">
              {(fields, { add, remove }) => (
                <>
                  <Typography.Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
                    儿童信息（年龄/身高决定门票：6周岁以下或身高1.2米以下免首道大门票，6-18周岁半价；占座影响高铁/火车购票：6岁以下不占座可免票，占座需儿童优惠票）
                  </Typography.Text>
                  {fields.map(({ key, name, ...restField }) => (
                    <Space key={key} align="baseline" style={{ display: "flex", marginBottom: 8 }}>
                      <Form.Item
                        {...restField}
                        name={[name, "age"]}
                        rules={[{ required: true, message: "填年龄" }]}
                        style={{ marginBottom: 0 }}
                      >
                        <InputNumber min={0} max={17} placeholder="年龄(周岁)" style={{ width: 120 }} />
                      </Form.Item>
                      <Form.Item
                        {...restField}
                        name={[name, "height"]}
                        style={{ marginBottom: 0 }}
                      >
                        <InputNumber min={0} max={2.5} step={0.01} placeholder="身高(米,可选)" style={{ width: 140 }} />
                      </Form.Item>
                      <Form.Item
                        {...restField}
                        name={[name, "seat"]}
                        valuePropName="checked"
                        style={{ marginBottom: 0 }}
                      >
                        <Switch checkedChildren="占座" unCheckedChildren="不占座" />
                      </Form.Item>
                      <MinusCircleOutlined onClick={() => remove(name)} />
                    </Space>
                  ))}
                  <Button type="dashed" onClick={() => add({ age: 6, height: 1.2, seat: false })} icon={<PlusOutlined />} block>
                    添加一位儿童
                  </Button>
                </>
              )}
            </Form.List>

            <Form.List name="elders_detail">
              {(fields, { add, remove }) => (
                <>
                  <Typography.Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
                    老人信息（年龄决定门票：60-64 半价，65 及以上免首道大门票，需身份证原件）
                  </Typography.Text>
                  {fields.map(({ key, name, ...restField }) => (
                    <Space key={key} align="baseline" style={{ display: "flex", marginBottom: 8 }}>
                      <Form.Item
                        {...restField}
                        name={[name, "age"]}
                        rules={[{ required: true, message: "填年龄" }]}
                        style={{ marginBottom: 0 }}
                      >
                        <InputNumber min={0} max={120} placeholder="年龄" style={{ width: 100 }} />
                      </Form.Item>
                      <Form.Item
                        {...restField}
                        name={[name, "gender"]}
                        rules={[{ required: true, message: "选性别" }]}
                        style={{ marginBottom: 0 }}
                      >
                        <Select
                          placeholder="性别"
                          style={{ width: 90 }}
                          options={[
                            { value: "男", label: "男" },
                            { value: "女", label: "女" },
                          ]}
                        />
                      </Form.Item>
                      <MinusCircleOutlined onClick={() => remove(name)} />
                    </Space>
                  ))}
                  <Button type="dashed" onClick={() => add({ age: 60, gender: "男" })} icon={<PlusOutlined />} block>
                    添加一位老人
                  </Button>
                </>
              )}
            </Form.List>

            <Row gutter={16}>
              <Col span={8}>
                <Form.Item name="adult_relation" label="成人关系">
                  <Select
                    allowClear
                    placeholder="选择关系（可选）"
                    options={[
                      { value: "情侣", label: "情侣" },
                      { value: "单身", label: "单身" },
                      { value: "未婚", label: "未婚" },
                      { value: "已婚", label: "已婚" },
                      { value: "家庭", label: "家庭" },
                      { value: "朋友", label: "朋友" },
                      { value: "同事", label: "同事" },
                    ]}
                  />
                </Form.Item>
              </Col>
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
              <Col span={8}>
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
