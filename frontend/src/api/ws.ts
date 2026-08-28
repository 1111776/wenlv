// WebSocket 客户端：订阅行程实时事件
export interface PlanEvent {
  event: string;
  plan_id: string;
  status: string;
  resume_from?: string;
  agent?: string;
  progress?: { done: number; total: number };
  ts?: string;
}

export function subscribePlan(
  planId: string,
  onEvent: (evt: PlanEvent) => void
): () => void {
  const token = localStorage.getItem("token") || "";
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const url = `${proto}://${location.host}/ws/plans/${planId}?token=${encodeURIComponent(token)}`;
  const ws = new WebSocket(url);

  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      if (data.event) onEvent(data);
    } catch {
      /* 忽略非 JSON 帧 */
    }
  };

  // 返回取消订阅函数
  return () => ws.close();
}
