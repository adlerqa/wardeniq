/** A status line: plain text, or an ok / err span, or a spinner before the text. */
export default function StatusText({ status }) {
  if (!status) return null;
  if (status.kind === "err") return <span className="err">{status.text}</span>;
  if (status.kind === "ok") return <span className="ok">{status.text}</span>;
  if (status.kind === "muted") return <span className="muted">{status.text}</span>;
  if (status.kind === "spin")
    return (
      <>
        <span className="spin-inline"></span>
        {status.text}
      </>
    );
  return status.text;
}
