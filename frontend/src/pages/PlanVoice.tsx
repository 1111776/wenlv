import { useState, useRef } from "react";
import {
  Button,
  Card,
  Input,
  message,
  Space,
  Typography,
  Alert,
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
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const recRef = useRef<any>(null);

  const startListening = () => {
    setErrorMsg(null);
    const w: any = window as any;
    const SR = w.SpeechRecognition || w.webkitSpeechRecognition;

    // 1. 浏览器不支持
    if (!SR) {
      setErrorMsg(
        "当前浏览器不支持语音识别（Web Speech API）。请改用 Chrome 或 Edge 浏览器打开本页面。"
      );
      return;
    }

    const rec = new SR();
    rec.lang = "zh-CN";
    rec.continuous = true;
    rec.interimResults = true;

    rec.onstart = () => {
      setListening(true);
      setErrorMsg(null);
    };

    rec.onresult = (event: any) => {
      let finalText = "";
      for (let i = 0; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          finalText += event.results[i][0].transcript;
        }
      }
      if (finalText) {
        setText((prev) => (prev ? prev + finalText : finalText));
      }
    };

    rec.onerror = (event: any) => {
      setListening(false);
      switch (event.error) {
        case "not-allowed":
          setErrorMsg(
            "麦克风权限被拒绝。请点击浏览器地址栏左侧的锁图标，允许麦克风访问后重试。"
          );
          break;
        case "no-speech":
          setErrorMsg("没有检测到语音，请离麦克风近一点再试。");
          break;
        case "audio-capture":
          setErrorMsg("没有找到麦克风设备，请检查麦克风是否连接。");
          break;
        case "network":
          setErrorMsg(
            "语音识别网络连接失败。浏览器原生识别依赖 Google 语音服务，国内网络不稳定。建议换 Edge 浏览器重试，或改用「新建行程/问答式创建」手动输入。"
          );
          break;
        case "service-not-allowed":
          setErrorMsg("浏览器语音识别服务不可用（可能被浏览器禁用或网络受限）。");
          break;
        default:
          setErrorMsg("识别出错：" + event.error);
      }
    };

    rec.onend = () => {
      setListening(false);
    };

    recRef.current = rec;
    try {
      rec.start();
    } catch (e: any) {
      setListening(false);
      setErrorMsg("无法启动语音识别：" + (e?.message || e));
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
      setErrorMsg("请先说话或输入需求");
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
      setErrorMsg(e.message);
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
          description="点击下方按钮开始说话。注意：浏览器原生语音识别依赖 Google 服务，国内网络可能不稳定；如果转不出字，请换 Edge 浏览器，或改用「新建行程/问答式创建」手动输入。"
        />

        {/* 错误提示（内联，不依赖可能失效的全局 message） */}
        {errorMsg && (
          <Alert
            style={{ marginBottom: 16 }}
            type="error"
            showIcon
            message="语音识别未成功"
            description={errorMsg}
          />
        )}

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
