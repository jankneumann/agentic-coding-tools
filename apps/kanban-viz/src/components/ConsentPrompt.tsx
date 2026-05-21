/**
 * ConsentPrompt — modal-style confirmation for destructive-write actions.
 * Design D8: every destructive-write surfaces a consent prompt before execution.
 */

interface Props {
  message: string;
  onConfirm: () => void;
  onDecline: () => void;
}

export function ConsentPrompt({ message, onConfirm, onDecline }: Props) {
  return (
    <div
      data-testid="consent-prompt"
      role="dialog"
      aria-modal="true"
      aria-label="Confirm action"
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(0,0,0,0.4)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div
        style={{
          background: "#fff",
          borderRadius: 6,
          padding: 24,
          maxWidth: 400,
          boxShadow: "0 4px 20px rgba(0,0,0,0.2)",
        }}
      >
        <p data-testid="consent-message" style={{ marginBottom: 16 }}>
          {message}
        </p>
        <div style={{ display: "flex", gap: 12, justifyContent: "flex-end" }}>
          <button
            data-testid="consent-decline"
            onClick={onDecline}
            style={{ padding: "6px 16px" }}
          >
            Cancel
          </button>
          <button
            data-testid="consent-confirm"
            onClick={onConfirm}
            style={{
              padding: "6px 16px",
              background: "#de350b",
              color: "#fff",
              border: "none",
              borderRadius: 4,
            }}
          >
            Confirm
          </button>
        </div>
      </div>
    </div>
  );
}
