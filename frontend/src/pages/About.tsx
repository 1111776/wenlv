import { Card, Timeline, Tag, Typography, Space, Alert } from "antd";
import {
  EnvironmentOutlined,
  ClusterOutlined,
  SafetyCertificateOutlined,
  SyncOutlined,
} from "@ant-design/icons";

// 系统说明页
export default function About() {
  return (
    <div style={{ maxWidth: 800, margin: "0 auto" }}>
      <Card title="系统说明" style={{ marginBottom: 16 }}>
        <Typography.Paragraph>
          本系统是基于 <Tag color="blue">8 个 AI Agent 协作</Tag> 的文旅资源调研与个性化行程规划系统。
          用户输入一句自然语言需求，Agent 团队自动完成从偏好解析到报告生成的完整流程。
        </Typography.Paragraph>
      </Card>

      <Card title="8 个协作 Agent" style={{ marginBottom: 16 }}>
        <Timeline
          items={[
            { color: "blue", children: "🔍 偏好解析（Intake）— 解析目的地、天数、预算、出行人" },
            { color: "blue", children: "📋 任务拆解（Planner）— CoT 拆解出 10+ 个网页调研子任务" },
            { color: "green", children: "🌐 网页调研（Web Research）— ReAct 逐页抓取，实时更新看板" },
            { color: "green", children: "💬 舆情评估（Sentiment）— 情感分析与消费陷阱识别" },
            { color: "green", children: "🗓️ 日程编排（Itinerary）— 按天排景点+交通+住宿，检测夜行风险" },
            { color: "green", children: "💰 预算计算（Budget）— 分项金额汇总，超预算 20% 预警" },
            { color: "orange", children: "👤 人工审核（Human Review）— 风险场景挂起，主管审批" },
            { color: "purple", children: "📄 报告生成（Report）— 行程单 + 预算明细" },
          ]}
        />
      </Card>

      <Card title="核心能力">
        <Space direction="vertical" size="large" style={{ width: "100%" }}>
          <div>
            <Typography.Title level={5}>
              <ClusterOutlined /> 断点续传
            </Typography.Title>
            <Typography.Paragraph type="secondary">
              全过程持久化到 travel_plan.md 状态文件，进程崩溃后 5 秒内从断点恢复，已完成任务不重复执行。
            </Typography.Paragraph>
          </div>
          <div>
            <Typography.Title level={5}>
              <SafetyCertificateOutlined /> 安全防护
            </Typography.Title>
            <Typography.Paragraph type="secondary">
              网页内容安全过滤 + Prompt 注入检测，恶意内容不进上下文、不进报告。
            </Typography.Paragraph>
          </div>
          <div>
            <Typography.Title level={5}>
              <SyncOutlined /> 人机协作
            </Typography.Title>
            <Typography.Paragraph type="secondary">
              超预算 20% / 高危夜行 / 严重舆情 → 挂起人工审核，通过后续跑，驳回即终止。
            </Typography.Paragraph>
          </div>
        </Space>
      </Card>

      <Alert
        style={{ marginTop: 16 }}
        type="info"
        showIcon
        message="演示提示"
        description="种子数据中第 7 页为注入对抗样本、第 8 页为严重负面舆情、第 9 页为高危夜行路段，因此完整流程会触发人工审核（待审核），这是设计使然，用于演示 HITL 功能。"
      />
    </div>
  );
}
