import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Descriptions,
  message,
  Modal,
  Space,
  Table,
  Tag,
  Typography,
  Empty,
} from "antd";
import { api, unwrap } from "../api/client";

const REASON_LABEL: Record<string, { label: string; color: string }> = {
  budget_over: { label: "超预算 20%", color: "volcano" },
  risk_night: { label: "高危夜行", color: "orange" },
  sentiment_risk: { label: "严重舆情", color: "red" },
};

// 审核台（supervisor）：表格内直接操作，不依赖抽屉
// 流程：待抢占 → 点「抢占」→ 变成「通过/驳回」两个按钮 → 点即生效
export default function ReviewBoard() {
  const [reviews, setReviews] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<any>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [submitting, setSubmitting] = useState<string>("");

  const load = async () => {
    try {
      const data = await unwrap<any>(api.get("/reviews/pending"));
      setReviews(data.items || []);
    } catch (e: any) {
      message.error(e.message);
    }
  };

  useEffect(() => {
    load();
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, []);

  const claim = async (id: string) => {
    setSubmitting(`claim:${id}`);
    try {
      await unwrap(api.post(`/reviews/${id}/claim`));
      message.success("已抢占，现在可以审核");
      await load();
    } catch (e: any) {
      message.error(e.message || "抢占失败");
    } finally {
      setSubmitting("");
    }
  };

  const decide = async (id: string, decision: string) => {
    setSubmitting(`decide:${id}`);
    try {
      await unwrap(api.post(`/reviews/${id}/decision`, { decision }));
      message.success(decision === "approved" ? "已通过，行程继续执行" : "已驳回");
      setDetailOpen(false);
      await load();
    } catch (e: any) {
      message.error(e.message || "操作失败");
    } finally {
      setSubmitting("");
    }
  };

  const showDetail = async (id: string) => {
    try {
      const d = await unwrap<any>(api.get(`/reviews/${id}`));
      setDetail(d);
      setDetailOpen(true);
    } catch (e: any) {
      message.error(e.message);
    }
  };

  const columns = [
    {
      title: "行程需求",
      dataIndex: "plan_query",
      key: "plan_query",
      ellipsis: true,
      render: (q: string, r: any) => <a onClick={() => showDetail(r.id)}>{q}</a>,
    },
    {
      title: "触发原因",
      dataIndex: "reason",
      key: "reason",
      width: 120,
      render: (r: string) => {
        const m = REASON_LABEL[r] || { label: r, color: "default" };
        return <Tag color={m.color}>{m.label}</Tag>;
      },
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (s: string) =>
        s === "pending" ? <Tag>待抢占</Tag> : <Tag color="processing">审核中</Tag>,
    },
    {
      title: "操作",
      key: "action",
      width: 240,
      render: (_: any, r: any) => {
        if (r.status === "pending") {
          return (
            <Space>
              <Button
                type="primary"
                size="small"
                loading={submitting === `claim:${r.id}`}
                onClick={() => claim(r.id)}
              >
                抢占
              </Button>
              <Button size="small" onClick={() => showDetail(r.id)}>
                详情
              </Button>
            </Space>
          );
        }
        if (r.status === "reviewing") {
          return (
            <Space>
              <Button
                type="primary"
                size="small"
                loading={submitting === `decide:${r.id}`}
                onClick={() => decide(r.id, "approved")}
              >
                通过
              </Button>
              <Button
                danger
                size="small"
                loading={submitting === `decide:${r.id}`}
                onClick={() => decide(r.id, "rejected")}
              >
                驳回
              </Button>
            </Space>
          );
        }
        return null;
      },
    },
  ];

  return (
    <div>
      <Card
        title={
          <Space>
            <span>待审核队列</span>
            <Tag color="red">{reviews.length} 条待处理</Tag>
          </Space>
        }
      >
        {reviews.length === 0 ? (
          <Empty description="暂无待审核行程" style={{ padding: 40 }} />
        ) : (
          <Table
            rowKey="id"
            dataSource={reviews}
            columns={columns}
            loading={loading}
            pagination={false}
          />
        )}
      </Card>

      {/* 详情弹窗（只读展示） */}
      <Modal
        title="审核详情"
        open={detailOpen}
        onCancel={() => setDetailOpen(false)}
        footer={
          detail &&
          (detail.status === "pending" ? (
            <Button type="primary" loading={submitting === `claim:${detail.id}`} onClick={() => { claim(detail.id); }}>
              抢占此审核
            </Button>
          ) : detail.status === "reviewing" ? (
            <Space>
              <Button danger loading={submitting === `decide:${detail.id}`} onClick={() => decide(detail.id, "rejected")}>
                驳回
              </Button>
              <Button type="primary" loading={submitting === `decide:${detail.id}`} onClick={() => decide(detail.id, "approved")}>
                通过
              </Button>
            </Space>
          ) : null)
        }
      >
        {detail && (
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="当前状态">
              <Tag color={detail.status === "reviewing" ? "processing" : "default"}>{detail.status}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="触发原因">
              <Tag color={REASON_LABEL[detail.reason]?.color || "default"}>
                {REASON_LABEL[detail.reason]?.label || detail.reason}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="触发明细">
              <pre style={{ margin: 0, whiteSpace: "pre-wrap", fontSize: 12, fontFamily: "inherit" }}>
                {JSON.stringify(detail.trigger_detail, null, 2)}
              </pre>
            </Descriptions.Item>
            {detail.plan_summary?.query && (
              <Descriptions.Item label="原始需求">{detail.plan_summary.query}</Descriptions.Item>
            )}
            {detail.plan_summary?.preferences?.destination && (
              <Descriptions.Item label="目的地">{detail.plan_summary.preferences.destination}</Descriptions.Item>
            )}
            {detail.plan_summary?.total_budget != null && (
              <Descriptions.Item label="当前预算">
                ¥{Number(detail.plan_summary.total_budget).toLocaleString()}
              </Descriptions.Item>
            )}
          </Descriptions>
        )}
      </Modal>
    </div>
  );
}
