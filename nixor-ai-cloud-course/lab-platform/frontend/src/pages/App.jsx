import { useEffect, useMemo, useState } from "react";

import { api } from "../api";
import { AuthForm } from "../components/AuthForm";
import { ChatPanel } from "../components/ChatPanel";
import { CoursePanel } from "../components/CoursePanel";
import { EditorPanel } from "../components/EditorPanel";
import { TerminalPanel } from "../components/TerminalPanel";

export function App() {
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState(null);
  const [course, setCourse] = useState([]);
  const [completed, setCompleted] = useState([]);
  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [files, setFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState("");
  const [content, setContent] = useState("");
  const [loadingFile, setLoadingFile] = useState(false);
  const [banner, setBanner] = useState("");

  const completedSet = useMemo(() => new Set(completed), [completed]);

  async function bootstrap() {
    const me = await api.me();
    setUser(me);

    await api.workspaceStart();

    const [courseRes, progressRes, filesRes] = await Promise.all([
      api.course(),
      api.progress(),
      api.filesTree(),
    ]);
    setCourse(courseRes.sessions || []);
    setSelectedSessionId(courseRes.sessions?.[0]?.id || "");
    setCompleted(progressRes.completed || []);
    setFiles(filesRes.files || []);
  }

  useEffect(() => {
    if (!api.token) {
      setReady(true);
      return;
    }
    bootstrap().catch(() => api.setToken(""))
      .finally(() => setReady(true));
  }, []);

  async function handleAuth({ mode, email, password, name, accessCode }) {
    const data =
      mode === "login"
        ? await api.login({ email, password })
        : await api.signup({ email, password, name, access_code: accessCode });
    api.setToken(data.access_token);
    await bootstrap();
  }

  async function openFile(path) {
    setSelectedFile(path);
    setLoadingFile(true);
    try {
      const data = await api.readFile(path);
      setContent(data.content || "");
    } finally {
      setLoadingFile(false);
    }
  }

  async function saveFile() {
    if (!selectedFile) return;
    await api.writeFile(selectedFile, content);
    setBanner(`Saved ${selectedFile}`);
    setTimeout(() => setBanner(""), 1200);
  }

  async function toggleStep(stepId, checked) {
    const res = await api.setProgress(stepId, checked);
    setCompleted(res.completed || []);
  }

  async function sendChat(messages, onDelta) {
    const context = selectedFile ? `File: ${selectedFile}\n\n${content.slice(0, 5000)}` : "";
    await api.chat(messages, context, onDelta);
  }

  if (!ready) {
    return <div className="loading">Loading...</div>;
  }

  if (!user) {
    return <AuthForm onAuth={handleAuth} />;
  }

  const total = course.reduce((n, s) => n + (s.steps?.length || 0), 0);
  const progressPct = total > 0 ? Math.round((completed.length / total) * 100) : 0;

  return (
    <div className="app-shell">
      <header>
        <div>
          <h1>Nixor AI Lab</h1>
          <p>{user.email}</p>
        </div>
        <div className="header-actions">
          <div className="progress">Progress: {completed.length}/{total} ({progressPct}%)</div>
          <button onClick={() => { api.setToken(""); window.location.reload(); }}>Logout</button>
        </div>
      </header>

      {banner && <div className="banner">{banner}</div>}

      <main>
        <div className="left-col">
          <CoursePanel
            sessions={course}
            selectedSessionId={selectedSessionId}
            onSelectSession={setSelectedSessionId}
            completedSet={completedSet}
            onToggleStep={toggleStep}
          />
        </div>

        <div className="center-col">
          <EditorPanel
            files={files}
            selectedFile={selectedFile}
            content={loadingFile ? "Loading..." : content}
            onOpenFile={openFile}
            onChangeContent={setContent}
            onSave={saveFile}
          />
          <TerminalPanel token={api.token} />
        </div>

        <div className="right-col">
          <ChatPanel onSend={sendChat} />
        </div>
      </main>
    </div>
  );
}
