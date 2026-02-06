import { useState, useEffect, useCallback } from "react";
import { sidecarApi } from "../../services/sidecarApi";
import { deploySharedKey } from "../../services/sharedConfig";
import {
  fetchUsageSummary,
  fetchAllUsers,
  type UserUsageSummary,
  type RegisteredUser,
} from "../../services/adminUsageQueries";
import { useToast } from "../shared/Toast";
import type { AppSettings, LLMProvider } from "../../types/sidecar";
import "../settings/SettingsScreen.css";
import "./AdminScreen.css";

type TimeRange = "7d" | "30d" | "all";

function sinceDate(range: TimeRange): Date {
  if (range === "all") return new Date("2000-01-01");
  const d = new Date();
  d.setDate(d.getDate() - (range === "7d" ? 7 : 30));
  return d;
}

export function AdminScreen() {
  const { showToast } = useToast();
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deploying, setDeploying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const [provider, setProvider] = useState<LLMProvider>("claude");
  const [claudeKey, setClaudeKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");
  const [claudeModel, setClaudeModel] = useState("");
  const [openaiModel, setOpenaiModel] = useState("");

  // Dashboard state
  const [timeRange, setTimeRange] = useState<TimeRange>("7d");
  const [refreshKey, setRefreshKey] = useState(0);
  const [usageSummary, setUsageSummary] = useState<UserUsageSummary[]>([]);
  const [allUsers, setAllUsers] = useState<RegisteredUser[]>([]);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [dashboardError, setDashboardError] = useState<string | null>(null);

  useEffect(() => {
    async function loadSettings() {
      try {
        const s = await sidecarApi.getSettings();
        setSettings(s);
        setProvider(s.llm_provider);
        setClaudeModel(s.claude_model ?? "");
        setOpenaiModel(s.openai_model ?? "");
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

  // Load dashboard data
  useEffect(() => {
    let cancelled = false;
    async function loadDashboard() {
      setDashboardLoading(true);
      setDashboardError(null);
      try {
        const [users, usage] = await Promise.all([
          fetchAllUsers(),
          fetchUsageSummary(sinceDate(timeRange)),
        ]);
        if (cancelled) return;
        setAllUsers(users);
        setUsageSummary(usage);
      } catch (err) {
        if (cancelled) return;
        const msg = err instanceof Error ? err.message : "Failed to load dashboard data";
        setDashboardError(msg);
      } finally {
        if (!cancelled) setDashboardLoading(false);
      }
    }
    loadDashboard();
    return () => { cancelled = true; };
  }, [timeRange, refreshKey]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setError(null);
    setSuccess(false);

    try {
      const update: Record<string, unknown> = {
        llm_provider: provider,
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
  }, [provider, claudeKey, openaiKey, claudeModel, openaiModel, showToast]);

  const handleDeployKey = useCallback(async () => {
    setDeploying(true);
    try {
      const { key } = await sidecarApi.getRawApiKey("claude");
      await deploySharedKey("claude_api_key", key);
      showToast("success", "Claude API key deployed to all users.");
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Failed to deploy key";
      showToast("error", msg);
    } finally {
      setDeploying(false);
    }
  }, [showToast]);

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
        <h2 className="settings-title">Admin</h2>
        <p className="settings-description">
          Manage LLM provider settings and deploy shared API keys.
        </p>
      </header>

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

      {/* Save */}
      <div className="settings-actions">
        <button className="save-btn" onClick={handleSave} disabled={saving}>
          {saving ? "Saving..." : "Save Settings"}
        </button>
        {success && <span className="save-success">Settings saved.</span>}
        {error && <span className="save-error">{error}</span>}
      </div>

      {/* Deploy API Key */}
      <section className="settings-section admin-deploy-section">
        <h3 className="settings-section-title">Deploy API Key</h3>
        <p className="settings-description">
          Push your locally configured Claude API key to all users via Supabase.
          Users will receive the key automatically on their next sync.
        </p>
        <button
          className="deploy-btn"
          onClick={handleDeployKey}
          disabled={deploying}
        >
          {deploying
            ? "Deploying..."
            : "Deploy Claude Key to All Users"}
        </button>
      </section>

      {/* Usage Dashboard */}
      <section className="settings-section admin-dashboard-section">
        <h3 className="settings-section-title">Usage Dashboard</h3>

        <div className="dashboard-controls">
          <label className="form-label" htmlFor="time-range">
            Time Range
          </label>
          <select
            id="time-range"
            className="form-input"
            value={timeRange}
            onChange={(e) => setTimeRange(e.target.value as TimeRange)}
          >
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
            <option value="all">All time</option>
          </select>
          <button
            className="dashboard-refresh-btn"
            onClick={() => setRefreshKey((k) => k + 1)}
            disabled={dashboardLoading}
          >
            {dashboardLoading ? "Refreshing..." : "Refresh"}
          </button>
        </div>

        {dashboardLoading ? (
          <p className="settings-description">Loading dashboard...</p>
        ) : dashboardError ? (
          <p className="save-error">{dashboardError}</p>
        ) : (
          <>
            {/* Summary stat cards */}
            <div className="stats-grid">
              <div className="stat-card">
                <span className="stat-label">Total Users</span>
                <span className="stat-value">
                  {allUsers.length.toLocaleString()}
                </span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Total Queries</span>
                <span className="stat-value">
                  {usageSummary
                    .reduce((s, u) => s + u.total_queries, 0)
                    .toLocaleString()}
                </span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Total Tokens</span>
                <span className="stat-value">
                  {usageSummary
                    .reduce(
                      (s, u) => s + u.total_input_tokens + u.total_output_tokens,
                      0,
                    )
                    .toLocaleString()}
                </span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Deep Analysis</span>
                <span className="stat-value">
                  {usageSummary
                    .reduce((s, u) => s + u.deep_analysis_count, 0)
                    .toLocaleString()}
                </span>
              </div>
            </div>

            {/* Per-user table */}
            <div className="usage-table-wrapper">
              <table className="usage-table">
                <thead>
                  <tr>
                    <th>Email</th>
                    <th>Signed Up</th>
                    <th>Queries</th>
                    <th>Sonnet Tokens</th>
                    <th>Opus Tokens</th>
                    <th>Deep Analysis</th>
                    <th>Last Active</th>
                  </tr>
                </thead>
                <tbody>
                  {allUsers.map((user) => {
                    const usage = usageSummary.find(
                      (u) => u.user_id === user.user_id,
                    );
                    return (
                      <tr key={user.user_id}>
                        <td>{user.email}</td>
                        <td>
                          {new Date(user.created_at).toLocaleDateString()}
                        </td>
                        {usage ? (
                          <>
                            <td>{usage.total_queries.toLocaleString()}</td>
                            <td>
                              {(
                                usage.sonnet_input_tokens +
                                usage.sonnet_output_tokens
                              ).toLocaleString()}
                            </td>
                            <td>
                              {(
                                usage.opus_input_tokens +
                                usage.opus_output_tokens
                              ).toLocaleString()}
                            </td>
                            <td>
                              {usage.deep_analysis_count.toLocaleString()}
                            </td>
                            <td>
                              {new Date(usage.last_active).toLocaleDateString()}
                            </td>
                          </>
                        ) : (
                          <>
                            <td colSpan={5} className="no-usage">
                              No usage data
                            </td>
                          </>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
