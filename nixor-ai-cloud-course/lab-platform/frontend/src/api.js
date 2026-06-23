export class ApiClient {
  constructor() {
    this.base = "";
    this.token = localStorage.getItem("nixor_token") || "";
  }

  setToken(token) {
    this.token = token;
    if (token) {
      localStorage.setItem("nixor_token", token);
    } else {
      localStorage.removeItem("nixor_token");
    }
  }

  _headers(extra = {}) {
    const headers = { ...extra };
    if (this.token) {
      headers.Authorization = `Bearer ${this.token}`;
    }
    return headers;
  }

  async _json(path, options = {}) {
    const res = await fetch(`${this.base}${path}`, {
      ...options,
      headers: this._headers({ "Content-Type": "application/json", ...(options.headers || {}) }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Request failed (${res.status})`);
    }
    return res.json();
  }

  signup(payload) {
    return this._json("/api/auth/signup", { method: "POST", body: JSON.stringify(payload) });
  }

  login(payload) {
    return this._json("/api/auth/login", { method: "POST", body: JSON.stringify(payload) });
  }

  me() {
    return this._json("/api/auth/me");
  }

  course() {
    return this._json("/api/course");
  }

  progress() {
    return this._json("/api/progress");
  }

  setProgress(stepId, completed = true) {
    return this._json("/api/progress", {
      method: "POST",
      body: JSON.stringify({ step_id: stepId, completed }),
    });
  }

  workspaceStart() {
    return this._json("/api/workspace/start", { method: "POST" });
  }

  workspaceStatus() {
    return this._json("/api/workspace/status");
  }

  filesTree() {
    return this._json("/api/files/tree");
  }

  readFile(path) {
    return this._json(`/api/files?path=${encodeURIComponent(path)}`);
  }

  writeFile(path, content) {
    return this._json("/api/files", {
      method: "PUT",
      body: JSON.stringify({ path, content }),
    });
  }

  async chat(messages, context, onDelta) {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: this._headers({ "Content-Type": "application/json" }),
      body: JSON.stringify({ messages, context }),
    });
    if (!res.ok || !res.body) {
      throw new Error("Chat request failed");
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() || "";
      for (const evt of events) {
        const line = evt.split("\n").find((l) => l.startsWith("data:"));
        if (!line) continue;
        const payload = JSON.parse(line.slice(5).trim());
        onDelta(payload);
      }
    }
  }
}

export const api = new ApiClient();
