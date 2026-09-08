import { useEffect, useRef, useState } from "react";
import {
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Input,
  message,
  Modal,
  Row,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import { SearchOutlined, ReloadOutlined, ApiOutlined } from "@ant-design/icons";
import { Graph } from "@antv/g6";
import { api, unwrap } from "../api/client";
import { useAuth } from "../store/auth";

const NODE_CLASS_LABEL: Record<string, { label: string; color: string }> = {
  chat_memory: { label: "对话记忆", color: "blue" },
  domain_wiki: { label: "领域知识", color: "green" },
  code_graph: { label: "代码图", color: "purple" },
};

// 实体类型 → 中文（归一化：把 LLM 抽出的碎片类型归到统一中文标签）
const TYPE_LABEL: Record<string, string> = {
  User: "用户",
  Food: "食物",
  Attraction: "景点",
  City: "城市",
  Location: "目的地",
  Destination: "目的地",
  Place: "地点",
  Preference: "偏好",
  Interest: "偏好",
  Theme: "偏好",
  Constraint: "约束",
  Allergy: "过敏原",
  Activity: "活动",
  TravelStyle: "出行风格",
  Group: "同行人",
  Accommodation: "住宿",
};

// 类型 → 颜色（按语义大类分组，相同大类同色）
const TYPE_COLOR: Record<string, string> = {
  User: "#fa8c16",        // 橙色：用户（核心）
  Food: "#f5222d",        // 红色：食物/过敏原
  Allergy: "#f5222d",
  Location: "#1677ff",    // 蓝色：目的地
  Destination: "#1677ff",
  City: "#1677ff",
  Place: "#1677ff",
  Attraction: "#52c41a",  // 绿色：景点/活动
  Activity: "#52c41a",
  Preference: "#722ed1",  // 紫色：偏好/风格
  Interest: "#722ed1",
  Theme: "#722ed1",
  TravelStyle: "#722ed1",
  Constraint: "#eb2f96",  // 粉色：约束
  Group: "#13c2c2",       // 青色：同行人
  Accommodation: "#13c2c2",
};

// 关系 → 中文
const RELATION_LABEL: Record<string, string> = {
  HAS_ALLERGY: "过敏",
  PREFERS: "偏好",
  PLANS_VISIT: "想去",
  LOCATED_IN: "位于",
  HATES: "不喜欢",
  LIKES: "喜欢",
};

// 记忆图谱页：实体卡片 + 可视化知识图谱 + 搜索 + 干预（supervisor）+ 干预历史
export default function MemoryGraph() {
  const { role } = useAuth();
  const [nodes, setNodes] = useState<any[]>([]);
  const [edges, setEdges] = useState<any[]>([]);
  const [interventions, setInterventions] = useState<any[]>([]);
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [searchKey, setSearchKey] = useState("");
  const [loading, setLoading] = useState(false);
  const [interveneOpen, setInterveneOpen] = useState(false);
  const [interveneForm, setInterveneForm] = useState({ entityKey: "", entityType: "Attraction", patch: "{}", reason: "" });
  const graphContainerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<any>(null);

  const load = async () => {
    setLoading(true);
    try {
      const [g, i] = await Promise.all([
        unwrap<any>(api.get("/memory/graph")),
        unwrap<any>(api.get("/memory/interventions")),
      ]);
      setNodes(g.nodes || []);
      setEdges(g.edges || []);
      setInterventions(i.items || []);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  // 渲染可视化知识图谱（G6）
  useEffect(() => {
    if (!graphContainerRef.current || nodes.length === 0) return;

    // 清洗 key：去掉解析产生的脏前缀（如「天上海」→「上海」）
    const cleanKey = (key: string) => {
      if (!key) return key;
      return key.replace(/^天/, "");
    };

    // 组装 G6 数据（中文标签，按语义大类配色）
    const g6Nodes = nodes.map((n) => {
      const color = TYPE_COLOR[n.type] || "#8c8c8c";
      const label = `${TYPE_LABEL[n.type] || n.type}:${cleanKey(n.key)}`;
      return {
        id: String(n.id),
        label,
        style: { fill: color, stroke: color },
        labelCfg: { style: { fontSize: 12, fill: "#333" } },
      };
    });
    const g6Edges = edges.map((e) => ({
      source: String(e.src_id),
      target: String(e.dst_id),
      label: RELATION_LABEL[e.relation] || e.relation,
      labelCfg: { style: { fontSize: 11, fill: "#8c8c8c" } },
    }));

    if (graphRef.current) {
      graphRef.current.destroy();
      graphRef.current = null;
    }

    const graph = new Graph({
      container: graphContainerRef.current,
      width: graphContainerRef.current.clientWidth,
      height: 520,
      modes: {
        default: ["drag-canvas", "zoom-canvas", "drag-node"],
      },
      layout: {
        type: "force",
        preventOverlap: true,
        linkDistance: 150,
        nodeStrength: -120,
        nodeSize: 40,
      },
      defaultNode: {
        type: "circle",
        size: 26,
      },
      defaultEdge: {
        type: "line",
        style: { endArrow: true, stroke: "#d9d9d9", lineWidth: 1 },
      },
    });
    graph.data({ nodes: g6Nodes, edges: g6Edges });
    graph.render();
    graphRef.current = graph;

    return () => {
      if (graphRef.current) {
        graphRef.current.destroy();
        graphRef.current = null;
      }
    };
  }, [nodes, edges]);

  const onSearch = async () => {
    if (!searchKey.trim()) return;
    try {
      const r = await unwrap<any>(api.get("/memory/search", { params: { q: searchKey } }));
      setSearchResults(r.items || []);
    } catch (e: any) {
      message.error(e.message);
    }
  };

  const doIntervene = async () => {
    try {
      const { entityKey, entityType, patch, reason } = interveneForm;
      const threadId = searchKey || "plan_demo"; // 简化：用搜索词作为 thread_id（实际应选目标 plan）
      // 前端计算 HMAC 签名（与后端 mutator._hmac_sign 完全对齐）
      const nonce = crypto.randomUUID();
      const secret = "dev-only-insecure-secret-change-me";
      const patchObj = JSON.parse(patch);
      // 后端：payload = thread_id|nonce|sha256(json.dumps(patch, sort_keys=True)).hexdigest()
      const patchSha = await sha256Hex(JSON.stringify(patchObj, Object.keys(patchObj).sort()));
      const payload = `${threadId}|${nonce}|${patchSha}`;
      const sig = await signHmac(secret, payload);

      const r = await unwrap<any>(
        api.post("/memory/intervene", {
          thread_id: threadId,
          target_entity: { type: entityType, key: entityKey },
          patch: patchObj,
          state_patch: { excluded_attractions: [entityKey] },
          reason,
          nonce,
          signature: sig,
        })
      );
      message.success(`干预成功，流水 id=${r.intervention_id}`);
      setInterveneOpen(false);
      load();
    } catch (e: any) {
      message.error(e.message || "干预失败");
    }
  };

  const columns = [
    { title: "ID", dataIndex: "id", width: 60 },
    { title: "thread", dataIndex: "thread_id", ellipsis: true },
    { title: "目标实体", dataIndex: ["target_entity", "key"] },
    {
      title: "状态",
      dataIndex: "status",
      render: (s: string) => (
        <Tag color={s === "applied" ? "processing" : s === "consumed" ? "success" : "default"}>{s}</Tag>
      ),
    },
    { title: "操作者", dataIndex: "operator", width: 100 },
    { title: "时间", dataIndex: "created_at", width: 180, render: (v: string) => v?.slice(0, 19) },
  ];

  return (
    <div>
      <Card
        title="记忆图谱"
        extra={
          <Space>
            <Input
              prefix={<SearchOutlined />}
              placeholder="搜索记忆（如：海鲜过敏）"
              value={searchKey}
              onChange={(e) => setSearchKey(e.target.value)}
              onPressEnter={onSearch}
              style={{ width: 260 }}
            />
            <Button icon={<SearchOutlined />} onClick={onSearch}>
              检索
            </Button>
            <Button icon={<ReloadOutlined />} onClick={load}>
              刷新
            </Button>
            {role === "supervisor" && (
              <Button type="primary" icon={<ApiOutlined />} onClick={() => setInterveneOpen(true)}>
                发起干预
              </Button>
            )}
          </Space>
        }
      >
        <Typography.Paragraph type="secondary">
          跨系统共享图记忆：实体节点 {nodes.length} 个，关系边 {edges.length} 条（拖拽节点、滚轮缩放）
        </Typography.Paragraph>

        {/* 图例 */}
        <div style={{ marginBottom: 12, display: "flex", flexWrap: "wrap", gap: 16 }}>
          <span style={{ fontSize: 12 }}><span style={{ display: "inline-block", width: 10, height: 10, borderRadius: "50%", background: "#fa8c16", marginRight: 4 }} />用户</span>
          <span style={{ fontSize: 12 }}><span style={{ display: "inline-block", width: 10, height: 10, borderRadius: "50%", background: "#1677ff", marginRight: 4 }} />目的地/城市</span>
          <span style={{ fontSize: 12 }}><span style={{ display: "inline-block", width: 10, height: 10, borderRadius: "50%", background: "#52c41a", marginRight: 4 }} />景点/活动</span>
          <span style={{ fontSize: 12 }}><span style={{ display: "inline-block", width: 10, height: 10, borderRadius: "50%", background: "#722ed1", marginRight: 4 }} />偏好/风格</span>
          <span style={{ fontSize: 12 }}><span style={{ display: "inline-block", width: 10, height: 10, borderRadius: "50%", background: "#f5222d", marginRight: 4 }} />食物/过敏</span>
          <span style={{ fontSize: 12 }}><span style={{ display: "inline-block", width: 10, height: 10, borderRadius: "50%", background: "#eb2f96", marginRight: 4 }} />约束</span>
        </div>

        {/* 可视化知识图谱 */}
        {nodes.length > 0 ? (
          <div
            ref={graphContainerRef}
            style={{ width: "100%", height: 520, border: "1px solid #f0f0f0", borderRadius: 8 }}
          />
        ) : (
          <Empty description="暂无记忆实体" style={{ padding: 40 }} />
        )}
      </Card>

      {/* 检索结果 */}
      {searchResults.length > 0 && (
        <Card title={`检索结果（${searchResults.length}）`} style={{ marginTop: 16 }}>
          <Table
            rowKey={(r: any) => r.key}
            dataSource={searchResults}
            columns={[
              { title: "类型", dataIndex: "type", width: 100 },
              { title: "键", dataIndex: "key" },
              { title: "得分", dataIndex: "score", width: 100 },
              { title: "检索路径", dataIndex: "retrieval_path", ellipsis: true },
            ]}
            pagination={false}
            size="small"
          />
        </Card>
      )}

      {/* 干预历史 */}
      <Card title="干预历史" style={{ marginTop: 16 }}>
        <Table
          rowKey="id"
          dataSource={interventions}
          columns={columns}
          pagination={false}
          size="small"
        />
      </Card>

      {/* 干预弹窗 */}
      <Modal
        title="发起强干预"
        open={interveneOpen}
        onCancel={() => setInterveneOpen(false)}
        onOk={doIntervene}
        okText="确认干预"
      >
        <Space direction="vertical" style={{ width: "100%" }} size="middle">
          <div>
            <Typography.Text strong>目标实体 key</Typography.Text>
            <Input
              value={interveneForm.entityKey}
              onChange={(e) => setInterveneForm({ ...interveneForm, entityKey: e.target.value })}
              placeholder="如：栈桥"
            />
          </div>
          <div>
            <Typography.Text strong>实体类型</Typography.Text>
            <Input
              value={interveneForm.entityType}
              onChange={(e) => setInterveneForm({ ...interveneForm, entityType: e.target.value })}
              placeholder="Attraction"
            />
          </div>
          <div>
            <Typography.Text strong>属性补丁（JSON）</Typography.Text>
            <Input.TextArea
              rows={3}
              value={interveneForm.patch}
              onChange={(e) => setInterveneForm({ ...interveneForm, patch: e.target.value })}
              placeholder='{"available": false, "closed_reason": "台风停运"}'
            />
          </div>
          <div>
            <Typography.Text strong>原因</Typography.Text>
            <Input
              value={interveneForm.reason}
              onChange={(e) => setInterveneForm({ ...interveneForm, reason: e.target.value })}
              placeholder="台风停运"
            />
          </div>
        </Space>
      </Modal>
    </div>
  );
}

// 工具函数：与后端 mutator 签名逻辑对齐
async function sha256Hex(s: string): Promise<string> {
  const enc = new TextEncoder();
  const buf = await crypto.subtle.digest("SHA-256", enc.encode(s));
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function signHmac(secret: string, payload: string): Promise<string> {
  // 使用 Web Crypto API 计算 HMAC-SHA256
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(payload));
  return Array.from(new Uint8Array(sig)).map((b) => b.toString(16).padStart(2, "0")).join("");
}
