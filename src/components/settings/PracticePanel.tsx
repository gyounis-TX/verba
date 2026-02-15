import { useState, useEffect, useCallback } from "react";
import { sidecarApi } from "../../services/sidecarApi";
import { isAuthConfigured, getSession } from "../../services/supabase";
import { useToast } from "../shared/Toast";
import type { PracticeInfo, PracticeMember, PracticeUsageSummary } from "../../types/practice";

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

export function PracticePanel() {
  const { showToast } = useToast();
  const [isSignedIn, setIsSignedIn] = useState(false);
  const [loading, setLoading] = useState(true);
  const [info, setInfo] = useState<PracticeInfo | null>(null);

  const checkAuth = useCallback(async () => {
    if (!isAuthConfigured()) {
      setIsSignedIn(false);
      setLoading(false);
      return;
    }
    const session = await getSession();
    setIsSignedIn(!!session?.user);
  }, []);

  const fetchPractice = useCallback(async () => {
    try {
      const data = await sidecarApi.getMyPractice();
      setInfo(data);
    } catch {
      // Silently fail
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    checkAuth().then(() => fetchPractice());
  }, [checkAuth, fetchPractice]);

  if (loading) return null;
  if (!isSignedIn) return null;

  if (!info) {
    return <NoPracticeView onJoined={fetchPractice} />;
  }

  if (info.role === "admin") {
    return <AdminView info={info} onUpdate={fetchPractice} />;
  }

  return <MemberView info={info} onLeft={fetchPractice} />;
}


function NoPracticeView({ onJoined }: { onJoined: () => void }) {
  const { showToast } = useToast();
  const [mode, setMode] = useState<"idle" | "join" | "create">("idle");
  const [joinCode, setJoinCode] = useState("");
  const [name, setName] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleJoin = useCallback(async () => {
    if (!joinCode.trim() || submitting) return;
    setSubmitting(true);
    try {
      await sidecarApi.joinPractice(joinCode.trim());
      showToast("success", "Joined practice successfully!");
      onJoined();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Failed to join.");
    } finally {
      setSubmitting(false);
    }
  }, [joinCode, submitting, showToast, onJoined]);

  const handleCreate = useCallback(async () => {
    if (!name.trim() || submitting) return;
    setSubmitting(true);
    try {
      await sidecarApi.createPractice(name.trim(), specialty || undefined);
      showToast("success", "Practice created!");
      onJoined();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Failed to create.");
    } finally {
      setSubmitting(false);
    }
  }, [name, specialty, submitting, showToast, onJoined]);

  return (
    <section className="settings-section practice-panel">
      <h3 className="settings-section-title">Practice</h3>
      <p className="settings-description" style={{ marginBottom: "var(--space-md)" }}>
        Join or create a practice to share teaching points and templates with your colleagues.
      </p>

      {mode === "idle" && (
        <div className="practice-actions-row">
          <button className="practice-btn practice-btn--primary" onClick={() => setMode("join")}>
            Join a Practice
          </button>
          <button className="practice-btn" onClick={() => setMode("create")}>
            Create a Practice
          </button>
        </div>
      )}

      {mode === "join" && (
        <div className="practice-form">
          <label className="form-label">Join Code</label>
          <div className="sharing-add">
            <input
              className="sharing-input"
              type="text"
              placeholder="e.g. A3K9M2XN"
              maxLength={8}
              value={joinCode}
              onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
              onKeyDown={(e) => { if (e.key === "Enter") handleJoin(); }}
              style={{ textTransform: "uppercase", letterSpacing: "0.15em", fontFamily: "monospace" }}
            />
            <button
              className="sharing-add-btn"
              onClick={handleJoin}
              disabled={!joinCode.trim() || submitting}
            >
              {submitting ? "Joining..." : "Join"}
            </button>
          </div>
          <button className="practice-link-btn" onClick={() => setMode("idle")}>Cancel</button>
        </div>
      )}

      {mode === "create" && (
        <div className="practice-form">
          <div className="form-group">
            <label className="form-label">Practice Name</label>
            <input
              className="form-input"
              type="text"
              placeholder="e.g. Main Street Cardiology"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="form-group">
            <label className="form-label">Specialty</label>
            <select className="form-input" value={specialty} onChange={(e) => setSpecialty(e.target.value)}>
              <option value="">Select a specialty...</option>
              {SPECIALTY_OPTIONS.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <div className="practice-actions-row">
            <button
              className="practice-btn practice-btn--primary"
              onClick={handleCreate}
              disabled={!name.trim() || submitting}
            >
              {submitting ? "Creating..." : "Create Practice"}
            </button>
            <button className="practice-link-btn" onClick={() => setMode("idle")}>Cancel</button>
          </div>
        </div>
      )}
    </section>
  );
}


function MemberView({ info, onLeft }: { info: PracticeInfo; onLeft: () => void }) {
  const { showToast } = useToast();
  const [leaving, setLeaving] = useState(false);

  const handleLeave = useCallback(async () => {
    if (!confirm("Are you sure you want to leave this practice?")) return;
    setLeaving(true);
    try {
      await sidecarApi.leavePractice();
      showToast("success", "Left practice.");
      onLeft();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Failed to leave.");
    } finally {
      setLeaving(false);
    }
  }, [showToast, onLeft]);

  return (
    <section className="settings-section practice-panel">
      <h3 className="settings-section-title">Practice</h3>
      <div className="practice-info-card">
        <div className="practice-info-row">
          <span className="practice-info-label">Name</span>
          <span className="practice-info-value">{info.practice.name}</span>
        </div>
        {info.practice.specialty && (
          <div className="practice-info-row">
            <span className="practice-info-label">Specialty</span>
            <span className="practice-info-value">{info.practice.specialty}</span>
          </div>
        )}
        <div className="practice-info-row">
          <span className="practice-info-label">Members</span>
          <span className="practice-info-value">{info.member_count}</span>
        </div>
        <div className="practice-info-row">
          <span className="practice-info-label">Join Code</span>
          <span className="practice-info-value" style={{ fontFamily: "monospace", letterSpacing: "0.1em" }}>
            {info.practice.join_code}
          </span>
        </div>
        <div className="practice-info-row">
          <span className="practice-info-label">Content Sharing</span>
          <span className="practice-info-value">{info.practice.sharing_enabled ? "On" : "Off"}</span>
        </div>
        <div className="practice-info-row">
          <span className="practice-info-label">Your Role</span>
          <span className="practice-info-value practice-role-badge">{info.role}</span>
        </div>
      </div>
      <button className="practice-btn practice-btn--danger" onClick={handleLeave} disabled={leaving} style={{ marginTop: "var(--space-md)" }}>
        {leaving ? "Leaving..." : "Leave Practice"}
      </button>
    </section>
  );
}


function AdminView({ info, onUpdate }: { info: PracticeInfo; onUpdate: () => void }) {
  const { showToast } = useToast();
  const [members, setMembers] = useState<PracticeMember[]>([]);
  const [usage, setUsage] = useState<PracticeUsageSummary | null>(null);
  const [usagePeriod, setUsagePeriod] = useState("30d");
  const [editName, setEditName] = useState(info.practice.name);
  const [editSpecialty, setEditSpecialty] = useState(info.practice.specialty || "");
  const [sharingEnabled, setSharingEnabled] = useState(info.practice.sharing_enabled);
  const [savingSettings, setSavingSettings] = useState(false);
  const [leaving, setLeaving] = useState(false);

  const fetchMembers = useCallback(async () => {
    try {
      const data = await sidecarApi.getPracticeMembers();
      setMembers(data);
    } catch {
      // ignore
    }
  }, []);

  const fetchUsage = useCallback(async () => {
    const sinceMap: Record<string, string> = {
      "7d": new Date(Date.now() - 7 * 86400000).toISOString(),
      "30d": new Date(Date.now() - 30 * 86400000).toISOString(),
      "all": "2000-01-01T00:00:00Z",
    };
    try {
      const data = await sidecarApi.getPracticeUsage(sinceMap[usagePeriod]);
      setUsage(data);
    } catch {
      // ignore
    }
  }, [usagePeriod]);

  useEffect(() => { fetchMembers(); }, [fetchMembers]);
  useEffect(() => { fetchUsage(); }, [fetchUsage]);

  const handleSaveSettings = useCallback(async () => {
    setSavingSettings(true);
    try {
      await sidecarApi.updatePracticeSettings({
        name: editName.trim(),
        specialty: editSpecialty || null,
        sharing_enabled: sharingEnabled,
      });
      showToast("success", "Practice settings saved.");
      onUpdate();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Failed to save.");
    } finally {
      setSavingSettings(false);
    }
  }, [editName, editSpecialty, sharingEnabled, showToast, onUpdate]);

  const handleRegenerateCode = useCallback(async () => {
    if (!confirm("This will invalidate the current join code. Continue?")) return;
    try {
      const result = await sidecarApi.regenerateJoinCode();
      showToast("success", `New join code: ${result.join_code}`);
      onUpdate();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Failed to regenerate.");
    }
  }, [showToast, onUpdate]);

  const handleRemoveMember = useCallback(async (userId: string, email: string) => {
    if (!confirm(`Remove ${email} from this practice?`)) return;
    try {
      await sidecarApi.removePracticeMember(userId);
      showToast("success", `${email} removed.`);
      fetchMembers();
      onUpdate();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Failed to remove.");
    }
  }, [showToast, fetchMembers, onUpdate]);

  const handleRoleChange = useCallback(async (userId: string, newRole: "admin" | "member") => {
    try {
      await sidecarApi.updateMemberRole(userId, newRole);
      showToast("success", `Role updated to ${newRole}.`);
      fetchMembers();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Failed to update role.");
    }
  }, [showToast, fetchMembers]);

  const handleCopyCode = useCallback(() => {
    navigator.clipboard.writeText(info.practice.join_code);
    showToast("success", "Join code copied!");
  }, [info.practice.join_code, showToast]);

  const handleLeave = useCallback(async () => {
    if (!confirm("Are you sure you want to leave this practice?")) return;
    setLeaving(true);
    try {
      await sidecarApi.leavePractice();
      showToast("success", "Left practice.");
      onUpdate();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Failed to leave.");
    } finally {
      setLeaving(false);
    }
  }, [showToast, onUpdate]);

  return (
    <section className="settings-section practice-panel">
      <h3 className="settings-section-title">Practice Admin</h3>

      {/* Settings */}
      <div className="practice-subsection">
        <h4 className="sharing-subtitle">Settings</h4>
        <div className="form-group">
          <label className="form-label">Practice Name</label>
          <input
            className="form-input"
            type="text"
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
          />
        </div>
        <div className="form-group">
          <label className="form-label">Specialty</label>
          <select className="form-input" value={editSpecialty} onChange={(e) => setEditSpecialty(e.target.value)}>
            <option value="">Select a specialty...</option>
            {SPECIALTY_OPTIONS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label className="form-label checkbox-label">
            <input
              type="checkbox"
              checked={sharingEnabled}
              onChange={(e) => setSharingEnabled(e.target.checked)}
            />
            <span className="checkbox-label-text">
              Content Sharing
              <span className="checkbox-label-hint">
                When enabled, all members' teaching points and templates are shared within the practice
              </span>
            </span>
          </label>
        </div>
        <button
          className="practice-btn practice-btn--primary"
          onClick={handleSaveSettings}
          disabled={savingSettings || !editName.trim()}
        >
          {savingSettings ? "Saving..." : "Save Settings"}
        </button>
      </div>

      {/* Join Code */}
      <div className="practice-subsection">
        <h4 className="sharing-subtitle">Join Code</h4>
        <div className="practice-code-row">
          <code className="practice-code">{info.practice.join_code}</code>
          <button className="practice-btn practice-btn--small" onClick={handleCopyCode}>Copy</button>
          <button className="practice-btn practice-btn--small" onClick={handleRegenerateCode}>Regenerate</button>
        </div>
        <p className="settings-description">
          Share this code with colleagues to invite them to your practice.
        </p>
      </div>

      {/* Members */}
      <div className="practice-subsection">
        <h4 className="sharing-subtitle">Members ({members.length})</h4>
        {members.length === 0 ? (
          <p className="sharing-empty">No members yet.</p>
        ) : (
          <div className="practice-members-table">
            <div className="practice-members-header">
              <span>Email</span>
              <span>Role</span>
              <span>Reports</span>
              <span>Last Active</span>
              <span></span>
            </div>
            {members.map((m) => (
              <div key={m.user_id} className="practice-member-row">
                <span className="practice-member-email">{m.email}</span>
                <span>
                  <select
                    className="practice-role-select"
                    value={m.role}
                    onChange={(e) => handleRoleChange(m.user_id, e.target.value as "admin" | "member")}
                  >
                    <option value="admin">Admin</option>
                    <option value="member">Member</option>
                  </select>
                </span>
                <span>{m.report_count}</span>
                <span className="practice-member-date">
                  {m.last_active ? new Date(m.last_active).toLocaleDateString() : "Never"}
                </span>
                <span>
                  <button
                    className="sharing-remove-btn"
                    onClick={() => handleRemoveMember(m.user_id, m.email)}
                    title={`Remove ${m.email}`}
                  >
                    Remove
                  </button>
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Usage */}
      <div className="practice-subsection">
        <h4 className="sharing-subtitle">Usage</h4>
        <div className="practice-usage-period">
          {(["7d", "30d", "all"] as const).map((p) => (
            <button
              key={p}
              className={`practice-btn practice-btn--small ${usagePeriod === p ? "practice-btn--active" : ""}`}
              onClick={() => setUsagePeriod(p)}
            >
              {p === "7d" ? "7 Days" : p === "30d" ? "30 Days" : "All Time"}
            </button>
          ))}
        </div>
        {usage && (
          <div className="practice-usage-cards">
            <div className="practice-usage-card">
              <span className="practice-usage-value">{usage.total_members}</span>
              <span className="practice-usage-label">Members</span>
            </div>
            <div className="practice-usage-card">
              <span className="practice-usage-value">{usage.total_queries.toLocaleString()}</span>
              <span className="practice-usage-label">Queries</span>
            </div>
            <div className="practice-usage-card">
              <span className="practice-usage-value">{usage.deep_analysis_count.toLocaleString()}</span>
              <span className="practice-usage-label">Deep Analyses</span>
            </div>
            <div className="practice-usage-card">
              <span className="practice-usage-value">
                {((usage.total_input_tokens + usage.total_output_tokens) / 1000).toFixed(0)}k
              </span>
              <span className="practice-usage-label">Total Tokens</span>
            </div>
          </div>
        )}
      </div>

      {/* Leave */}
      <button className="practice-btn practice-btn--danger" onClick={handleLeave} disabled={leaving} style={{ marginTop: "var(--space-md)" }}>
        {leaving ? "Leaving..." : "Leave Practice"}
      </button>
    </section>
  );
}
