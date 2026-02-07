import { useState, useEffect, useCallback } from "react";
import { sidecarApi } from "../../services/sidecarApi";
import { queueUpsertAfterMutation, deleteFromSupabase } from "../../services/syncEngine";
import { getMyShareRecipients, type ShareRecipient } from "../../services/sharingService";
import { getSupabase, getSession } from "../../services/supabase";
import { useToast } from "../shared/Toast";
import type { TeachingPoint, SharedTeachingPoint } from "../../types/sidecar";
import "./TeachingPointsScreen.css";

export function TeachingPointsScreen() {
  const { showToast } = useToast();
  const [teachingPoints, setTeachingPoints] = useState<TeachingPoint[]>([]);
  const [sharedPoints, setSharedPoints] = useState<SharedTeachingPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [newText, setNewText] = useState("");
  const [saving, setSaving] = useState(false);

  // Recipients state (for "Shared with" footer)
  const [recipients, setRecipients] = useState<ShareRecipient[]>([]);

  // Edit state
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editText, setEditText] = useState("");
  const [editScope, setEditScope] = useState<string | null>(null);

  // Inline type-edit state (click badge to change type without full edit mode)
  const [inlineTypeEditId, setInlineTypeEditId] = useState<number | null>(null);

  // Valid test types from registry (for validation)
  const [validTypes, setValidTypes] = useState<{ id: string; name: string }[]>([]);

  const fetchPoints = useCallback(async () => {
    try {
      const [pts, shared] = await Promise.all([
        sidecarApi.listTeachingPoints(),
        sidecarApi.listSharedTeachingPoints().catch(() => [] as SharedTeachingPoint[]),
      ]);
      setTeachingPoints(pts);
      setSharedPoints(shared);
    } catch {
      showToast("error", "Failed to load teaching points.");
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    fetchPoints();
    sidecarApi.listTestTypes().then(setValidTypes).catch(() => {});
  }, [fetchPoints]);

  useEffect(() => {
    async function loadRecipients() {
      const supabase = getSupabase();
      if (!supabase) return;
      const session = await getSession();
      if (!session?.user) return;
      try {
        const r = await getMyShareRecipients();
        setRecipients(r);
      } catch {}
    }
    loadRecipients();
  }, []);

  const handleAdd = useCallback(async () => {
    const text = newText.trim();
    if (!text || saving) return;
    setSaving(true);
    try {
      const tp = await sidecarApi.createTeachingPoint({ text });
      setTeachingPoints((prev) => [tp, ...prev]);
      setNewText("");
      queueUpsertAfterMutation("teaching_points", tp.id).catch(() => {});
      showToast("success", "Teaching point saved.");
    } catch {
      showToast("error", "Failed to save teaching point.");
    } finally {
      setSaving(false);
    }
  }, [newText, saving, showToast]);

  const handleDelete = useCallback(
    async (id: number) => {
      try {
        const tp = teachingPoints.find((p) => p.id === id);
        await sidecarApi.deleteTeachingPoint(id);
        setTeachingPoints((prev) => prev.filter((p) => p.id !== id));
        if (tp?.sync_id) {
          deleteFromSupabase("teaching_points", tp.sync_id).catch(() => {});
        }
        showToast("success", "Teaching point removed.");
      } catch {
        showToast("error", "Failed to delete teaching point.");
      }
    },
    [showToast, teachingPoints],
  );

  const startEditing = useCallback((tp: TeachingPoint) => {
    setEditingId(tp.id);
    setEditText(tp.text);
    setEditScope(tp.test_type ?? null);
  }, []);

  const cancelEditing = useCallback(() => {
    setEditingId(null);
    setEditText("");
    setEditScope(null);
  }, []);

  // All valid types for the datalist (registry + any already used), with display names
  const allTypeOptions = (() => {
    const map = new Map<string, string>();
    for (const t of validTypes) map.set(t.id, t.name);
    for (const tp of teachingPoints) {
      if (tp.test_type && !map.has(tp.test_type)) {
        map.set(tp.test_type, tp.test_type.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()));
      }
    }
    return [...map.entries()].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name));
  })();

  /** Try to match free-text input to a valid registry type ID. */
  const resolveTypeId = (input: string): string | null => {
    if (!input) return null;
    const lower = input.toLowerCase().replace(/[\s_-]+/g, "_");
    // Exact match on ID
    const exact = validTypes.find((t) => t.id === lower);
    if (exact) return exact.id;
    // Exact match on display name (case-insensitive)
    const byName = validTypes.find((t) => t.name.toLowerCase() === input.toLowerCase());
    if (byName) return byName.id;
    // Partial match: input contained in name or ID
    const partial = validTypes.find(
      (t) => t.id.includes(lower) || t.name.toLowerCase().includes(input.toLowerCase()),
    );
    if (partial) return partial.id;
    return null;
  };

  const getDisplayName = (typeId: string): string => {
    const found = validTypes.find(t => t.id === typeId);
    return found?.name ?? typeId.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
  };

  const handleInlineTypeChange = useCallback(
    async (id: number, rawInput: string | null) => {
      setInlineTypeEditId(null);
      const prev = teachingPoints.find((tp) => tp.id === id);
      if (!prev) return;

      // Blank = "All types"
      if (!rawInput) {
        if (prev.test_type === null) return;
        setTeachingPoints((pts) =>
          pts.map((tp) => (tp.id === id ? { ...tp, test_type: null } : tp)),
        );
        try {
          await sidecarApi.updateTeachingPoint(id, { test_type: null });
          queueUpsertAfterMutation("teaching_points", id).catch(() => {});
        } catch {
          setTeachingPoints((pts) =>
            pts.map((tp) => (tp.id === id ? { ...tp, test_type: prev.test_type } : tp)),
          );
          showToast("error", "Failed to update type.");
        }
        return;
      }

      const resolved = resolveTypeId(rawInput);
      if (!resolved) {
        showToast("info", "No matching type found. Try picking from the suggestions.");
        return;
      }
      if (resolved === prev.test_type) return;

      setTeachingPoints((pts) =>
        pts.map((tp) => (tp.id === id ? { ...tp, test_type: resolved } : tp)),
      );
      try {
        await sidecarApi.updateTeachingPoint(id, { test_type: resolved });
        queueUpsertAfterMutation("teaching_points", id).catch(() => {});
      } catch {
        setTeachingPoints((pts) =>
          pts.map((tp) => (tp.id === id ? { ...tp, test_type: prev.test_type } : tp)),
        );
        showToast("error", "Failed to update type.");
      }
    },
    [teachingPoints, showToast, validTypes],
  );

  const handleSaveEdit = useCallback(async () => {
    if (editingId === null || !editText.trim()) return;
    try {
      const updated = await sidecarApi.updateTeachingPoint(editingId, {
        text: editText.trim(),
        test_type: editScope,
      });
      setTeachingPoints((prev) =>
        prev.map((p) => (p.id === editingId ? updated : p)),
      );
      setEditingId(null);
      queueUpsertAfterMutation("teaching_points", editingId).catch(() => {});
      showToast("success", "Teaching point updated.");
    } catch {
      showToast("error", "Failed to update teaching point.");
    }
  }, [editingId, editText, editScope, showToast]);

  if (loading) {
    return (
      <div className="tp-screen">
        <p>Loading teaching points...</p>
      </div>
    );
  }

  return (
    <div className="tp-screen">
      <header className="tp-header">
        <h2 className="tp-title">Teaching Points</h2>
        <p className="tp-description">
          Personalized instructions that customize how the AI interprets and
          explains results. These points can be stylistic or clinical. They are
          applied automatically during every analysis.
        </p>
      </header>

      {/* Data Entry */}
      <section className="tp-section tp-entry">
        <h3 className="tp-section-title">Add Teaching Point</h3>
        <p className="tp-section-desc">
          Write an instruction the AI should follow when generating
          explanations. For example: "Always mention diastolic dysfunction
          grading" or "De-emphasize trace regurgitation".
        </p>
        <div className="tp-entry-form">
          <textarea
            className="tp-entry-textarea"
            placeholder="e.g. Always explain the significance of E/A ratio in the context of diastolic function..."
            value={newText}
            onChange={(e) => setNewText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && newText.trim()) {
                e.preventDefault();
                handleAdd();
              }
            }}
            rows={4}
          />
          <button
            className="tp-entry-btn"
            disabled={!newText.trim() || saving}
            onClick={handleAdd}
          >
            {saving ? "Saving..." : "Add Teaching Point"}
          </button>
        </div>
      </section>

      {/* Library */}
      <section className="tp-section tp-library">
        <h3 className="tp-section-title">
          Library
          {teachingPoints.length > 0 && (
            <span className="tp-library-count">{teachingPoints.length}</span>
          )}
        </h3>
        {teachingPoints.length === 0 ? (
          <div className="tp-empty">
            <p>No teaching points yet.</p>
            <p className="tp-empty-hint">
              Add your first teaching point above to start customizing the AI.
            </p>
          </div>
        ) : (
          <div className="tp-library-list">
            {teachingPoints.map((tp) => (
              <div key={tp.id} className="tp-card">
                {editingId === tp.id ? (
                  <div className="tp-card-edit">
                    <textarea
                      className="tp-edit-textarea"
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      rows={3}
                      autoFocus
                    />
                    <div className="tp-edit-scope">
                      <span className="tp-edit-scope-label">Scope:</span>
                      <button
                        className={`tp-edit-scope-btn${editScope !== null ? " tp-edit-scope-btn--active" : ""}`}
                        onClick={() => setEditScope(tp.test_type ?? "General")}
                      >
                        {tp.test_type || "Original type"}
                      </button>
                      <button
                        className={`tp-edit-scope-btn${editScope === null ? " tp-edit-scope-btn--active" : ""}`}
                        onClick={() => setEditScope(null)}
                      >
                        All types
                      </button>
                    </div>
                    <div className="tp-edit-actions">
                      <button
                        className="tp-edit-save"
                        disabled={!editText.trim()}
                        onClick={handleSaveEdit}
                      >
                        Save
                      </button>
                      <button
                        className="tp-edit-cancel"
                        onClick={cancelEditing}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="tp-card-body">
                      <p className="tp-card-text">{tp.text}</p>
                      <div className="tp-card-meta">
                        {inlineTypeEditId === tp.id ? (
                          <>
                            <input
                              className="tp-card-type-select"
                              list={`tp-type-list-${tp.id}`}
                              defaultValue={tp.test_type ? getDisplayName(tp.test_type) : ""}
                              placeholder="Type or pick (blank = all)"
                              autoFocus
                              onKeyDown={(e) => {
                                if (e.key === "Enter") {
                                  const val = (e.target as HTMLInputElement).value.trim() || null;
                                  handleInlineTypeChange(tp.id, val);
                                } else if (e.key === "Escape") {
                                  setInlineTypeEditId(null);
                                }
                              }}
                              onBlur={(e) => {
                                const val = e.target.value.trim() || null;
                                handleInlineTypeChange(tp.id, val);
                              }}
                            />
                            <datalist id={`tp-type-list-${tp.id}`}>
                              {allTypeOptions.map((t) => (
                                <option key={t.id} value={t.name} />
                              ))}
                            </datalist>
                          </>
                        ) : tp.test_type ? (
                          <>
                            <span
                              className="tp-card-type tp-card-type--clickable"
                              onClick={() => setInlineTypeEditId(tp.id)}
                              title="Click to change type"
                            >
                              {tp.test_type}
                            </span>
                            <span
                              className="tp-card-type tp-card-type--display tp-card-type--clickable"
                              onClick={() => setInlineTypeEditId(tp.id)}
                              title="Click to change type"
                            >
                              {getDisplayName(tp.test_type)}
                            </span>
                          </>
                        ) : (
                          <span
                            className="tp-card-type tp-card-type--global tp-card-type--clickable"
                            onClick={() => setInlineTypeEditId(tp.id)}
                            title="Click to assign a type"
                          >
                            All types
                          </span>
                        )}
                        <span className="tp-card-date">
                          {new Date(tp.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                    <button
                      className="tp-card-edit-btn"
                      onClick={() => startEditing(tp)}
                      aria-label={`Edit teaching point: ${tp.text.slice(0, 30)}`}
                      title="Edit this teaching point"
                    >
                      Edit
                    </button>
                    <button
                      className="tp-card-delete"
                      onClick={() => handleDelete(tp.id)}
                      aria-label={`Delete teaching point: ${tp.text.slice(0, 30)}`}
                      title="Delete this teaching point"
                    >
                      &times;
                    </button>
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Shared With You */}
      {sharedPoints.length > 0 && (
        <section className="tp-section tp-shared">
          <h3 className="tp-section-title">
            Shared With You
            <span className="tp-library-count">{sharedPoints.length}</span>
          </h3>
          <p className="tp-section-desc">
            These teaching points are shared by colleagues and are automatically
            included in your reports.
          </p>
          <div className="tp-library-list">
            {sharedPoints.map((sp) => (
              <div key={sp.sync_id} className="tp-card tp-card--shared">
                <div className="tp-card-body">
                  <p className="tp-card-text">{sp.text}</p>
                  <div className="tp-card-meta">
                    <span className="tp-card-sharer">
                      Shared by {sp.sharer_email}
                    </span>
                    {sp.test_type ? (
                      <span className="tp-card-type">{sp.test_type}</span>
                    ) : (
                      <span className="tp-card-type tp-card-type--global">
                        All types
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {recipients.length > 0 && (
        <p className="tp-shared-footer">
          Shared with: {recipients.map(r => r.recipient_email).join(", ")}
        </p>
      )}
    </div>
  );
}
