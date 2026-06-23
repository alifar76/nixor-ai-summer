import { useEffect, useMemo, useState } from "react";
import Editor from "@monaco-editor/react";

const EDITABLE_EXT = [".py", ".md", ".txt", ".json", ".sh", ".yml", ".yaml", ".toml", ".env", ".js", ".jsx", ".ts", ".tsx"];

function isEditable(path) {
  const lower = path.toLowerCase();
  return EDITABLE_EXT.some((ext) => lower.endsWith(ext)) || !lower.includes(".");
}

export function EditorPanel({ files, selectedFile, content, onOpenFile, onChangeContent, onSave }) {
  const [filter, setFilter] = useState("");
  const list = useMemo(() => {
    return files
      .filter((f) => !f.is_dir)
      .filter((f) => isEditable(f.path))
      .filter((f) => f.path.toLowerCase().includes(filter.toLowerCase()));
  }, [files, filter]);

  useEffect(() => {
    if (!selectedFile && list.length > 0) {
      onOpenFile(list[0].path);
    }
  }, [selectedFile, list, onOpenFile]);

  return (
    <section className="panel editor-panel">
      <div className="panel-header">
        <h2>Code Editor</h2>
        <button onClick={onSave} disabled={!selectedFile}>Save</button>
      </div>
      <div className="editor-layout">
        <div className="file-list">
          <input
            placeholder="Search files"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          {list.map((f) => (
            <button
              key={f.path}
              className={selectedFile === f.path ? "active" : ""}
              onClick={() => onOpenFile(f.path)}
            >
              {f.path}
            </button>
          ))}
        </div>
        <div className="editor-wrap">
          {selectedFile ? (
            <Editor
              height="100%"
              language={selectedFile.endsWith(".py") ? "python" : "markdown"}
              value={content}
              onChange={(v) => onChangeContent(v || "")}
              options={{
                minimap: { enabled: false },
                fontSize: 14,
                automaticLayout: true,
              }}
            />
          ) : (
            <div className="empty">No editable file found yet.</div>
          )}
        </div>
      </div>
    </section>
  );
}
