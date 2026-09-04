import { useState, useRef } from "react";
import {
  Button,
  Card,
  Input,
  message,
  Select,
  Space,
  Tag,
  Typography,
  Alert,
  InputNumber,
  Divider,
} from "antd";
import {
  ArrowLeftOutlined,
  AudioOutlined,
  StopOutlined,
  SendOutlined,
  ClearOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { api, unwrap } from "../api/client";

// 语音创建行程：用浏览器原生 SpeechRecognition 把语音转文字，再提交生成行程
export default function PlanVoice() {
  const navigate = useNavigate();
  const [listening, setListening] = useState(false);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const [supported, setSupported] = useState<boolean | null>(null);
  const recRef = useRef<any>(null);

  // 浏览器语音识别支持检测
  const getRecognition = (): any | null => {
    const w: any = window as any;
    const SR = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!SR) return null;
    const rec = new SR();
    rec.lang = "zh-CN";
    rec.continuous = true;
    rec.interimResults = true;
    return rec;
  };

  const startListening = () => {
    const rec = getRecognition();
    if (!rec) {
      setSupported(false);
      message.error("当前浏览器不支持语音识别，请使用 Chrome 或 Edge");
      return;
    }
    setSupported(true);
    rec.onresult = (event: any) => {
      let finalText = "";
      let interimText = "";
      for (let i = 0; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          finalText += event.results[i][0].transcript;
        } else {
          interimText += event.results[i][0].transcript;
        }
      }
      // 追加最终结果到已有文本
      if (finalText) {
        setText((prev) => (prev ? prev + finalText : finalText));
      }
    };
    rec.onerror = (event: any) => {
      if (event.error === "not-allowed") {
        message.error("麦克风权限被拒绝，请在浏览器地址栏允许麦克风访问");
      } else if (event.error !== "aborted") {
        message.warning("识别出错：" + event.error);
      }
      setListening(false);
    };
    rec.onend = () => {
      setListening(false);
    };
    recRef.current = rec;
    try {
      rec.start();
      setListening(true);
    } catch (e) {
      setListening(false);
    }
  };

  const stopListening = () => {
    if (recRef.current) {
      try {
        recRef.current.stop();
      } catch (e) {
        /* ignore */
      }
    }
    setListening(false);
  };

  const clearText = () => setText("");

  const onSubmit = async () => {
    if (!text.trim()) {
      message.warning("请先说话或输入需求");
      return;
    }
    setLoading(true);
    try {
      const payload: any = {
        query: text.trim(),
        tags: [],
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
          <AudioOutlined style={{ marginRight: 8, color: "#1677ff" }} />
          语音创建行程
        </Typography.Title>
      </Space>

      <Card>
        <Alert
          style={{ marginBottom: 16 }}
          type="info"
          showIcon
          message="用嘴说需求，系统自动转成文字生成行程"
          description="点击下方按钮开始说话（例如：去云南玩7天，2个大人1个小孩，预算15000，喜欢自然风光）。说完后确认文字再提交。推荐使用 Chrome / Edge 浏览器。"
        />

        {/* 麦克风按钮 */}
        <div style={{ textAlign: "center", margin: "24px 0" }}>
          {listening ? (
            <Button
              type="primary"
              danger
              size="large"
              icon={<StopOutlined />}
              onClick={stopListening}
              style={{ width: 220, height: 56, fontSize: 16 }}
            >
              正在聆听… 点击停止
            </Button>
          ) : (
            <Button
              type="primary"
              size="large"
              icon={<AudioOutlined />}
              onClick={startListening}
              style={{ width: 220, height: 56, fontSize: 16 }}
            >
              点击开始说话
            </Button>
          )}
          {supported === false && (
            <div style={{ marginTop: 12, color: "#f5222d" }}>
              当前浏览器不支持语音识别，请改用 Chrome 或 Edge
            </div>
          )}
        </div>

        <Divider style={{ margin: "12px 0" }} />

        {/* 识别文字 */}
        <Typography.Text type="secondary">识别到的需求（可手动修改）：</Typography.Text>
        <Input.TextArea
          rows={4}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="这里会显示语音识别结果，也可以直接手动输入需求…"
          style={{ marginTop: 8 }}
        />

        <div style={{ marginTop: 16, display: "flex", gap: 12, justifyContent: "flex-end" }}>
          <Button icon={<ClearOutlined />} onClick={clearText} disabled={!text}>
            清空
          </Button>
          <Button
            type="primary"
            icon={<SendOutlined />}
            loading={loading}
            onClick={onSubmit}
            disabled={!text.trim()}
          >
            生成行程
          </Button>
        </div>
      </Card>
    </div>
  );
}
