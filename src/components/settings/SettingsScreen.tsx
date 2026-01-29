import { useState, useEffect, useCallback } from "react";
import { sidecarApi } from "../../services/sidecarApi";
import { useToast } from "../shared/Toast";
import type {
  AppSettings,
  LLMProvider,
  LiteracyLevel,
} from "../../types/sidecar";
import "./SettingsScreen.css";

const SPECIALTY_OPTIONS = [
  "Cardiology",
  "Pulmonology",
  "Neurology",
  "Gastroenterology",
  "Endocrinology",
  "Nephrology",
  "Hematology",
  "Oncology",
  "Radiology",
  "General/Primary Care",
];

const LITERACY_OPTIONS: {
  value: LiteracyLevel;
  label: string;
  description: string;
}[] = [
  {
    value: "grade_4",
    label: "Grade 4",
    description: "Very simple words, short sentences",
  },
  {
    value: "grade_6",
    label: "Grade 6 (Default)",
    description: "Simple, clear language",
  },
  {
    value: "grade_8",
    label: "Grade 8",
    description: "Clear with some technical terms",
  },
  {
    value: "clinical",
    label: "Clinical",
    description: "Standard medical terminology",
  },
];

export function SettingsScreen() {
  const { showToast } = useToast();
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const [provider, setProvider] = useState<LLMProvider>("claude");
  const [claudeKey, setClaudeKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");
  const [literacyLevel, setLiteracyLevel] =
    useState<LiteracyLevel>("grade_6");
  const [specialty, setSpecialty] = useState("");
  const [practiceName, setPracticeName] = useState("");
  const [claudeModel, setClaudeModel] = useState("");
  const [openaiModel, setOpenaiModel] = useState("");

  useEffect(() => {
    async function loadSettings() {
      try {
        const s = await sidecarApi.getSettings();
        setSettings(s);
        setProvider(s.llm_provider);
        setLiteracyLevel(s.literacy_level);
        setSpecialty(s.specialty ?? "");
        setPracticeName(s.practice_name ?? "");
        setClaudeModel(s.claude_model ?? "");
        setOpenaiModel(s.openai_model ?? "");
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Failed to load settings";
        setError(msg);
        showToast("error", msg);
      } finally {
        setLoading(false);
      }
    }
    loadSettings();
  }, [showToast]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setError(null);
    setSuccess(false);

    try {
      const update: Record<string, unknown> = {
        llm_provider: provider,
        literacy_level: literacyLevel,
        specialty: specialty || null,
        practice_name: practiceName.trim() || null,
        claude_model: claudeModel.trim() || null,
        openai_model: openaiModel.trim() || null,
      };
      if (claudeKey.trim()) {
        update.claude_api_key = claudeKey.trim();
      }
      if (openaiKey.trim()) {
        update.openai_api_key = openaiKey.trim();
      }

      const updated = await sidecarApi.updateSettings(update);
      setSettings(updated);
      setSuccess(true);
      setClaudeKey("");
      setOpenaiKey("");
      showToast("success", "Settings saved.");
      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to save settings";
      setError(msg);
      showToast("error", msg);
    } finally {
      setSaving(false);
    }
  }, [provider, claudeKey, openaiKey, literacyLevel, specialty, practiceName, claudeModel, openaiModel, showToast]);

  if (loading) {
    return (
      <div className="settings-screen">
        <p>Loading settings...</p>
      </div>
    );
  }

  return (
    <div className="settings-screen">
      <header className="settings-header">
        <h2 className="settings-title">Settings</h2>
        <p className="settings-description">
          Configure your LLM provider, API keys, and explanation
          preferences.
        </p>
      </header>

      {/* Practice Information */}
      <section className="settings-section">
        <h3 className="settings-section-title">Practice Information</h3>
        <div className="form-group">
          <label className="form-label">Specialty</label>
          <select
            className="form-input"
            value={specialty}
            onChange={(e) => setSpecialty(e.target.value)}
          >
            <option value="">Select a specialty...</option>
            {SPECIALTY_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label className="form-label">Practice Name</label>
          <input
            type="text"
            className="form-input"
            placeholder="e.g. Main Street Cardiology"
            value={practiceName}
            onChange={(e) => setPracticeName(e.target.value)}
          />
        </div>
      </section>

      {/* Provider Selection */}
      <section className="settings-section">
        <h3 className="settings-section-title">LLM Provider</h3>
        <div className="provider-toggle">
          <button
            className={`provider-btn ${provider === "claude" ? "provider-btn--active" : ""}`}
            onClick={() => setProvider("claude")}
          >
            Claude (Anthropic)
          </button>
          <button
            className={`provider-btn ${provider === "openai" ? "provider-btn--active" : ""}`}
            onClick={() => setProvider("openai")}
          >
            OpenAI
          </button>
        </div>
      </section>

      {/* API Keys */}
      <section className="settings-section">
        <h3 className="settings-section-title">API Keys</h3>
        <div className="form-group">
          <label className="form-label">
            Claude API Key
            {settings?.claude_api_key && (
              <span className="key-status key-status--set">
                Configured
              </span>
            )}
          </label>
          <input
            type="password"
            className="form-input"
            placeholder={
              settings?.claude_api_key
                ? "Enter new key to replace"
                : "sk-ant-..."
            }
            value={claudeKey}
            onChange={(e) => setClaudeKey(e.target.value)}
          />
        </div>
        <div className="form-group">
          <label className="form-label">
            OpenAI API Key
            {settings?.openai_api_key && (
              <span className="key-status key-status--set">
                Configured
              </span>
            )}
          </label>
          <input
            type="password"
            className="form-input"
            placeholder={
              settings?.openai_api_key
                ? "Enter new key to replace"
                : "sk-..."
            }
            value={openaiKey}
            onChange={(e) => setOpenaiKey(e.target.value)}
          />
        </div>
      </section>

      {/* Model Override */}
      <section className="settings-section">
        <h3 className="settings-section-title">Model Override</h3>
        <p className="settings-description" style={{ marginBottom: "var(--space-md)" }}>
          Leave blank to use the default model for each provider.
        </p>
        <div className="form-group">
          <label className="form-label">Claude Model</label>
          <input
            type="text"
            className="form-input"
            placeholder="e.g. claude-sonnet-4-20250514"
            value={claudeModel}
            onChange={(e) => setClaudeModel(e.target.value)}
          />
        </div>
        <div className="form-group">
          <label className="form-label">OpenAI Model</label>
          <input
            type="text"
            className="form-input"
            placeholder="e.g. gpt-4o"
            value={openaiModel}
            onChange={(e) => setOpenaiModel(e.target.value)}
          />
        </div>
      </section>

      {/* Literacy Level */}
      <section className="settings-section">
        <h3 className="settings-section-title">Explanation Level</h3>
        <div className="literacy-options">
          {LITERACY_OPTIONS.map((opt) => (
            <label
              key={opt.value}
              className={`literacy-option ${literacyLevel === opt.value ? "literacy-option--selected" : ""}`}
            >
              <input
                type="radio"
                name="literacy"
                value={opt.value}
                checked={literacyLevel === opt.value}
                onChange={() => setLiteracyLevel(opt.value)}
                className="literacy-radio"
              />
              <div className="literacy-content">
                <span className="literacy-label">{opt.label}</span>
                <span className="literacy-desc">
                  {opt.description}
                </span>
              </div>
            </label>
          ))}
        </div>
      </section>

      {/* Save */}
      <div className="settings-actions">
        <button
          className="save-btn"
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? "Saving..." : "Save Settings"}
        </button>
        {success && (
          <span className="save-success">Settings saved.</span>
        )}
        {error && <span className="save-error">{error}</span>}
      </div>
    </div>
  );
}
