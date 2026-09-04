import { useState, useRef, useEffect } from "react";
import {
  Button,
  Card,
  Input,
  message,
  Space,
  Typography,
  Tag,
  Spin,
} from "antd";
import {
  ArrowLeftOutlined,
  SendOutlined,
  RobotOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { api, unwrap } from "../api/client";

interface Msg {
  role: "user" | "ai";
  content: string;
}

// 对话式创建行程：像 DeepSeek 一样 AI 主动问、用户自然语言答
export default function PlanChat() {
  const navigate = useNavigate();
  const [messages, setMessages] = useState<Msg[]>([
    {
      role: "ai",
      content: "你好呀！我是你的行程规划助手～ 想去哪里玩？告诉我目的地，我来帮你安排。",
    },
  ]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [extracted, setExtracted] = useState<Record<string, any>>({});
  const [ready, setReady] = useState(false);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, thinking]);

  const send = async () => {
    const text = input.trim();
    if (!text || thinking) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setThinking(true);

    try {
      const history = messages
        .filter((m) => m.role !== "ai" || true)
        .map((m) => ({ role: m.role, content: m.content }));

      const data = await unwrap<any>(
        api.post("/plans/chat", {
          message: text,
          history,
          extracted,
        })
      );

      setMessages((prev) => [...prev, { role: "ai", content: data.reply }]);
      setExtracted(data.extracted || {});
      setReady(!!data.ready);
    } catch (e: any) {
      setMessages((prev) => [...prev, { role: "ai", content: "抱歉，出错了：" + e.message }]);
    } finally {
      setThinking(false);
    }
  };

  const generate = async () => {
    if (!extracted.destination || !extracted.days || !extracted.adults) {
      message.warning("信息还不完整，请再补充一下");
      return;
    }
    try {
      const queryParts: string[] = [];
      if (extracted.origin && extracted.destination)
        queryParts.push(`从${extracted.origin}到${extracted.destination}`);
      else queryParts.push(`${extracted.destination}游`);
      queryParts.push(`${extracted.days}天`);
      queryParts.push(`${extracted.adults}大${extracted.children || 0}小${extracted.elders || 0}老`);
      if (extracted.budget_limit) queryParts.push(`预算${extracted.budget_limit}`);
      if (extracted.tags?.length) queryParts.push(extracted.tags.join(" "));
      const query = queryParts.join("，");

      const payload: any = {
        query,
        origin: extracted.origin || null,
        destination: extracted.destination || null,
        days: extracted.days || undefined,
        budget_limit: extracted.budget_limit || undefined,
        tags: extracted.tags || [],
        party: {
          adults: extracted.adults || 1,
          children: extracted.children || 0,
          elders: extracted.elders || 0,
        },
      };
      const data = await unwrap<any>(api.post("/plans", payload));
      setCreatedId(data.plan_id);
      message.success("行程已提交，Agent 团队开始工作");
    } catch (e: any) {
      message.error(e.message);
    }
  };

  if (createdId) {
    return (
      <div style={{ maxWidth: 720, margin: "0 auto" }}>
        <Card>
          <Typography.Title level={4}>行程创建成功！</Typography.Title>
          <Typography.Paragraph>
            行程 ID：{createdId}。8 个 Agent 正在协作处理，可前往行程列表查看进度。
          </Typography.Paragraph>
          <Space>
            <Button type="primary" onClick={() => navigate(`/plans/${createdId}`)}>
              查看实时进度
            </Button>
            <Button onClick={() => navigate("/plans")}>返回列表</Button>
          </Space>
        </Card>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 720, margin: "0 auto", height: "100%" }}>
      <Space style={{ marginBottom: 12 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/plans")}>
          返回列表
        </Button>
        <Typography.Title level={4} style={{ margin: 0 }}>
          <RobotOutlined style={{ marginRight: 8, color: "#1677ff" }} />
          对话式创建行程
        </Typography.Title>
      </Space>

      {/* 已收集字段展示 */}
      {Object.keys(extracted).length > 0 && (
        <div style={{ marginBottom: 12 }}>
          {Object.entries(extracted).map(([k, v]) => {
            if (k === "tags") return null;
            return (
              <Tag key={k} color="blue" style={{ marginBottom: 4 }}>
                {fieldLabel(k)}：{Array.isArray(v) ? v.join("、") : v}
              </Tag>
            );
          })}
        </div>
      )}

      <Card
        bodyStyle={{ padding: 0, display: "flex", flexDirection: "column", height: "calc(100vh - 200px)" }}
        style={{ height: "calc(100vh - 200px)" }}
      >
        {/* 聊天区 */}
        <div
          ref={listRef}
          style={{ flex: 1, overflowY: "auto", padding: 16, background: "#f7fafc" }}
        >
          {messages.map((m, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                justifyContent: m.role === "user" ? "flex-end" : "flex-start",
                marginBottom: 12,
              }}
            >
              {m.role === "ai" && (
                <div
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: "50%",
                    background: "#1677ff",
                    color: "#fff",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    marginRight: 8,
                    flexShrink: 0,
                  }}
                >
                  <RobotOutlined />
                </div>
              )}
              <div
                style={{
                  maxWidth: "75%",
                  padding: "10px 14px",
                  borderRadius: 12,
                  background: m.role === "user" ? "#1677ff" : "#fff",
                  color: m.role === "user" ? "#fff" : "#1f2d3d",
                  boxShadow: "0 1px 3px rgba(0,0,0,0.08)",
                  lineHeight: 1.6,
                  whiteSpace: "pre-wrap",
                }}
              >
                {m.content}
              </div>
              {m.role === "user" && (
                <div
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: "50%",
                    background: "#52c41a",
                    color: "#fff",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    marginLeft: 8,
                    flexShrink: 0,
                  }}
                >
                  <UserOutlined />
                </div>
              )}
            </div>
          ))}
          {thinking && (
            <div style={{ display: "flex", alignItems: "center", marginBottom: 12 }}>
              <Spin size="small" style={{ marginRight: 8 }} />
              <Typography.Text type="secondary">正在思考…</Typography.Text>
            </div>
          )}
        </div>

        {/* 输入区 */}
        <div style={{ padding: 12, borderTop: "1px solid #f0f0f0", background: "#fff" }}>
          {ready ? (
            <Space direction="vertical" style={{ width: "100%" }}>
              <Typography.Text type="success">✅ 信息已齐全，可以生成行程了</Typography.Text>
              <Button type="primary" block onClick={generate}>
                立即生成行程
              </Button>
            </Space>
          ) : (
            <Space.Compact style={{ width: "100%" }}>
              <Input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onPressEnter={send}
                placeholder="输入你的回答，回车发送…"
                disabled={thinking}
              />
              <Button type="primary" icon={<SendOutlined />} onClick={send} loading={thinking}>
                发送
              </Button>
            </Space.Compact>
          )}
        </div>
      </Card>
    </div>
  );
}

function fieldLabel(key: string): string {
  const map: Record<string, string> = {
    origin: "出发地",
    destination: "目的地",
    days: "天数",
    budget_limit: "预算",
    adults: "成人",
    children: "儿童",
    elders: "老人",
    tags: "兴趣",
  };
  return map[key] || key;
}
