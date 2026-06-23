import { useState } from "react";

export function AuthForm({ onAuth }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [accessCode, setAccessCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await onAuth({ mode, email, password, name, accessCode });
    } catch (err) {
      setError(err.message || "Could not sign in");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-shell">
      <form className="auth-card" onSubmit={submit}>
        <h1>Nixor AI Lab</h1>
        <p>Sign in to start coding in your browser workspace.</p>

        {mode === "signup" && (
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
        )}

        <label>
          Email
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>

        <label>
          Password
          <input
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>

        {mode === "signup" && (
          <label>
            Access Code (optional)
            <input value={accessCode} onChange={(e) => setAccessCode(e.target.value)} />
          </label>
        )}

        {error && <div className="error">{error}</div>}

        <button disabled={loading} type="submit">
          {loading ? "Please wait..." : mode === "login" ? "Login" : "Create Account"}
        </button>

        <button
          type="button"
          className="link"
          onClick={() => setMode(mode === "login" ? "signup" : "login")}
        >
          {mode === "login" ? "Need an account? Sign up" : "Already have an account? Login"}
        </button>
      </form>
    </div>
  );
}
