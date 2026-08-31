import loginBg from "../assets/login-bg.png";

// 动态壁纸背景
// variant: "dark"（登录页·真实图片 + 深色遮罩）| "light"（内容区·真实图片 + 白色遮罩）
// position: "fixed"（全屏，登录页用）| "absolute"（仅父容器内，内容区用，不遮挡侧边栏）
export default function DynamicBackground({
  variant = "dark",
  position = "fixed",
}: {
  variant?: "dark" | "light";
  position?: "fixed" | "absolute";
}) {
  const dark = variant === "dark";

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
        background: dark ? "#0a1628" : "#f5f7fa",
      }}
    >
      {dark ? <PhotoScene /> : <LightScene />}
    </div>
  );
}

// 内容区场景：同一张真实图片，原色显示（不加白色遮罩，图片清晰可见，不遮挡侧边栏）
function LightScene() {
  return (
    <>
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundImage: `url(${loginBg})`,
          backgroundSize: "cover",
          backgroundPosition: "center",
          // 原图清晰显示，只轻微压暗保证白字可读（卡片本身白底不受影响）
          filter: "saturate(1.2) contrast(1.08) brightness(0.85)",
        }}
      />
    </>
  );
}

// 登录页真实图片场景：图片背景 + 半透明深色遮罩（保证文字可读）+ 缓慢缩放
function PhotoScene() {
  return (
    <>
      {/* 真实图片背景（缓慢缩放 Ken Burns 效果） */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundImage: `url(${loginBg})`,
          backgroundSize: "cover",
          backgroundPosition: "center",
          animation: "kenBurns 30s ease-in-out infinite alternate",
        }}
      />
      {/* 半透明深色遮罩（保证白色文字清晰） */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: "linear-gradient(135deg, rgba(10,22,40,0.65) 0%, rgba(10,22,40,0.35) 50%, rgba(10,22,40,0.55) 100%)",
        }}
      />
      <style>{`
        @keyframes kenBurns {
          0% { transform: scale(1); }
          100% { transform: scale(1.08); }
        }
      `}</style>
    </>
  );
}
