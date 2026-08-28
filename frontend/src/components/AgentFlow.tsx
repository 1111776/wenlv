import { Space, Tag, Tooltip } from "antd";
import {
  CheckCircleFilled,
  LoadingOutlined,
  ClockCircleOutlined,
  ExclamationCircleFilled,
  MinusCircleOutlined,
} from "@ant-design/icons";

// Agent 状态 → 展示元素
const STATUS_ICON: Record<string, any> = {
  completed: <CheckCircleFilled style={{ color: "#52c41a", fontSize: 20 }} />,
  running: <LoadingOutlined style={{ color: "#1677ff", fontSize: 20 }} />,
  pending: <ClockCircleOutlined style={{ color: "#d9d9d9", fontSize: 20 }} />,
  waiting: <ExclamationCircleFilled style={{ color: "#faad14", fontSize: 20 }} />,
  reviewing: <LoadingOutlined style={{ color: "#faad14", fontSize: 20 }} />,
  rejected: <MinusCircleOutlined style={{ color: "#ff4d4f", fontSize: 20 }} />,
  skipped: <MinusCircleOutlined style={{ color: "#d9d9d9", fontSize: 20 }} />,
};

const STATUS_LABEL: Record<string, string> = {
  completed: "已完成",
  running: "执行中",
  pending: "待执行",
  waiting: "待审核",
  reviewing: "审核中",
  rejected: "已驳回",
  skipped: "已跳过",
};

// Agent 执行流程可视化（横向 Steps 风格）
export default function AgentFlow({ agents }: { agents: any[] }) {
  if (!agents?.length) return null;

  return (
    <div style={{ display: "flex", alignItems: "center", overflowX: "auto", padding: "12px 0" }}>
      {agents.map((a, i) => {
        const status = a.status || "pending";
        const icon = STATUS_ICON[status] || STATUS_ICON.pending;
        return (
          <div key={a.key} style={{ display: "flex", alignItems: "center", flexShrink: 0 }}>
            <Tooltip title={`${a.name} — ${STATUS_LABEL[status] || status}`}>
              <div style={{ textAlign: "center", width: 80 }}>
                <div>{icon}</div>
                <div style={{ fontSize: 13, marginTop: 6, fontWeight: status === "running" ? 600 : 400 }}>
                  {a.name}
                </div>
                <Tag
                  color={
                    status === "completed"
                      ? "success"
                      : status === "running" || status === "reviewing"
                      ? "processing"
                      : status === "waiting" || status === "rejected"
                      ? "warning"
                      : "default"
                  }
                  style={{ marginTop: 4, fontSize: 11 }}
                >
                  {STATUS_LABEL[status] || status}
                </Tag>
              </div>
            </Tooltip>
            {i < agents.length - 1 && (
              <div style={{ width: 28, height: 2, background: status === "completed" ? "#52c41a" : "#e8e8e8", margin: "0 4px" }} />
            )}
          </div>
        );
      })}
    </div>
  );
}
