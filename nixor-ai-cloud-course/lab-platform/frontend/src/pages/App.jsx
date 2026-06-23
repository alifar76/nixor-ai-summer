import { useEffect, useMemo, useRef, useState } from "react";

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
  const [leftPct, setLeftPct] = useState(28);
  const [centerPct, setCenterPct] = useState(44);
  const [editorPct, setEditorPct] = useState(60);
  const [isNarrow, setIsNarrow] = useState(
    typeof window !== "undefined" ? window.innerWidth <= 1200 : false
  );
  const mainRef = useRef(null);
  const centerRef = useRef(null);

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

  useEffect(() => {
    const onResize = () => setIsNarrow(window.innerWidth <= 1200);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
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

  function startColumnResize(edge) {
    const onMove = (evt) => {
      const main = mainRef.current;
      if (!main) return;
      const rect = main.getBoundingClientRect();
      const x = Math.max(0, Math.min(rect.width, evt.clientX - rect.left));
      const xPct = (x / rect.width) * 100;
      if (edge === "left") {
        const nextLeft = Math.max(14, Math.min(60, xPct));
        const maxLeft = 84 - centerPct;
        setLeftPct(Math.min(nextLeft, maxLeft));
      } else {
        const nextCenter = Math.max(22, Math.min(68, xPct - leftPct));
        const maxCenter = 84 - leftPct;
        setCenterPct(Math.min(nextCenter, maxCenter));
      }
    };

    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.classList.remove("resizing");
    };

    document.body.classList.add("resizing");
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }

  function startRowResize(evt) {
    evt.preventDefault();
    const onMove = (evt) => {
      const center = centerRef.current;
      if (!center) return;
      const rect = center.getBoundingClientRect();
      const y = evt.clientY - rect.top;
      const next = (y / rect.height) * 100;
      setEditorPct(Math.max(25, Math.min(85, next)));
    };

    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.classList.remove("resizing");
    };

    document.body.classList.add("resizing");
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }

  if (!ready) {
    return <div className="loading">Loading...</div>;
  }

  if (!user) {
    return <AuthForm onAuth={handleAuth} />;
  }

  const total = course.reduce((n, s) => n + (s.steps?.length || 0), 0);
  const progressPct = total > 0 ? Math.round((completed.length / total) * 100) : 0;
  const rightPct = Math.max(16, 100 - leftPct - centerPct);

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

      <main
        ref={mainRef}
        style={
          isNarrow
            ? undefined
            : { gridTemplateColumns: `${leftPct}fr 10px ${centerPct}fr 10px ${rightPct}fr` }
        }
      >
        <div className="left-col">
          <CoursePanel
            sessions={course}
            selectedSessionId={selectedSessionId}
            onSelectSession={setSelectedSessionId}
            completedSet={completedSet}
            onToggleStep={toggleStep}
          />
        </div>

        {!isNarrow && (
          <div
            className="resize-handle vertical"
            onMouseDown={() => startColumnResize("left")}
            title="Drag to resize panels"
          />
        )}

        <div
          ref={centerRef}
          className="center-col"
          style={
            isNarrow
              ? undefined
              : { gridTemplateRows: `${editorPct}fr 10px ${Math.max(18, 100 - editorPct)}fr` }
          }
        >
          <EditorPanel
            files={files}
            selectedFile={selectedFile}
            content={loadingFile ? "Loading..." : content}
            onOpenFile={openFile}
            onChangeContent={setContent}
            onSave={saveFile}
          />
          {!isNarrow && (
            <div
              className="resize-handle horizontal"
              onMouseDown={startRowResize}
              title="Drag to resize editor and terminal"
            />
          )}
          <TerminalPanel token={api.token} />
        </div>

        {!isNarrow && (
          <div
            className="resize-handle vertical"
            onMouseDown={() => startColumnResize("center")}
            title="Drag to resize panels"
          />
        )}

        <div className="right-col">
          <ChatPanel onSend={sendChat} />
        </div>
      </main>
    </div>
  );
}
