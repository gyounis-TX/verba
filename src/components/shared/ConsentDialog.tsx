import "./ConsentDialog.css";

interface ConsentDialogProps {
  onConsent: () => void;
}

export function ConsentDialog({ onConsent }: ConsentDialogProps) {
  return (
    <div className="consent-overlay">
      <div className="consent-card">
        <h2 className="consent-title">Privacy & Data Notice</h2>
        <ul className="consent-list">
          <li>All report processing happens locally on your device.</li>
          <li>Your medical data never leaves your computer without your action.</li>
          <li>API keys are stored securely in your operating system's keychain.</li>
          <li>Analysis history is saved locally and can be permanently deleted at any time.</li>
          <li>When you request an AI explanation, only anonymized text (with personal health information scrubbed) is sent to the AI provider.</li>
        </ul>
        <button className="consent-btn" onClick={onConsent}>
          I Understand
        </button>
      </div>
    </div>
  );
}
