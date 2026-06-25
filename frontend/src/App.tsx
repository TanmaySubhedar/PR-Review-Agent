import { Link, Route, Routes } from "react-router-dom";
import { ReviewDetailPage } from "./pages/ReviewDetailPage";
import { ReviewListPage } from "./pages/ReviewListPage";
import { brand, colors } from "./theme";

function Header() {
  return (
    <header
      style={{
        display: "flex",
        alignItems: "baseline",
        gap: 12,
        padding: "20px 24px",
        borderBottom: `1px solid ${colors.line}`,
      }}
    >
      <Link to="/" style={{ textDecoration: "none", display: "flex", alignItems: "baseline", gap: 10 }}>
        <span
          style={{
            display: "inline-block",
            width: 14,
            height: 14,
            borderRadius: 4,
            background: colors.accent,
          }}
        />
        <span style={{ fontSize: 20, fontWeight: 800, color: colors.ink }}>{brand.name}</span>
      </Link>
      <span style={{ color: colors.muted, fontSize: 14 }}>{brand.tagline}</span>
    </header>
  );
}

function Footer() {
  return (
    <footer
      style={{
        textAlign: "center",
        padding: "24px 0",
        color: colors.muted,
        fontSize: 13,
        borderTop: `1px solid ${colors.line}`,
        marginTop: 40,
      }}
    >
      {brand.team}
    </footer>
  );
}

export function App() {
  return (
    <div style={{ fontFamily: "sans-serif", color: colors.ink, minHeight: "100vh" }}>
      <Header />
      <div style={{ maxWidth: 960, margin: "0 auto", padding: 24 }}>
        <Routes>
          <Route path="/" element={<ReviewListPage />} />
          <Route path="/reviews/:reviewRunId" element={<ReviewDetailPage />} />
        </Routes>
      </div>
      <Footer />
    </div>
  );
}
