import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../lib/api";

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string) ?? "";

async function login(email: string, password: string): Promise<string> {
  const body = new URLSearchParams({ username: email, password });
  const res = await fetch(`${BASE_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = (await res.json()) as { detail?: string };
      detail = data.detail ?? detail;
    } catch {
      // non-JSON
    }
    throw new ApiError(res.status, detail);
  }
  const data = (await res.json()) as { access_token: string };
  return data.access_token;
}

export function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const token = await login(email, password);
      localStorage.setItem("ws_token", token);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{
      minHeight: "100vh",
      background: "var(--color-bg-canvas)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
    }}>
      <div style={{
        width: "340px",
        background: "var(--color-bg-surface)",
        border: "1px solid var(--color-border-subtle)",
        padding: "40px 36px",
      }}>
        {/* Wordmark */}
        <div style={{ marginBottom: "32px", textAlign: "center" }}>
          <div style={{
            fontFamily: "var(--font-display)",
            fontSize: "26px",
            fontStyle: "italic",
            color: "var(--color-text-primary)",
            marginBottom: "4px",
          }}>
            WSRE Intelligence
          </div>
          <div style={{
            fontSize: "9px",
            fontWeight: 700,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--color-text-tertiary)",
          }}>
            Market Intelligence
          </div>
        </div>

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <label style={labelStyle}>Email</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              autoFocus
              style={inputStyle}
              placeholder="analyst@whitestarksa.com"
            />
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <label style={labelStyle}>Password</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              style={inputStyle}
            />
          </div>

          {error && (
            <div style={{
              fontSize: "11px",
              color: "#f87171",
              fontFamily: "var(--font-mono)",
              padding: "8px 10px",
              border: "1px solid rgba(248,113,113,0.3)",
              background: "rgba(248,113,113,0.05)",
            }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              marginTop: "8px",
              padding: "10px",
              background: loading ? "var(--color-bg-canvas)" : "var(--color-accent)",
              color: loading ? "var(--color-text-tertiary)" : "#0a0a0a",
              border: "1px solid var(--color-accent)",
              fontFamily: "var(--font-mono)",
              fontSize: "11px",
              fontWeight: 700,
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              cursor: loading ? "not-allowed" : "pointer",
            }}
          >
            {loading ? "Authenticating…" : "Sign In"}
          </button>
        </form>

        <div style={{
          marginTop: "28px",
          paddingTop: "16px",
          borderTop: "1px solid var(--color-border-subtle)",
          fontSize: "10px",
          color: "var(--color-text-tertiary)",
          textAlign: "center",
          fontFamily: "var(--font-mono)",
        }}>
          Internal use only · Riyadh, KSA
        </div>
      </div>
    </div>
  );
}

const labelStyle: React.CSSProperties = {
  fontSize: "9px",
  fontWeight: 700,
  letterSpacing: "0.14em",
  textTransform: "uppercase",
  color: "var(--color-text-tertiary)",
};

const inputStyle: React.CSSProperties = {
  padding: "9px 12px",
  background: "var(--color-bg-canvas)",
  border: "1px solid var(--color-border-subtle)",
  color: "var(--color-text-primary)",
  fontFamily: "var(--font-mono)",
  fontSize: "13px",
  outline: "none",
  width: "100%",
  boxSizing: "border-box",
};
