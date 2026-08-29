import { CSSProperties } from "react";

// 动态壁纸背景：流动渐变 + 漂浮光斑 + 星光粒子（纯 CSS 动画，无外部图片）
// variant: "dark"（登录页深蓝）| "light"（内容区淡色）
// position: "fixed"（全屏，登录页用）| "absolute"（仅父容器内，内容区用，不覆盖侧边栏）
export default function DynamicBackground({
  variant = "dark",
  position = "fixed",
}: {
  variant?: "dark" | "light";
  position?: "fixed" | "absolute";
}) {
  const dark = variant === "dark";
  const gradient = dark
    ? "linear-gradient(135deg, #0a3d91 0%, #1677ff 35%, #0a3d91 70%, #063a8c 100%)"
    : "linear-gradient(135deg, #e6f0ff 0%, #f0f7ff 30%, #e0ecff 60%, #eef4ff 100%)";
  const bubbleColor = dark ? "rgba(255,255,255,0.08)" : "rgba(22,119,255,0.06)";
  const starColor = dark ? "#fff" : "#1677ff";

  return (
    <div
      style={{
        position,
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: 0,
        overflow: "hidden",
        background: gradient,
        backgroundSize: "400% 400%",
        animation: "gradientShift 18s ease infinite",
      }}
    >
      {/* 漂浮光斑 */}
      <div style={{ ..._bubble(300, bubbleColor, "20%", "-10%", 25) }} />
      <div style={{ ..._bubble(450, bubbleColor, "65%", "10%", 32) }} />
      <div style={{ ..._bubble(350, bubbleColor, "40%", "30%", 28) }} />
      <div style={{ ..._bubble(500, bubbleColor, "85%", "50%", 35) }} />

      {/* 星光粒子 */}
      {Array.from({ length: 24 }).map((_, i) => (
        <div key={i} style={_star(i, starColor)} />
      ))}

      <style>{`
        @keyframes gradientShift {
          0% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
          100% { background-position: 0% 50%; }
        }
        @keyframes floatBubble {
          0%, 100% { transform: translate(0, 0) scale(1); }
          50% { transform: translate(60px, -60px) scale(1.15); }
        }
        @keyframes twinkle {
          0%, 100% { opacity: 0.2; transform: scale(0.8); }
          50% { opacity: 1; transform: scale(1.3); }
        }
      `}</style>
    </div>
  );
}

// 漂浮光斑样式
function _bubble(size: number, color: string, left: string, top: string, duration: number): CSSProperties {
  return {
    position: "absolute",
    left,
    top,
    width: size,
    height: size,
    borderRadius: "50%",
    background: color,
    filter: "blur(60px)",
    animation: `floatBubble ${duration}s ease-in-out infinite`,
  };
}

// 星光粒子样式（确定性伪随机）
function _star(i: number, color: string): CSSProperties {
  const left = `${(i * 41 + 13) % 100}%`;
  const top = `${(i * 67 + 29) % 100}%`;
  const size = 2 + (i % 3);
  const delay = (i % 10) * 0.6;
  const duration = 2.5 + (i % 5);
  return {
    position: "absolute",
    left,
    top,
    width: size,
    height: size,
    borderRadius: "50%",
    background: color,
    opacity: 0.5,
    animation: `twinkle ${duration}s ease-in-out ${delay}s infinite`,
  };
}
