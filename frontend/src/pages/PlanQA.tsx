import { useState } from "react";
import {
  Button,
  Card,
  Col,
  Input,
  InputNumber,
  message,
  Row,
  Select,
  Space,
  Steps,
  Switch,
  Tag,
  Typography,
  Alert,
  Divider,
} from "antd";
import {
  RocketOutlined,
  ArrowLeftOutlined,
  LeftOutlined,
  RightOutlined,
  PlusOutlined,
  MinusCircleOutlined,
  CheckOutlined,
  CommentOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { api, unwrap } from "../api/client";

// 问答式创建行程：一步一步提问，最后汇总提交
export default function PlanQA() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [createdId, setCreatedId] = useState<string | null>(null);

  // 各步答案
  const [origin, setOrigin] = useState("");
  const [destination, setDestination] = useState("");
  const [days, setDays] = useState<number | null>(null);
  const [budget, setBudget] = useState<number | null>(null);
  const [adults, setAdults] = useState<number | null>(2);
  const [children, setChildren] = useState(0);
  const [childrenDetail, setChildrenDetail] = useState<any[]>([]);
  const [elders, setElders] = useState(0);
  const [eldersDetail, setEldersDetail] = useState<any[]>([]);
  const [elderStatus, setElderStatus] = useState<string | undefined>(undefined);
  const [students, setStudents] = useState(0);
  const [studentsDetail, setStudentsDetail] = useState<any[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [adultRelation, setAdultRelation] = useState<string | undefined>(undefined);
  const [ticketMode, setTicketMode] = useState<string | undefined>(undefined);
  const [hotelMode, setHotelMode] = useState<string | undefined>(undefined);

  const steps = [
    { title: "出发地" },
    { title: "目的地" },
    { title: "天数" },
    { title: "预算" },
    { title: "成人" },
    { title: "儿童" },
    { title: "老人" },
    { title: "学生" },
    { title: "偏好" },
    { title: "确认" },
  ];

  const resizeDetail = (arr: any[], n: number, template: any) => {
    const next = [...arr];
    while (next.length < n) next.push({ ...template });
    while (next.length > n) next.pop();
    return next;
  };

  const canNext = () => {
    switch (step) {
      case 1:
        return !!destination.trim();
      case 4:
        return (adults || 0) >= 1;
      default:
        return true;
    }
  };

  const next = () => {
    if (!canNext()) {
      message.warning("请先填写必要信息");
      return;
    }
    setStep((s) => Math.min(s + 1, steps.length - 1));
  };
  const prev = () => setStep((s) => Math.max(s - 1, 0));

  const onSubmit = async () => {
    setLoading(true);
    try {
      const _children = childrenDetail.length || children;
      const _elders = eldersDetail.length || elders;
      const _students = studentsDetail.length || students;

      const queryParts: string[] = [];
      if (origin && destination) queryParts.push(`从${origin}到${destination}`);
      else if (destination) queryParts.push(`${destination}游`);
      if (days) queryParts.push(`${days}天`);
      queryParts.push(`${adults || 1}大${_children}小${_elders}老`);
      if (budget) queryParts.push(`预算${budget}`);
      if (tags.length) queryParts.push(tags.join(" "));
      const query = queryParts.join("，");

      const payload: any = {
        query,
        origin: origin || null,
        destination: destination || null,
        days: days || undefined,
        budget_limit: budget || undefined,
        tags,
        ticket_purchase_mode: ticketMode || null,
        hotel_booking_mode: hotelMode || null,
        party: {
          adults: adults || 1,
          children: _children,
          elders: _elders,
          students: _students,
          elder_status: elderStatus || null,
          adult_relation: adultRelation || null,
          elders_detail: eldersDetail,
          children_detail: childrenDetail,
          students_detail: studentsDetail,
        },
      };

      const data = await unwrap<any>(api.post("/plans", payload));
      setCreatedId(data.plan_id);
      message.success("行程已提交，Agent 团队开始工作");
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  if (createdId) {
    return (
      <div style={{ maxWidth: 720, margin: "0 auto" }}>
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
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 720, margin: "0 auto" }}>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/plans")}>
          返回列表
        </Button>
        <Typography.Title level={4} style={{ margin: 0 }}>
          <CommentOutlined style={{ marginRight: 8, color: "#1677ff" }} />
          问答式创建行程
        </Typography.Title>
      </Space>

      <Steps
        style={{ marginBottom: 24 }}
        size="small"
        current={step}
        items={steps}
      />

      <Card>
        {/* 第 1 步：出发地 */}
        {step === 0 && (
          <QABlock
            title="从哪里出发？"
            subtitle="填写出发城市，可不填（不填则忽略往返交通规划）"
          >
            <Input
              size="large"
              placeholder="例如：北京"
              value={origin}
              onChange={(e) => setOrigin(e.target.value)}
            />
          </QABlock>
        )}

        {/* 第 2 步：目的地 */}
        {step === 1 && (
          <QABlock title="想去哪里玩？" subtitle="填写目的地城市或地区" required>
            <Input
              size="large"
              placeholder="例如：云南 / 三亚 / 东京"
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
              autoFocus
            />
          </QABlock>
        )}

        {/* 第 3 步：天数 */}
        {step === 2 && (
          <QABlock title="计划玩几天？" subtitle="出行天数">
            <InputNumber
              size="large"
              min={1}
              max={30}
              style={{ width: "100%" }}
              placeholder="7"
              value={days}
              onChange={(v) => setDays(v)}
            />
          </QABlock>
        )}

        {/* 第 4 步：预算 */}
        {step === 3 && (
          <QABlock title="预算大概多少？" subtitle="预算上限（元）">
            <InputNumber
              size="large"
              min={1}
              max={35000}
              style={{ width: "100%" }}
              placeholder="15000"
              value={budget}
              onChange={(v) => setBudget(v)}
            />
          </QABlock>
        )}

        {/* 第 5 步：成人 */}
        {step === 4 && (
          <QABlock title="几位成人同行？" subtitle="18 周岁及以上" required>
            <InputNumber
              size="large"
              min={1}
              max={20}
              style={{ width: "100%" }}
              placeholder="2"
              value={adults}
              onChange={(v) => setAdults(v)}
            />
          </QABlock>
        )}

        {/* 第 6 步：儿童 */}
        {step === 5 && (
          <QABlock
            title="有儿童同行吗？"
            subtitle="填 0 表示没有；有则填写数量，并补充年龄/身高/是否占座"
          >
            <InputNumber
              size="large"
              min={0}
              max={20}
              style={{ width: "100%", marginBottom: 12 }}
              placeholder="0"
              value={children}
              onChange={(v) => {
                const n = v || 0;
                setChildren(n);
                setChildrenDetail(resizeDetail(childrenDetail, n, { age: 6, height: 1.2, seat: false }));
              }}
            />
            {children > 0 && (
              <>
                <Divider style={{ margin: "8px 0" }} />
                {childrenDetail.map((c, i) => (
                  <Space key={i} align="baseline" style={{ display: "flex", marginBottom: 8 }}>
                    <Typography.Text>儿童 {i + 1}</Typography.Text>
                    <InputNumber
                      min={0}
                      max={17}
                      placeholder="年龄(周岁)"
                      value={c.age}
                      onChange={(v) =>
                        setChildrenDetail((prev) => {
                          const n = [...prev];
                          n[i] = { ...n[i], age: v || 0 };
                          return n;
                        })
                      }
                    />
                    <InputNumber
                      min={0}
                      max={2.5}
                      step={0.01}
                      placeholder="身高(米)"
                      value={c.height}
                      onChange={(v) =>
                        setChildrenDetail((prev) => {
                          const n = [...prev];
                          n[i] = { ...n[i], height: v ?? null };
                          return n;
                        })
                      }
                    />
                    <Space size={4}>
                      <Switch
                        checked={c.seat}
                        onChange={(v) =>
                          setChildrenDetail((prev) => {
                            const n = [...prev];
                            n[i] = { ...n[i], seat: v };
                            return n;
                          })
                        }
                      />
                      <Typography.Text style={{ fontSize: 12 }}>占座</Typography.Text>
                    </Space>
                  </Space>
                ))}
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  门票：6周岁以下或1.2米以下免首道大门票，6-18周岁半价；高铁6岁以下不占座免票、占座半价
                </Typography.Text>
              </>
            )}
          </QABlock>
        )}

        {/* 第 7 步：老人 */}
        {step === 6 && (
          <QABlock
            title="有老人同行吗？"
            subtitle="填 0 表示没有；有则填写数量，并补充年龄/性别"
          >
            <InputNumber
              size="large"
              min={0}
              max={20}
              style={{ width: "100%", marginBottom: 12 }}
              placeholder="0"
              value={elders}
              onChange={(v) => {
                const n = v || 0;
                setElders(n);
                setEldersDetail(resizeDetail(eldersDetail, n, { age: 60, gender: "男" }));
              }}
            />
            {elders > 0 && (
              <>
                <Divider style={{ margin: "8px 0" }} />
                {eldersDetail.map((e, i) => (
                  <Space key={i} align="baseline" style={{ display: "flex", marginBottom: 8 }}>
                    <Typography.Text>老人 {i + 1}</Typography.Text>
                    <InputNumber
                      min={0}
                      max={120}
                      placeholder="年龄"
                      value={e.age}
                      onChange={(v) =>
                        setEldersDetail((prev) => {
                          const n = [...prev];
                          n[i] = { ...n[i], age: v || 0 };
                          return n;
                        })
                      }
                    />
                    <Select
                      style={{ width: 90 }}
                      value={e.gender}
                      onChange={(v) =>
                        setEldersDetail((prev) => {
                          const n = [...prev];
                          n[i] = { ...n[i], gender: v };
                          return n;
                        })
                      }
                      options={[
                        { value: "男", label: "男" },
                        { value: "女", label: "女" },
                      ]}
                    />
                  </Space>
                ))}
                <Divider style={{ margin: "8px 0" }} />
                <Typography.Text style={{ display: "block", marginBottom: 8 }}>
                  老人生活状态（可选）
                </Typography.Text>
                <Select
                  style={{ width: "100%" }}
                  allowClear
                  placeholder="选择状态（可选）"
                  value={elderStatus}
                  onChange={setElderStatus}
                  options={[
                    { value: "健康", label: "健康" },
                    { value: "行动不便", label: "行动不便" },
                    { value: "需轮椅", label: "需轮椅" },
                    { value: "慢病需注意", label: "慢病需注意" },
                    { value: "需常休息", label: "需常休息" },
                  ]}
                />
                <Typography.Text type="secondary" style={{ fontSize: 12, display: "block", marginTop: 8 }}>
                  门票：60-64周岁半价，65周岁及以上免首道大门票（需身份证原件）
                </Typography.Text>
              </>
            )}
          </QABlock>
        )}

        {/* 第 8 步：学生 */}
        {step === 7 && (
          <QABlock
            title="有学生同行吗？"
            subtitle="填 0 表示没有；高铁学生票仅限家校往返，旅游不适用"
          >
            <InputNumber
              size="large"
              min={0}
              max={20}
              style={{ width: "100%", marginBottom: 12 }}
              placeholder="0"
              value={students}
              onChange={(v) => {
                const n = v || 0;
                setStudents(n);
                setStudentsDetail(resizeDetail(studentsDetail, n, { level: "大学本科" }));
              }}
            />
            {students > 0 && (
              <>
                <Divider style={{ margin: "8px 0" }} />
                {studentsDetail.map((s, i) => (
                  <Space key={i} align="baseline" style={{ display: "flex", marginBottom: 8 }}>
                    <Typography.Text>学生 {i + 1}</Typography.Text>
                    <Select
                      style={{ width: 180 }}
                      value={s.level}
                      onChange={(v) =>
                        setStudentsDetail((prev) => {
                          const n = [...prev];
                          n[i] = { ...n[i], level: v };
                          return n;
                        })
                      }
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
                  </Space>
                ))}
              </>
            )}
          </QABlock>
        )}

        {/* 第 9 步：偏好 */}
        {step === 8 && (
          <QABlock title="有什么兴趣偏好？" subtitle="自由填写，可留空；以及同行关系">
            <Select
              mode="tags"
              style={{ width: "100%", marginBottom: 12 }}
              placeholder="输入后回车，如：自然风光 / 美食 / 亲子 / 温泉"
              tokenSeparators={[",", "，"]}
              value={tags}
              onChange={setTags}
            />
            <Select
              style={{ width: "100%" }}
              allowClear
              placeholder="成人关系（可选）"
              value={adultRelation}
              onChange={setAdultRelation}
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
            <Divider style={{ margin: "12px 0" }} />
            <Row gutter={12}>
              <Col span={12}>
                <Typography.Text style={{ display: "block", marginBottom: 6 }}>
                  购票方式（可选）
                </Typography.Text>
                <Select
                  style={{ width: "100%" }}
                  allowClear
                  placeholder="选择购票方式"
                  value={ticketMode}
                  onChange={setTicketMode}
                  options={[
                    { value: "bundle", label: "一次性买票" },
                    { value: "separate", label: "分开买票" },
                  ]}
                />
              </Col>
              <Col span={12}>
                <Typography.Text style={{ display: "block", marginBottom: 6 }}>
                  酒店预订（可选）
                </Typography.Text>
                <Select
                  style={{ width: "100%" }}
                  allowClear
                  placeholder="选择酒店预订方式"
                  value={hotelMode}
                  onChange={setHotelMode}
                  options={[
                    { value: "bundle", label: "一次性订" },
                    { value: "separate", label: "分开订" },
                  ]}
                />
              </Col>
            </Row>
          </QABlock>
        )}

        {/* 第 10 步：确认 */}
        {step === 9 && (
          <QABlock title="确认信息" subtitle="核对无误后提交给 Agent 团队">
            <Row gutter={[12, 12]}>
              <Col span={12}><Info label="出发地" value={origin || "未填写"} /></Col>
              <Col span={12}><Info label="目的地" value={destination || "未填写"} /></Col>
              <Col span={12}><Info label="天数" value={days ? `${days} 天` : "未填写"} /></Col>
              <Col span={12}><Info label="预算" value={budget ? `¥${budget}` : "未填写"} /></Col>
              <Col span={12}><Info label="成人" value={`${adults || 1} 人`} /></Col>
              <Col span={12}><Info label="儿童" value={children > 0 ? `${children} 人` : "无"} /></Col>
              <Col span={12}><Info label="老人" value={elders > 0 ? `${elders} 人` : "无"} /></Col>
              <Col span={12}><Info label="学生" value={students > 0 ? `${students} 人` : "无"} /></Col>
              <Col span={12}><Info label="购票方式" value={ticketMode === "bundle" ? "一次性买票" : ticketMode === "separate" ? "分开买票" : "未填写"} /></Col>
              <Col span={12}><Info label="酒店预订" value={hotelMode === "bundle" ? "一次性订" : hotelMode === "separate" ? "分开订" : "未填写"} /></Col>
              <Col span={24}>
                <Info label="兴趣偏好" value={tags.length ? tags.join("、") : "未填写"} />
              </Col>
            </Row>
            <div style={{ marginTop: 16 }}>
              {tags.map((t) => (
                <Tag key={t} color="blue">{t}</Tag>
              ))}
            </div>
          </QABlock>
        )}

        {/* 底部按钮 */}
        <div style={{ marginTop: 24, display: "flex", justifyContent: "space-between" }}>
          <Button icon={<LeftOutlined />} onClick={prev} disabled={step === 0}>
            上一步
          </Button>
          {step < steps.length - 1 ? (
            <Button type="primary" icon={<RightOutlined />} onClick={next}>
              下一步
            </Button>
          ) : (
            <Button
              type="primary"
              size="large"
              icon={step === 9 ? <RocketOutlined /> : <CheckOutlined />}
              loading={loading}
              onClick={onSubmit}
            >
              提交给 Agent 团队
            </Button>
          )}
        </div>
      </Card>
    </div>
  );
}

function QABlock({
  title,
  subtitle,
  required,
  children,
}: {
  title: string;
  subtitle?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div style={{ minHeight: 180 }}>
      <Space align="baseline">
        <Typography.Title level={4} style={{ margin: 0 }}>
          {title}
        </Typography.Title>
        {required && <Tag color="red">必填</Tag>}
      </Space>
      {subtitle && (
        <Typography.Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
          {subtitle}
        </Typography.Text>
      )}
      <div>{children}</div>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ background: "#f7fafc", borderRadius: 6, padding: "8px 12px" }}>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {label}
      </Typography.Text>
      <div style={{ fontSize: 14, fontWeight: 500 }}>{value}</div>
    </div>
  );
}
