import { useEffect, useRef, useState } from "react";
import { sendChat } from "../api/client";
import { colors } from "../theme";
import type { ChatMessage, ReviewRun } from "../types";

const SUGGESTED: Record<string, string[]> = {
  global: [
    "What was the highest risk finding across all PRs?",
    "Are there any security issues in recent reviews?",
    "Summarize all reviewed pull requests",
    "Which PRs have blocking or major findings?",
  ],
  pr: [
    "Why was this code changed?",
    "What are the main risks in this PR?",
    "Explain the blast radius analysis",
    "What did the critic filter out and why?",
  ],
};

function useTypewriter(text: string, active: boolean): string {
  const [out, setOut] = useState(active ? "" : text);
  useEffect(() => {
    if (!active) { setOut(text); return; }
    setOut("");
    let i = 0;
    const id = setInterval(() => {
      i++;
      setOut(text.slice(0, i));
      if (i >= text.length) clearInterval(id);
    }, 10);
    return () => clearInterval(id);
  }, [text, active]);
  return out;
}

function SimpleMarkdown({ text }: { text: string }) {
  const html = text
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    .replace(/^- (.+)$/gm, "<li>$1</li>")
    .replace(/(<li>.*<\/li>)/s, "<ul>$1</ul>")
    .replace(/\n\n/g, "<br/><br/>")
    .replace(/\n/g, "<br/>");
  return <div className="md-content" dangerouslySetInnerHTML={{ __html: html }} />;
}

function Message({ msg, isLast }: { msg: ChatMessage; isLast: boolean }) {
  const isUser = msg.role === "user";
  const displayed = useTypewriter(msg.content, !isUser && isLast);

  const typing = !isUser && isLast && displayed.length < msg.content.length;

  return (
    <div style={{
      display: "flex",
      justifyContent: isUser ? "flex-end" : "flex-start",
      marginBottom: 12,
      animation: "fadeUp 0.2s ease-out both",
    }}>
      {!isUser && (
        <div style={{
          width: 26, height: 26, borderRadius: "50%",
          background: `linear-gradient(135deg, ${colors.accent}, #4FB6FF)`,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 12, fontWeight: 700, color: "#fff",
          marginRight: 8, flexShrink: 0, marginTop: 2,
        }}>S</div>
      )}
      <div style={{
        maxWidth: "82%",
        background: isUser ? colors.accent : colors.surface2,
        border: `1px solid ${isUser ? "transparent" : colors.border}`,
        borderRadius: isUser ? "16px 16px 4px 16px" : "16px 16px 16px 4px",
        padding: "10px 14px",
        fontSize: 13, lineHeight: 1.6,
        color: isUser ? "#fff" : colors.text,
      }}>
        {isUser ? <span>{displayed}</span> : (
          <>
            <SimpleMarkdown text={displayed} />
            {typing && <span style={{ animation: "blink 0.8s ease-in-out infinite" }}>▌</span>}
          </>
        )}
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
      <div style={{
        width: 26, height: 26, borderRadius: "50%",
        background: `linear-gradient(135deg, ${colors.accent}, #4FB6FF)`,
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 12, fontWeight: 700, color: "#fff", flexShrink: 0,
      }}>S</div>
      <div style={{
        background: colors.surface2, border: `1px solid ${colors.border}`,
        borderRadius: "16px 16px 16px 4px", padding: "12px 16px",
        display: "flex", gap: 4,
      }}>
        {[0, 1, 2].map(i => (
          <span key={i} style={{
            width: 6, height: 6, borderRadius: "50%",
            background: colors.muted, display: "inline-block",
            animation: `pulseDot 1.2s ease-in-out ${i * 0.2}s infinite`,
          }} />
        ))}
      </div>
    </div>
  );
}

interface Props {
  onClose: () => void;
  reviewRun?: ReviewRun | null;
  messages: ChatMessage[];
  onMessages: (msgs: ChatMessage[]) => void;
}

