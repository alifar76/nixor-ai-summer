import ReactMarkdown from "react-markdown";

export function CoursePanel({ sessions, selectedSessionId, onSelectSession, completedSet, onToggleStep }) {
  const selected = sessions.find((s) => s.id === selectedSessionId) || sessions[0];

  return (
    <section className="panel course-panel">
      <div className="panel-header">
        <h2>4-Day Course</h2>
      </div>
      <div className="session-tabs">
        {sessions.map((session) => (
          <button
            key={session.id}
            className={session.id === selected?.id ? "active" : ""}
            onClick={() => onSelectSession(session.id)}
          >
            Day {session.order}
          </button>
        ))}
      </div>
      {selected && (
        <>
          <h3>{selected.title}</h3>
          <div className="markdown">
            <ReactMarkdown>{selected.markdown}</ReactMarkdown>
          </div>
          <div className="steps">
            {selected.steps.map((step) => (
              <label key={step.id}>
                <input
                  type="checkbox"
                  checked={completedSet.has(step.id)}
                  onChange={(e) => onToggleStep(step.id, e.target.checked)}
                />
                <span>{step.text}</span>
              </label>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
