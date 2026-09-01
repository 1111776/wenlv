import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Input,
  message,
  Popconfirm,
  Progress,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import { PlusOutlined, ReloadOutlined, SearchOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import dayjs from "dayjs";
import { api, unwrap } from "../api/client";
import { useAuth } from "../store/auth";

const STATUS_META: Record<string, { color: string; label: string }> = {
  planning: { color: "blue", label: "排队中" },
  running: { color: "processing", label: "执行中" },
  suspended: { color: "warning", label: "待审核" },
  recovering: { color: "orange", label: "恢复中" },
  completed: { color: "success", label: "已完成" },
  failed: { color: "error", label: "失败" },
  cancelled: { color: "default", label: "已取消" },
};

// 行程列表：完整表格（搜索 + 状态筛选 + 取消 + 查看详情）
export default function PlanList() {
  const { role } = useAuth();
  const navigate = useNavigate();
  const [plans, setPlans] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [page, setPage] = useState(1);
  const pageSize = 10;

  const load = async () => {
    setLoading(true);
    try {
      const params: any = { page, page_size: pageSize };
      if (statusFilter) params.status = statusFilter;
      const data = await unwrap<any>(api.get("/plans", { params }));
      setPlans(data.items || []);
      setTotal(data.total || 0);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [page, statusFilter]);

  useEffect(() => {
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [page, statusFilter]);

  const onCancel = async (id: string) => {
    try {
      await unwrap(api.post(`/plans/${id}/cancel`));
      message.success("已取消");
      load();
    } catch (e: any) {
      message.error(e.message);
    }
  };

  const onDelete = async (id: string) => {
    try {
      await unwrap(api.delete(`/plans/${id}`));
      message.success("已删除");
      load();
    } catch (e: any) {
      message.error(e.message);
    }
  };

  const columns = [
    {
      title: "需求描述",
      dataIndex: "query",
      key: "query",
      ellipsis: true,
      render: (q: string, r: any) => (
        <a onClick={() => navigate(`/plans/${r.id}`)}>{q || "未命名行程"}</a>
      ),
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 110,
      render: (s: string) => {
        const m = STATUS_META[s] || { color: "default", label: s };
        return <Tag color={m.color}>{m.label}</Tag>;
      },
    },
    {
      title: "进度",
      key: "progress",
      width: 180,
      render: (_: any, r: any) => {
        const done = r.progress?.done ?? 0;
        const total = r.progress?.total ?? 0;
        const percent = total > 0 ? Math.round((done / total) * 100) : 0;
        return <Progress percent={percent} size="small" />;
      },
    },
    {
      title: "断点",
      dataIndex: "resume_from",
      key: "resume_from",
      width: 160,
      render: (v: string) => v || "-",
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      key: "created_at",
      width: 140,
      render: (v: string) => dayjs(v).format("MM-DD HH:mm"),
    },
    {
      title: "完成时间",
      dataIndex: "completed_at",
      key: "completed_at",
      width: 140,
      render: (v: string) => (v ? dayjs(v).format("MM-DD HH:mm") : "-"),
    },
    {
      title: "操作",
      key: "action",
      width: 160,
      render: (_: any, r: any) => (
        <Space>
          <a onClick={() => navigate(`/plans/${r.id}`)}>详情</a>
          {!["completed", "failed", "cancelled"].includes(r.status) && (
            <Popconfirm title="确认取消该行程？" onConfirm={() => onCancel(r.id)}>
              <a style={{ color: "#faad14" }}>取消</a>
            </Popconfirm>
          )}
          <Popconfirm title="确认删除该行程？删除后不可恢复" onConfirm={() => onDelete(r.id)}>
            <a style={{ color: "#ff4d4f" }}>删除</a>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card
      title={
        <Space>
          <span>行程列表</span>
          <Tag>{role === "supervisor" ? "全部行程" : "我的行程"}</Tag>
        </Space>
      }
      extra={
        <Space>
          <Input
            prefix={<SearchOutlined />}
            placeholder="搜索需求"
            allowClear
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onPressEnter={load}
            style={{ width: 200 }}
          />
          <Select
            placeholder="状态筛选"
            allowClear
            style={{ width: 140 }}
            value={statusFilter}
            onChange={setStatusFilter}
            options={Object.entries(STATUS_META).map(([k, v]) => ({ value: k, label: v.label }))}
          />
          <Button icon={<ReloadOutlined />} onClick={load}>
            刷新
          </Button>
          {role !== "supervisor" && (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate("/plans/new")}>
              新建行程
            </Button>
          )}
        </Space>
      }
    >
      <Table
        rowKey="id"
        dataSource={plans}
        columns={columns}
        loading={loading}
        pagination={{
          current: page,
          pageSize,
          total,
          onChange: setPage,
          showTotal: (t) => `共 ${t} 条`,
        }}
      />
    </Card>
  );
}
