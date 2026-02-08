import { useState, useEffect, useCallback } from "react";
import { sidecarApi } from "../../services/sidecarApi";
import { IS_TAURI } from "../../services/platform";
import { useToast } from "../shared/Toast";
import type { AppSettings, LLMProvider } from "../../types/sidecar";
import "../settings/SettingsScreen.css";
import "./AIModelScreen.css";

export function AIModelScreen() {
  const { showToast } = useToast();
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const [provider, setProvider] = useState<LLMProvider>("claude");
  const [claudeKey, setClaudeKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");
  const [awsAccessKey, setAwsAccessKey] = useState("");
  const [awsSecretKey, setAwsSecretKey] = useState("");
  const [awsRegion, setAwsRegion] = useState("us-east-1");
  const [claudeModel, setClaudeModel] = useState("");
  const [openaiModel, setOpenaiModel] = useState("");

  useEffect(() => {
    async function loadSettings() {
      try {
        const s = await sidecarApi.getSettings();
        setSettings(s);
        setProvider(s.llm_provider);
        setClaudeModel(s.claude_model ?? "");
        setOpenaiModel(s.openai_model ?? "");
        setAwsRegion(s.aws_region ?? "us-east-1");
      } catch (err) {
        const msg =
          err instanceof Error ? err.message : "Failed to load settings";
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
        claude_model: claudeModel.trim() || null,
        openai_model: openaiModel.trim() || null,
        aws_region: awsRegion,
      };
      if (claudeKey.trim()) {
        update.claude_api_key = claudeKey.trim();
      }
      if (openaiKey.trim()) {
        update.openai_api_key = openaiKey.trim();
      }
      if (awsAccessKey.trim()) {
        update.aws_access_key_id = awsAccessKey.trim();
      }
      if (awsSecretKey.trim()) {
        update.aws_secret_access_key = awsSecretKey.trim();
      }

      const updated = await sidecarApi.updateSettings(update);
      setSettings(updated);
      setSuccess(true);
      setClaudeKey("");
      setOpenaiKey("");
      setAwsAccessKey("");
      setAwsSecretKey("");
      showToast("success", "AI model settings saved.");
      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Failed to save settings";
      setError(msg);
      showToast("error", msg);
    } finally {
      setSaving(false);
    }
  }, [provider, claudeKey, openaiKey, awsAccessKey, awsSecretKey, awsRegion, claudeModel, openaiModel, showToast]);

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
        <h2 className="settings-title">AI Model</h2>
        <p className="settings-description">
          {IS_TAURI
            ? "Configure your LLM provider, API keys, and model overrides."
            : "AI model configuration is managed by the server."}
        </p>
      </header>

      {!IS_TAURI ? (
        /* Web mode: read-only cloud provider info */
        <section className="settings-section">
          <h3 className="settings-section-title">LLM Provider</h3>
          <p className="settings-description">
            AWS Bedrock (cloud-managed)
          </p>
        </section>
      ) : (
        <>
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
                className={`provider-btn ${provider === "bedrock" ? "provider-btn--active" : ""}`}
                onClick={() => setProvider("bedrock")}
              >
                AWS Bedrock
              </button>
              <button
                className={`provider-btn ${provider === "openai" ? "provider-btn--active" : ""}`}
                onClick={() => setProvider("openai")}
              >
                OpenAI
              </button>
            </div>
            {provider === "bedrock" && (
              <p className="settings-description" style={{ marginTop: "var(--space-sm)" }}>
                Uses Claude models via AWS Bedrock. Covered under your AWS BAA for HIPAA compliance.
              </p>
            )}
          </section>

          {/* API Keys */}
          <section className="settings-section">
            <h3 className="settings-section-title">
              {provider === "bedrock" ? "AWS Credentials" : "API Keys"}
            </h3>

            {provider === "bedrock" ? (
              <>
                <div className="form-group">
                  <label className="form-label">
                    AWS Access Key ID
                    {settings?.aws_access_key_id && (
                      <span className="key-status key-status--set">Configured</span>
                    )}
                  </label>
                  <input
                    type="password"
                    className="form-input"
                    placeholder={
                      settings?.aws_access_key_id
                        ? "Enter new key to replace"
                        : "AKIA..."
                    }
                    value={awsAccessKey}
                    onChange={(e) => setAwsAccessKey(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">
                    AWS Secret Access Key
                    {settings?.aws_secret_access_key && (
                      <span className="key-status key-status--set">Configured</span>
                    )}
                  </label>
                  <input
                    type="password"
                    className="form-input"
                    placeholder={
                      settings?.aws_secret_access_key
                        ? "Enter new key to replace"
                        : "Secret access key"
                    }
                    value={awsSecretKey}
                    onChange={(e) => setAwsSecretKey(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">AWS Region</label>
                  <select
                    className="form-input"
                    value={awsRegion}
                    onChange={(e) => setAwsRegion(e.target.value)}
                  >
                    <option value="us-east-1">US East (N. Virginia)</option>
                    <option value="us-west-2">US West (Oregon)</option>
                    <option value="eu-west-1">EU West (Ireland)</option>
                    <option value="eu-central-1">EU Central (Frankfurt)</option>
                    <option value="ap-southeast-1">Asia Pacific (Singapore)</option>
                    <option value="ap-northeast-1">Asia Pacific (Tokyo)</option>
                  </select>
                </div>
              </>
            ) : (
              <>
                <div className="form-group">
                  <label className="form-label">
                    Claude API Key
                    {settings?.claude_api_key && (
                      <span className="key-status key-status--set">Configured</span>
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
                      <span className="key-status key-status--set">Configured</span>
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
              </>
            )}
          </section>

          {/* Model Override */}
          <section className="settings-section">
            <h3 className="settings-section-title">Model Override</h3>
            <p
              className="settings-description"
              style={{ marginBottom: "var(--space-md)" }}
            >
              Leave blank to use the default model for each provider.
            </p>
            {provider !== "openai" && (
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
            )}
            {provider === "openai" && (
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
            )}
          </section>

          {/* Save */}
          <div className="settings-actions">
            <button className="save-btn" onClick={handleSave} disabled={saving}>
              {saving ? "Saving..." : "Save Settings"}
            </button>
            {success && <span className="save-success">Settings saved.</span>}
            {error && <span className="save-error">{error}</span>}
          </div>
        </>
      )}
    </div>
  );
}
