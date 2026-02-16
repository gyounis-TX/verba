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

// Anthropic pricing per million tokens (as of Jan 2025)
const SONNET_INPUT_COST = 3; // $/M tokens
const SONNET_OUTPUT_COST = 15; // $/M tokens
const OPUS_INPUT_COST = 15; // $/M tokens
const OPUS_OUTPUT_COST = 75; // $/M tokens

function calculateCostPerQuery(
  queries: number,
  inputTokens: number,
  outputTokens: number,
  inputCost: number,
  outputCost: number,
): number | null {
  if (queries === 0) return null;
  const totalCost =
    (inputTokens / 1_000_000) * inputCost +
    (outputTokens / 1_000_000) * outputCost;
  return totalCost / queries;
}

function calculateTotalCost(usage: UserUsageSummary): number {
  return (
    (usage.sonnet_input_tokens / 1_000_000) * SONNET_INPUT_COST +
    (usage.sonnet_output_tokens / 1_000_000) * SONNET_OUTPUT_COST +
    (usage.opus_input_tokens / 1_000_000) * OPUS_INPUT_COST +
    (usage.opus_output_tokens / 1_000_000) * OPUS_OUTPUT_COST
  );
}

function formatCost(cost: number | null): string {
  if (cost === null) return "—";
  if (cost < 0.01) return "<$0.01";
  return `$${cost.toFixed(2)}`;
}

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
  const [awsAccessKey, setAwsAccessKey] = useState("");
  const [awsSecretKey, setAwsSecretKey] = useState("");
  const [awsRegion, setAwsRegion] = useState("us-east-1");
  const [claudeModel, setClaudeModel] = useState("");
  const [openaiModel, setOpenaiModel] = useState("");

  // Dashboard state
  const [timeRange, setTimeRange] = useState<TimeRange>("7d");
  const [refreshKey, setRefreshKey] = useState(0);
  const [usageSummary, setUsageSummary] = useState<UserUsageSummary[]>([]);
  const [usage30d, setUsage30d] = useState<UserUsageSummary[]>([]);
  const [allUsers, setAllUsers] = useState<RegisteredUser[]>([]);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [dashboardError, setDashboardError] = useState<string | null>(null);

  // Billing admin state
  const [billingConfig, setBillingConfig] = useState<Record<string, string>>({});
  const [billingOverrides, setBillingOverrides] = useState<Record<string, unknown>[]>([]);
  const [billingLoading, setBillingLoading] = useState(false);
  const [overrideUserId, setOverrideUserId] = useState("");
  const [overrideExempt, setOverrideExempt] = useState(false);
  const [overrideTier, setOverrideTier] = useState("");
  const [overrideTrialDays, setOverrideTrialDays] = useState("");
  const [overrideNotes, setOverrideNotes] = useState("");

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

  // Load dashboard data
  useEffect(() => {
    let cancelled = false;
    async function loadDashboard() {
      setDashboardLoading(true);
      setDashboardError(null);
      try {
        const [users, usage, cost30d] = await Promise.all([
          fetchAllUsers(),
          fetchUsageSummary(sinceDate(timeRange)),
          fetchUsageSummary(sinceDate("30d")),
        ]);
        if (cancelled) return;
        setAllUsers(users);
        setUsageSummary(usage);
        setUsage30d(cost30d);
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

  // Load billing config
  useEffect(() => {
    let cancelled = false;
    async function loadBilling() {
      setBillingLoading(true);
      try {
        const [config, overrides] = await Promise.all([
          sidecarApi.getBillingConfig(),
          sidecarApi.getBillingOverrides(),
        ]);
        if (cancelled) return;
        setBillingConfig(config);
        setBillingOverrides(overrides);
      } catch {
        // Billing not available — silently ignore
      } finally {
        if (!cancelled) setBillingLoading(false);
      }
    }
    loadBilling();
    return () => { cancelled = true; };
  }, []);

  const handleUpdateBillingConfig = useCallback(
    async (key: string, value: string) => {
      try {
        await sidecarApi.updateBillingConfig(key, value);
        setBillingConfig((prev) => ({ ...prev, [key]: value }));
        showToast("success", `Updated ${key}.`);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Failed to update config";
        showToast("error", msg);
      }
    },
    [showToast],
  );

  const handleSetOverride = useCallback(async () => {
    if (!overrideUserId.trim()) {
      showToast("error", "Enter a user ID.");
      return;
    }
    try {
      await sidecarApi.setBillingOverride(overrideUserId.trim(), {
        payments_exempt: overrideExempt,
        custom_tier: overrideTier.trim() || null,
        custom_trial_days: overrideTrialDays ? parseInt(overrideTrialDays, 10) : null,
        notes: overrideNotes.trim() || null,
      });
      showToast("success", "Override saved.");
      setOverrideUserId("");
      setOverrideExempt(false);
      setOverrideTier("");
      setOverrideTrialDays("");
      setOverrideNotes("");
      // Refresh overrides
      const overrides = await sidecarApi.getBillingOverrides();
      setBillingOverrides(overrides);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to set override";
      showToast("error", msg);
    }
  }, [overrideUserId, overrideExempt, overrideTier, overrideTrialDays, overrideNotes, showToast]);

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

  const handleDeployKey = useCallback(async () => {
    setDeploying(true);
    try {
      if (provider === "bedrock") {
        const result = await sidecarApi.getRawApiKey("bedrock");
        if (!result.credentials) throw new Error("No AWS credentials configured.");
        await deploySharedKey("aws_access_key_id", result.credentials.access_key);
        await deploySharedKey("aws_secret_access_key", result.credentials.secret_key);
        await deploySharedKey("aws_region", result.credentials.region);
        await deploySharedKey("llm_provider", "bedrock");
        showToast("success", "AWS Bedrock credentials deployed to all users.");
      } else {
        const { key } = await sidecarApi.getRawApiKey("claude");
        if (!key) throw new Error("No Claude API key configured.");
        await deploySharedKey("claude_api_key", key);
        await deploySharedKey("llm_provider", "claude");
        showToast("success", "Claude API key deployed to all users.");
      }
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Failed to deploy key";
      showToast("error", msg);
    } finally {
      setDeploying(false);
    }
  }, [provider, showToast]);

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
        {settings?.llm_provider && (
          <p className="admin-active-provider">
            Currently active: <strong>{settings.llm_provider === "claude" ? "Claude (Anthropic)" : settings.llm_provider === "bedrock" ? "AWS Bedrock" : "OpenAI"}</strong>
          </p>
        )}
        {provider === "bedrock" && (
          <p className="settings-description" style={{ marginTop: "var(--space-sm)" }}>
            Uses Claude models via AWS Bedrock. Covered under your AWS BAA for HIPAA compliance.
          </p>
        )}
      </section>

      {/* API Keys / AWS Credentials */}
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

      {/* Deploy API Key */}
      <section className="settings-section admin-deploy-section">
        <h3 className="settings-section-title">Deploy API Key</h3>
        <p className="settings-description">
          {provider === "bedrock"
            ? "Push your AWS Bedrock credentials to all users via Supabase. Users will receive the credentials and provider setting automatically on their next sync."
            : "Push your locally configured Claude API key to all users via Supabase. Users will receive the key automatically on their next sync."}
        </p>
        <button
          className="deploy-btn"
          onClick={handleDeployKey}
          disabled={deploying}
        >
          {deploying
            ? "Deploying..."
            : provider === "bedrock"
              ? "Deploy AWS Credentials to All Users"
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
                    <th>Queries</th>
                    <th>Sonnet Tokens</th>
                    <th>Opus Tokens</th>
                    <th>30d Cost</th>
                    <th>Last Active</th>
                    <th>Signed Up</th>
                  </tr>
                </thead>
                <tbody>
                  {allUsers.map((user) => {
                    const usage = usageSummary.find(
                      (u) => u.user_id === user.user_id,
                    );
                    const cost30 = usage30d.find(
                      (u) => u.user_id === user.user_id,
                    );
                    return (
                      <tr key={user.user_id}>
                        <td>{user.email}</td>
                        {usage ? (
                          <>
                            <td>{usage.total_queries.toLocaleString()}</td>
                            <td>
                              {(
                                usage.sonnet_input_tokens +
                                usage.sonnet_output_tokens
                              ).toLocaleString()}
                              {" "}
                              <span className="cost-inline">
                                {formatCost(
                                  calculateCostPerQuery(
                                    usage.sonnet_queries,
                                    usage.sonnet_input_tokens,
                                    usage.sonnet_output_tokens,
                                    SONNET_INPUT_COST,
                                    SONNET_OUTPUT_COST,
                                  ),
                                )}/q
                              </span>
                            </td>
                            <td>
                              {(
                                usage.opus_input_tokens +
                                usage.opus_output_tokens
                              ).toLocaleString()}
                              {" "}
                              <span className="cost-inline">
                                {formatCost(
                                  calculateCostPerQuery(
                                    usage.opus_queries,
                                    usage.opus_input_tokens,
                                    usage.opus_output_tokens,
                                    OPUS_INPUT_COST,
                                    OPUS_OUTPUT_COST,
                                  ),
                                )}/q
                              </span>
                            </td>
                            <td>
                              {cost30
                                ? formatCost(calculateTotalCost(cost30))
                                : "—"}
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
                        <td>
                          {new Date(user.created_at).toLocaleDateString()}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      {/* Billing Configuration */}
      <section className="settings-section admin-dashboard-section">
        <h3 className="settings-section-title">Billing</h3>

        {billingLoading ? (
          <p className="settings-description">Loading billing config...</p>
        ) : (
          <>
            {/* Payments Enabled Toggle */}
            <div className="form-group">
              <label className="form-label">Payments Enabled</label>
              <div className="provider-toggle">
                <button
                  className={`provider-btn ${billingConfig.payments_enabled === "true" ? "provider-btn--active" : ""}`}
                  onClick={() => handleUpdateBillingConfig("payments_enabled", "true")}
                >
                  On
                </button>
                <button
                  className={`provider-btn ${billingConfig.payments_enabled !== "true" ? "provider-btn--active" : ""}`}
                  onClick={() => handleUpdateBillingConfig("payments_enabled", "false")}
                >
                  Off
                </button>
              </div>
              <p className="settings-description" style={{ marginTop: "var(--space-xs)" }}>
                When off, all features are available without billing enforcement.
              </p>
            </div>

            {/* Trial Settings */}
            <div className="form-group" style={{ marginTop: "var(--space-lg)" }}>
              <label className="form-label">Trial Period (days)</label>
              <input
                type="number"
                className="form-input"
                style={{ maxWidth: 120 }}
                value={billingConfig.trial_period_days ?? "14"}
                onChange={(e) =>
                  handleUpdateBillingConfig("trial_period_days", e.target.value)
                }
              />
            </div>

            <div className="form-group">
              <label className="form-label">Grace Period (hours)</label>
              <input
                type="number"
                className="form-input"
                style={{ maxWidth: 120 }}
                value={billingConfig.grace_period_hours ?? "72"}
                onChange={(e) =>
                  handleUpdateBillingConfig("grace_period_hours", e.target.value)
                }
              />
            </div>

            <div className="form-group">
              <label className="form-label">Trial Tier</label>
              <select
                className="form-input"
                style={{ maxWidth: 200 }}
                value={billingConfig.trial_tier ?? "professional"}
                onChange={(e) =>
                  handleUpdateBillingConfig("trial_tier", e.target.value)
                }
              >
                <option value="starter">Starter</option>
                <option value="professional">Professional</option>
                <option value="unlimited">Unlimited</option>
              </select>
            </div>

            {/* User Overrides */}
            <h4 className="settings-section-title" style={{ marginTop: "var(--space-xl)" }}>
              User Overrides
            </h4>

            <div className="form-group">
              <label className="form-label">User ID</label>
              <input
                type="text"
                className="form-input"
                placeholder="UUID of user"
                value={overrideUserId}
                onChange={(e) => setOverrideUserId(e.target.value)}
              />
            </div>
            <div className="form-group">
              <label className="form-label" style={{ display: "flex", alignItems: "center", gap: "var(--space-sm)" }}>
                <input
                  type="checkbox"
                  checked={overrideExempt}
                  onChange={(e) => setOverrideExempt(e.target.checked)}
                />
                Payments Exempt
              </label>
            </div>
            <div className="form-group">
              <label className="form-label">Custom Tier</label>
              <select
                className="form-input"
                style={{ maxWidth: 200 }}
                value={overrideTier}
                onChange={(e) => setOverrideTier(e.target.value)}
              >
                <option value="">None</option>
                <option value="starter">Starter</option>
                <option value="professional">Professional</option>
                <option value="unlimited">Unlimited</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Custom Trial Days</label>
              <input
                type="number"
                className="form-input"
                style={{ maxWidth: 120 }}
                placeholder="e.g. 30"
                value={overrideTrialDays}
                onChange={(e) => setOverrideTrialDays(e.target.value)}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Notes</label>
              <input
                type="text"
                className="form-input"
                placeholder="Internal note"
                value={overrideNotes}
                onChange={(e) => setOverrideNotes(e.target.value)}
              />
            </div>
            <button className="save-btn" onClick={handleSetOverride} style={{ marginTop: "var(--space-sm)" }}>
              Save Override
            </button>

            {/* Existing Overrides */}
            {billingOverrides.length > 0 && (
              <div className="usage-table-wrapper" style={{ marginTop: "var(--space-lg)" }}>
                <table className="usage-table">
                  <thead>
                    <tr>
                      <th>User ID</th>
                      <th>Exempt</th>
                      <th>Custom Tier</th>
                      <th>Trial Days</th>
                      <th>Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {billingOverrides.map((o) => (
                      <tr key={String(o.user_id)}>
                        <td style={{ fontSize: "var(--font-size-xs)", fontFamily: "monospace" }}>
                          {String(o.user_id).slice(0, 8)}...
                        </td>
                        <td>{o.payments_exempt ? "Yes" : "No"}</td>
                        <td>{String(o.custom_tier || "—")}</td>
                        <td>{o.custom_trial_days != null ? String(o.custom_trial_days) : "—"}</td>
                        <td>{String(o.notes || "—")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
