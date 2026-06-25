import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api";
import { AuthForm } from "../components/AuthForm";
import { ChatPanel } from "../components/ChatPanel";
import { CoursePanel } from "../components/CoursePanel";
import { DeployPanel } from "../components/DeployPanel";
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
  const [aiModels, setAiModels] = useState([]);
  const [selectedModelId, setSelectedModelId] = useState("");
  const [leftPct, setLeftPct] = useState(28);
  const [centerPct, setCenterPct] = useState(44);
  const [editorPct, setEditorPct] = useState(60);
  const [leftCoursePct, setLeftCoursePct] = useState(65);
  const [isNarrow, setIsNarrow] = useState(
    typeof window !== "undefined" ? window.innerWidth <= 1200 : false
  );
  const mainRef = useRef(null);
  const centerRef = useRef(null);
  const leftColRef = useRef(null);

  const completedSet = useMemo(() => new Set(completed), [completed]);

  async function bootstrap() {
    const me = await api.me();
    setUser(me);

    // Course should always load, even if workspace/terminal setup fails.
    const [courseRes, progressRes, modelsRes] = await Promise.all([
      api.course(),
      api.progress(),
      api.aiModels().catch(() => ({ models: [], default_model_id: "" })),
    ]);
    const sessions = courseRes.sessions || [];
    setCourse(sessions);
    setSelectedSessionId((prev) => prev || sessions?.[0]?.id || "");
    setCompleted(progressRes.completed || []);
    const models = modelsRes.models || [];
    setAiModels(models);
    const chatModels = models.filter((m) => m.chat_eligible);
    const fallbackId = chatModels.length > 0 ? chatModels[0].id : "";
    setSelectedModelId(modelsRes.default_model_id || fallbackId);

    try {
      await api.workspaceStart();
      const filesRes = await api.filesTree();
      setFiles(filesRes.files || []);
    } catch {
      setFiles([]);
      setBanner("Workspace could not start. Try again in a few seconds.");
    }
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
    await api.chat(messages, { context, modelId: selectedModelId }, onDelta);
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

  function startLeftRowResize(evt) {
    evt.preventDefault();
    const col = leftColRef.current;
    if (!col) return;

    const HANDLE_PX = 10;
    const MIN_COURSE_PX = 120;
    const MIN_DEPLOY_PX = 80;

    const rect = col.getBoundingClientRect();
    const colHeight = rect.height;
    const startY = evt.clientY;
    const startCoursePx = (leftCoursePct / 100) * colHeight;

    const handle = evt.currentTarget;
    if (handle.setPointerCapture && typeof evt.pointerId === "number") {
      handle.setPointerCapture(evt.pointerId);
    }

    const onMove = (moveEvt) => {
      const deltaPx = moveEvt.clientY - startY;
      const maxCoursePx = Math.max(MIN_COURSE_PX, colHeight - MIN_DEPLOY_PX - HANDLE_PX);
      const nextCoursePx = Math.max(MIN_COURSE_PX, Math.min(maxCoursePx, startCoursePx + deltaPx));
      setLeftCoursePct((nextCoursePx / colHeight) * 100);
    };

    const onUp = (upEvt) => {
      if (handle.releasePointerCapture && typeof upEvt.pointerId === "number") {
        try { handle.releasePointerCapture(upEvt.pointerId); } catch { /* gone */ }
      }
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
      window.removeEventListener("blur", onUp);
      document.body.classList.remove("resizing");
    };

    document.body.classList.add("resizing");
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    window.addEventListener("blur", onUp);
  }

  function startRowResize(evt) {
    evt.preventDefault();
    const center = centerRef.current;
    if (!center) return;

    const HANDLE_PX = 10;
    const MIN_EDITOR_PX = 140;
    const MIN_TERMINAL_PX = 140;

    const rect = center.getBoundingClientRect();
    const centerHeight = rect.height;
    const startY = evt.clientY;
    const startEditorPx = (editorPct / 100) * centerHeight;

    const handle = evt.currentTarget;
    if (handle.setPointerCapture && typeof evt.pointerId === "number") {
      handle.setPointerCapture(evt.pointerId);
    }

    const onMove = (moveEvt) => {
      const deltaPx = moveEvt.clientY - startY;
      const maxEditorPx = Math.max(MIN_EDITOR_PX, centerHeight - MIN_TERMINAL_PX - HANDLE_PX);
      const nextEditorPx = Math.max(MIN_EDITOR_PX, Math.min(maxEditorPx, startEditorPx + deltaPx));
      setEditorPct((nextEditorPx / centerHeight) * 100);
    };

    const onUp = (upEvt) => {
      if (handle.releasePointerCapture && typeof upEvt.pointerId === "number") {
        try {
          handle.releasePointerCapture(upEvt.pointerId);
        } catch {
          // No-op: capture may already be gone.
        }
      }
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
      window.removeEventListener("blur", onUp);
      document.body.classList.remove("resizing");
    };

    document.body.classList.add("resizing");
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    window.addEventListener("blur", onUp);
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
        <div
          ref={leftColRef}
          className="left-col"
          style={
            isNarrow
              ? undefined
              : { gridTemplateRows: `${leftCoursePct}fr 10px ${Math.max(8, 100 - leftCoursePct)}fr` }
          }
        >
          <CoursePanel
            sessions={course}
            selectedSessionId={selectedSessionId}
            onSelectSession={setSelectedSessionId}
            completedSet={completedSet}
            onToggleStep={toggleStep}
          />
          {!isNarrow && (
            <div
              className="resize-handle horizontal"
              onPointerDown={startLeftRowResize}
              title="Drag to resize course and deploy panels"
            />
          )}
          <DeployPanel />
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
              onPointerDown={startRowResize}
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
        <ChatPanel
          onSend={sendChat}
          models={aiModels}
          selectedModelId={selectedModelId}
          onSelectModel={setSelectedModelId}
        />
        </div>
      </main>
    </div>
  );
}
