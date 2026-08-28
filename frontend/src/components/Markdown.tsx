import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Markdown 渲染组件（报告 / travel_plan.md 看板）
export default function Markdown({ content }: { content: string }) {
  if (!content) return <span style={{ color: "#999" }}>（暂无内容）</span>;
  return (
    <div
      style={{
        lineHeight: 1.8,
        fontSize: 14,
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          table: ({ children }) => (
            <table style={{ borderCollapse: "collapse", width: "100%", margin: "12px 0" }}>
              {children}
            </table>
          ),
          th: ({ children }) => (
            <th style={{ border: "1px solid #e8e8e8", padding: "8px 12px", background: "#fafafa", textAlign: "left" }}>
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td style={{ border: "1px solid #e8e8e8", padding: "8px 12px" }}>{children}</td>
          ),
          h1: ({ children }) => <h1 style={{ fontSize: 22, margin: "16px 0 8px" }}>{children}</h1>,
          h2: ({ children }) => <h2 style={{ fontSize: 18, margin: "16px 0 8px" }}>{children}</h2>,
          h3: ({ children }) => <h3 style={{ fontSize: 16, margin: "12px 0 6px" }}>{children}</h3>,
          code: ({ children }) => (
            <code style={{ background: "#f5f5f5", padding: "2px 6px", borderRadius: 4 }}>{children}</code>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
