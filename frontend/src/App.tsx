import { createContext, useState } from "react";
import { Link, Route, Routes } from "react-router-dom";
import { ChatPanel } from "./components/ChatPanel";
import { RepoGraphPage } from "./pages/RepoGraphPage";
import { RepoListPage } from "./pages/RepoListPage";
import { ReviewDetailPage } from "./pages/ReviewDetailPage";
import { ReviewListPage } from "./pages/ReviewListPage";
import { brand, colors } from "./theme";
import type { ChatMessage, ReviewRun } from "./types";

/* ── Chat context ────────────────────────────────────────────── */

interface ChatCtx {
  isOpen: boolean;
  openChat: (run?: ReviewRun) => void;
  closeChat: () => void;
}

export const ChatContext = createContext<ChatCtx>({
  isOpen: false,
  openChat: () => undefined,
  closeChat: () => undefined,
});

/* ── Nav bar ─────────────────────────────────────────────────── */

function NavBar({ onOpenChat }: { onOpenChat: () => void }) {
  return (
    <header style={{
      position: "fixed", top: 0, left: 0, right: 0, zIndex: 100,
      height: 56,
      background: "rgba(5,8,16,0.85)",
      backdropFilter: "blur(20px)",
      borderBottom: `1px solid ${colors.border}`,
      display: "flex", alignItems: "center", padding: "0 24px", gap: 16,
    }}>
      {/* Brand */}
      <Link to="/" style={{ display: "flex", alignItems: "center", gap: 10, textDecoration: "none" }}>
        <img src="/logo.png" alt="AutomatonsX" style={{ height: 32, width: "auto" }} />
        <span style={{ fontSize: 16, fontWeight: 800, color: colors.text, letterSpacing: "-0.01em" }}>
          {brand.name}
        </span>
      </Link>

      {/* Tagline */}
      <span style={{ fontSize: 12, color: colors.muted, display: "none" as const }}
        className="tagline">
        {brand.tagline}
      </span>

      {/* Nav links */}
      <Link
        to="/repos"
        style={{
          fontSize: 13, color: colors.muted, textDecoration: "none", fontWeight: 500,
          marginLeft: 16,
          transition: "color 0.15s",
        }}
        onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = colors.text; }}
        onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = colors.muted; }}
      >
        Repos
      </Link>

      {/* Live indicator */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginLeft: "auto" }}>
        <span className="pulse-dot" style={{
          width: 7, height: 7, borderRadius: "50%", background: colors.status.done,
          display: "inline-block", boxShadow: `0 0 8px ${colors.status.done}`,
        }} />
        <span style={{ fontSize: 12, color: colors.muted }}>Live</span>
      </div>

      {/* Ask AI button */}
      <button
        onClick={onOpenChat}
        style={{
          display: "flex", alignItems: "center", gap: 8,
          background: `linear-gradient(135deg, ${colors.accent}22, #C301B122)`,
          border: `1px solid ${colors.accent}40`,
          borderRadius: 8, padding: "7px 14px",
          color: colors.text, fontSize: 13, fontWeight: 600, cursor: "pointer",
          transition: "all 0.15s",
        }}
        onMouseEnter={e => {
          const el = e.currentTarget as HTMLElement;
          el.style.background = `linear-gradient(135deg, ${colors.accent}33, #C301B133)`;
          el.style.borderColor = `${colors.accent}80`;
        }}
        onMouseLeave={e => {
          const el = e.currentTarget as HTMLElement;
          el.style.background = `linear-gradient(135deg, ${colors.accent}22, #C301B122)`;
          el.style.borderColor = `${colors.accent}40`;
        }}
      >
        <span style={{ fontSize: 14 }}>✦</span> Ask AI
      </button>
    </header>
  );
}

/* ── App ─────────────────────────────────────────────────────── */

export function App() {
  const [chatOpen,     setChatOpen]     = useState(false);
  const [chatRun,      setChatRun]      = useState<ReviewRun | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);

  const openChat = (run?: ReviewRun) => {
    const next = run ?? null;
    // clear messages when switching context
    if (next?.id !== chatRun?.id) setChatMessages([]);
    setChatRun(next);
    setChatOpen(true);
  };

  const closeChat = () => setChatOpen(false);

  return (
    <ChatContext.Provider value={{ isOpen: chatOpen, openChat, closeChat }}>
      <NavBar onOpenChat={() => openChat()} />

      {/* Main content — shifts left when chat is open */}
      <div style={{
        paddingTop: 56,           // nav height
        paddingRight: chatOpen ? 400 : 0,
        transition: "padding-right 0.28s cubic-bezier(0.4,0,0.2,1)",
        minHeight: "100vh",
      }}>
        <div style={{ maxWidth: 1100, margin: "0 auto", padding: "32px 24px" }}>
          <Routes>
            <Route path="/"                          element={<ReviewListPage />} />
            <Route path="/reviews/:reviewRunId"      element={<ReviewDetailPage />} />
            <Route path="/repos"                     element={<RepoListPage />} />
            <Route path="/repos/:repoId/graph"       element={<RepoGraphPage />} />
          </Routes>
        </div>

        {/* Footer */}
        <div style={{
          textAlign: "center", padding: "24px 0",
          borderTop: `1px solid ${colors.border}`,
          color: colors.muted, fontSize: 12,
        }}>
          {brand.team} · <span style={{ color: colors.accent }}>{brand.name}</span>
        </div>
      </div>

      {/* Chat panel */}
      {chatOpen && (
        <ChatPanel
          onClose={closeChat}
          reviewRun={chatRun}
          messages={chatMessages}
          onMessages={setChatMessages}
        />
      )}
    </ChatContext.Provider>
  );
}
