import { useState } from "react";

export function ChatPanel({ onSend, models = [], selectedModelId = "", onSelectModel = () => {} }) {
  const chatModels = models.filter((m) => m.chat_eligible);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "I can help you with code, errors, and deployment steps.",
    },
  ]);
  const [loading, setLoading] = useState(false);

  async function submit(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    const next = [...messages, { role: "user", content: text }, { role: "assistant", content: "" }];
    setMessages(next);
    setLoading(true);

    try {
      await onSend(next.filter((m) => m.role !== "assistant" || m.content), (delta) => {
        if (delta.error) {
          setMessages((prev) => {
            const copy = [...prev];
            copy[copy.length - 1] = { role: "assistant", content: delta.error };
            return copy;
          });
          return;
        }
        if (delta.delta) {
          setMessages((prev) => {
            const copy = [...prev];
            const last = copy[copy.length - 1];
            copy[copy.length - 1] = { ...last, content: (last.content || "") + delta.delta };
            return copy;
          });
        }
      });
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel chat-panel">
      <div className="panel-header">
        <h2>Coding Chatbot</h2>
        {chatModels.length > 0 && (
          <select
            className="chat-model-select"
            value={selectedModelId}
            onChange={(e) => onSelectModel(e.target.value)}
            title="Select chatbot model"
          >
            {chatModels.map((m) => (
              <option key={m.id} value={m.id}>{m.label}</option>
            ))}
          </select>
        )}
      </div>
      <div className="chat-log">
        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>
            <strong>{m.role === "user" ? "You" : "AI"}</strong>
            <p>{m.content}</p>
          </div>
        ))}
      </div>
      <form className="chat-input" onSubmit={submit}>
        <input
          placeholder="Ask for help with code or errors..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button disabled={loading} type="submit">Send</button>
      </form>
      {models.length > 0 && (
        <div className="ai-model-grid">
          {models.map((m) => (
            <div key={m.id} className="ai-model-card">
              <strong>{m.label}</strong>
              <span>{m.provider}</span>
              <small>in: {(m.input || []).join(", ") || "-"}</small>
              <small>out: {(m.output || []).join(", ") || "-"}</small>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