export function ChatPanel({ onClose, reviewRun, messages, onMessages }: Props) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const send = async (text: string) => {
    const q = text.trim();
    if (!q || loading) return;
    setInput("");

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: q,
      timestamp: new Date().toISOString(),
    };
    onMessages([...messages, userMsg]);
    setLoading(true);

    try {
      const res = await sendChat(q, reviewRun?.id);
      const aiMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: res.response,
        timestamp: new Date().toISOString(),
      };
      onMessages([...messages, userMsg, aiMsg]);
    } catch {
      const errMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: "Sorry, I couldn't reach the backend. Make sure the server is running.",
        timestamp: new Date().toISOString(),
      };
      onMessages([...messages, userMsg, errMsg]);
    } finally {
      setLoading(false);
    }
  };

  const suggestions = reviewRun ? SUGGESTED.pr : SUGGESTED.global;

  return (
    <div
      className="slide-in-r"
      style={{
        position: "fixed", top: 0, right: 0, bottom: 0,
        width: 400, zIndex: 200,
        background: colors.surface,
        borderLeft: `1px solid ${colors.border}`,
        display: "flex", flexDirection: "column",
        boxShadow: "-4px 0 40px rgba(0,0,0,0.4)",
      }}
    >
      {/* Header */}
      <div style={{
        padding: "16px 20px",
        borderBottom: `1px solid ${colors.border}`,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        flexShrink: 0,
        background: `linear-gradient(135deg, ${colors.surface} 0%, rgba(59,130,246,0.05) 100%)`,
      }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{
              width: 28, height: 28, borderRadius: "50%",
              background: `linear-gradient(135deg, ${colors.accent}, #4FB6FF)`,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 14, fontWeight: 800, color: "#fff",
            }}>S</div>
            <span style={{ fontWeight: 700, fontSize: 15, color: colors.text }}>Code Review Agent AI</span>
          </div>
          <div style={{ marginTop: 4, display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{
              fontSize: 11, padding: "2px 8px", borderRadius: 20,
              background: reviewRun ? colors.accentDim : colors.surface3,
              color: reviewRun ? colors.accent : colors.muted,
              fontWeight: 600,
            }}>
              {reviewRun ? `PR #${reviewRun.pr_number} · ${reviewRun.repo_full_name}` : "All PRs"}
            </span>
          </div>
        </div>
        <button
          onClick={onClose}
          style={{
            background: "none", border: "none", cursor: "pointer",
            color: colors.muted, fontSize: 18, padding: 4,
            borderRadius: 6, transition: "color 0.15s",
          }}
          title="Close"
        >✕</button>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", padding: "16px 16px 0" }}>
        {messages.length === 0 ? (
          <div className="fade-in" style={{ textAlign: "center", padding: "32px 16px" }}>
            <div style={{ fontSize: 36, marginBottom: 12 }}>✦</div>
            <p style={{ color: colors.text, fontWeight: 600, marginBottom: 4 }}>
              Ask me anything
            </p>
            <p style={{ color: colors.muted, fontSize: 13, marginBottom: 24 }}>
              {reviewRun
                ? "I have full context on this PR — findings, risk analysis, and change summary."
                : "I can answer questions about all reviewed pull requests."}
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {suggestions.map(s => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  style={{
                    background: colors.surface2, border: `1px solid ${colors.border}`,
                    borderRadius: 8, padding: "8px 12px",
                    color: colors.text, fontSize: 12, cursor: "pointer",
                    textAlign: "left", transition: "border-color 0.15s, background 0.15s",
                  }}
                  onMouseEnter={e => { (e.target as HTMLElement).style.borderColor = colors.accent; }}
                  onMouseLeave={e => { (e.target as HTMLElement).style.borderColor = colors.border; }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {messages.map((msg, i) => (
              <Message key={msg.id} msg={msg} isLast={i === messages.length - 1} />
            ))}
            {loading && <TypingIndicator />}
            <div ref={bottomRef} />
          </>
        )}
      </div>

      {/* Input */}
      <div style={{
        padding: 12, borderTop: `1px solid ${colors.border}`, flexShrink: 0,
        background: colors.surface,
      }}>
        <div style={{
          display: "flex", alignItems: "flex-end", gap: 8,
          background: colors.surface2, border: `1px solid ${colors.border}`,
          borderRadius: 12, padding: "8px 12px",
          transition: "border-color 0.2s",
        }}
          onFocus={e => { (e.currentTarget as HTMLElement).style.borderColor = colors.accent; }}
          onBlur={e => { (e.currentTarget as HTMLElement).style.borderColor = colors.border; }}
        >
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); }
            }}
            placeholder="Ask about your pull requests…"
            rows={1}
            style={{
              flex: 1, background: "none", border: "none", outline: "none",
              color: colors.text, fontSize: 13, lineHeight: 1.5, resize: "none",
              fontFamily: "inherit",
            }}
          />
          <button
            onClick={() => send(input)}
            disabled={!input.trim() || loading}
            style={{
              background: input.trim() && !loading ? colors.accent : colors.surface3,
              border: "none", borderRadius: 8, cursor: input.trim() && !loading ? "pointer" : "default",
              color: "#fff", padding: "6px 12px", fontSize: 13, fontWeight: 600,
              transition: "background 0.15s", flexShrink: 0,
            }}
          >
            {loading ? <span className="spin" style={{ display: "inline-block" }}>↻</span> : "↑"}
          </button>
        </div>
        <p style={{ fontSize: 11, color: colors.muted, textAlign: "center", marginTop: 6 }}>
          Enter to send · Shift+Enter for newline
        </p>
      </div>
    </div>
  );
}
