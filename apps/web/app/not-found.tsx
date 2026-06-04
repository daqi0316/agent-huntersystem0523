export default function NotFound() {
  return (
    <div
      style={{
        display: "flex",
        minHeight: "60vh",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "16px",
        padding: "24px",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <div
        style={{
          fontSize: "72px",
          fontWeight: 700,
          color: "rgba(0,0,0,0.2)",
          lineHeight: 1,
        }}
      >
        404
      </div>
      <h2 style={{ fontSize: "18px", fontWeight: 600, margin: 0 }}>
        页面不存在
      </h2>
      <p
        style={{
          fontSize: "14px",
          color: "#666",
          maxWidth: "420px",
          textAlign: "center",
          margin: 0,
        }}
      >
        你访问的页面不存在或已被移动。
      </p>
      <a
        href="/"
        style={{
          padding: "8px 16px",
          borderRadius: "6px",
          background: "#18181b",
          color: "white",
          textDecoration: "none",
          fontSize: "14px",
        }}
      >
        回到首页
      </a>
    </div>
  );
}
