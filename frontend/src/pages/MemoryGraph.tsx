import { useEffect, useState } from "react";
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
import { api, unwrap } from "../api/client";
import { useAuth } from "../store/auth";

const NODE_CLASS_LABEL: Record<string, { label: string; color: string }> = {
  chat_memory: { label: "对话记忆", color: "blue" },
  domain_wiki: { label: "领域知识", color: "green" },
  code_graph: { label: "代码图", color: "purple" },
};

// 记忆图谱页：实体卡片 + 搜索 + 干预（supervisor）+ 干预历史
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
          跨系统共享图记忆：实体节点 {nodes.length} 个，关系边 {edges.length} 条
        </Typography.Paragraph>

        {nodes.length === 0 ? (
          <Empty description="暂无记忆实体" style={{ padding: 40 }} />
        ) : (
          <Row gutter={[12, 12]}>
            {nodes.map((n) => {
              const cls = NODE_CLASS_LABEL[n.node_class] || { label: n.node_class, color: "default" };
              return (
                <Col span={6} key={n.id}>
                  <Card size="small" hoverable>
                    <Space direction="vertical" size={4}>
                      <Space>
                        <Tag color={cls.color}>{cls.label}</Tag>
                        <Tag>{n.type}</Tag>
                      </Space>
                      <Typography.Text strong>{n.key}</Typography.Text>
                      {n.properties && Object.keys(n.properties).length > 0 && (
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          {JSON.stringify(n.properties)}
                        </Typography.Text>
                      )}
                    </Space>
                  </Card>
                </Col>
              );
            })}
          </Row>
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
