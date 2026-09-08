import { useEffect, useRef, useState } from "react";
import { Button, Card, Input, message, Space, Tag, Typography, Spin } from "antd";
import {
  ArrowLeftOutlined,
  SendOutlined,
  RobotOutlined,
  UserOutlined,
  ClearOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { api, unwrap } from "../api/client";

interface Msg {
  role: "user" | "ai";
  content: string;
  sources?: { ref: string; source: string }[];
}

// 智能文旅问答：RAG 检索增强，问文旅问题，AI 基于知识库回答（带引用来源）
export default function QA() {
  const navigate = useNavigate();
  const [messages, setMessages] = useState<Msg[]>([
    {
      role: "ai",
      content: "你好！我是文旅智能问答助手，基于文旅知识库为你解答。\n\n你可以问我：\n· 老人去云南要注意什么？\n· 迪士尼儿童票怎么买？\n· 高铁儿童免票标准是什么？\n· 冬季去哪滑雪泡温泉？",
    },
  ]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
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
      const data = await unwrap<any>(
        api.post("/qa", {
          message: text,
          history: messages.map((m) => ({ role: m.role, content: m.content })),
        })
      );
      setMessages((prev) => [
        ...prev,
        { role: "ai", content: data.answer || "抱歉，我暂时无法回答。", sources: data.sources || [] },
      ]);
    } catch (e: any) {
      setMessages((prev) => [...prev, { role: "ai", content: "抱歉，出错了：" + e.message }]);
    } finally {
      setThinking(false);
    }
  };

  const clear = () => {
    setMessages([
      {
        role: "ai",
        content: "已清空对话。继续问我文旅问题吧～",
      },
    ]);
  };

  return (
    <div style={{ maxWidth: 760, margin: "0 auto", height: "100%" }}>
      <Space style={{ marginBottom: 12 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/")}>
          返回
        </Button>
        <Typography.Title level={4} style={{ margin: 0 }}>
          <RobotOutlined style={{ marginRight: 8, color: "#1677ff" }} />
          智能问答
        </Typography.Title>
        <Tag color="purple">RAG 检索增强</Tag>
      </Space>

      <Card
        bodyStyle={{ padding: 0, display: "flex", flexDirection: "column", height: "calc(100vh - 180px)" }}
        style={{ height: "calc(100vh - 180px)" }}
      >
        {/* 聊天区 */}
        <div ref={listRef} style={{ flex: 1, overflowY: "auto", padding: 16, background: "#f7fafc" }}>
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
              <div style={{ maxWidth: "75%" }}>
                <div
                  style={{
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
                {/* 引用来源 */}
                {m.sources && m.sources.length > 0 && (
                  <div style={{ marginTop: 6, fontSize: 12, color: "#8c8c8c" }}>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      参考来源：
                    </Typography.Text>
                    {m.sources.map((s) => (
                      <Tag key={s.ref} color="blue" style={{ fontSize: 11, marginTop: 4 }}>
                        {s.ref} {s.source}
                      </Tag>
                    ))}
                  </div>
                )}
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
              <Typography.Text type="secondary">正在检索知识库并思考…</Typography.Text>
            </div>
          )}
        </div>

        {/* 输入区 */}
        <div style={{ padding: 12, borderTop: "1px solid #f0f0f0", background: "#fff" }}>
          <Space.Compact style={{ width: "100%" }}>
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onPressEnter={send}
              placeholder="输入文旅问题，回车发送…"
              disabled={thinking}
            />
            <Button type="primary" icon={<SendOutlined />} onClick={send} loading={thinking}>
              发送
            </Button>
            <Button icon={<ClearOutlined />} onClick={clear} title="清空对话" />
          </Space.Compact>
        </div>
      </Card>
    </div>
  );
}
