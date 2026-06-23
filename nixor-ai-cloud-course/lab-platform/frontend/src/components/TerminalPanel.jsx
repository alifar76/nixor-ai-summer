import { useEffect, useRef } from "react";
import { Terminal } from "xterm";
import { FitAddon } from "xterm-addon-fit";

export function TerminalPanel({ token }) {
  const hostRef = useRef(null);
  const socketRef = useRef(null);

  useEffect(() => {
    if (!hostRef.current || !token) return undefined;

    const term = new Terminal({
      cursorBlink: true,
      fontSize: 13,
      convertEol: true,
      theme: {
        background: "#0f172a",
        foreground: "#f8fafc",
      },
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(hostRef.current);
    fit.fit();

    const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
    const url = `${wsProtocol}://${window.location.host}/api/terminal?token=${encodeURIComponent(token)}&cols=${term.cols}&rows=${term.rows}`;
    const socket = new WebSocket(url);
    socket.binaryType = "arraybuffer";
    socketRef.current = socket;

    socket.onmessage = (event) => {
      if (typeof event.data === "string") {
        term.write(event.data);
        return;
      }
      const text = new TextDecoder().decode(new Uint8Array(event.data));
      term.write(text);
    };

    socket.onopen = () => {
      term.focus();
      term.writeln("\r\nConnected to your Linux workspace.\r\n");
    };

    socket.onclose = () => {
      term.writeln("\r\nSession closed.\r\n");
    };

    const dataDispose = term.onData((data) => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "input", data }));
      }
    });

    const resize = () => {
      fit.fit();
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
      }
    };
    const observer = new ResizeObserver(resize);
    observer.observe(hostRef.current);

    return () => {
      observer.disconnect();
      dataDispose.dispose();
      socket.close();
      term.dispose();
    };
  }, [token]);

  return (
    <section className="panel terminal-panel">
      <div className="panel-header">
        <h2>Linux Terminal</h2>
      </div>
      <div className="terminal-host" ref={hostRef} />
    </section>
  );
}
