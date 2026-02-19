import { useState, useEffect, useCallback } from "react";
import { sidecarApi } from "../../services/sidecarApi";
import { queueUpsertAfterMutation, deleteFromSupabase } from "../../services/syncEngine";
import { getMyShareRecipients, type ShareRecipient } from "../../services/sharingService";
import { isAuthConfigured, getSession } from "../../services/supabase";
import { useToast } from "../shared/Toast";
import { groupTypesByCategory } from "../../utils/testTypeCategories";
import type { Template, SharedTemplate, TestTypeInfo } from "../../types/sidecar";
import "./TemplatesScreen.css";
import "../shared/TypeModal.css";

interface FormState {
  name: string;
  test_types: string[];
  tone: string;
  structure_instructions: string;
  closing_text: string;
}

const EMPTY_FORM: FormState = {
  name: "",
  test_types: [],
  tone: "",
  structure_instructions: "",
  closing_text: "",
};

/** Get display names for test type IDs from the available types list. */
function typeDisplayNames(ids: string[], allTypes: TestTypeInfo[]): string[] {
  return ids.map((id) => {
    const match = allTypes.find((t) => t.test_type_id === id);
    return match ? match.display_name : id;
  });
}

export function TemplatesScreen() {
  const { showToast } = useToast();
  const [templates, setTemplates] = useState<Template[]>([]);
  const [sharedTemplates, setSharedTemplates] = useState<SharedTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | number | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | number | null>(null);
  const [recipients, setRecipients] = useState<ShareRecipient[]>([]);
  const [availableTypes, setAvailableTypes] = useState<TestTypeInfo[]>([]);
  const [collapsedCategories, setCollapsedCategories] = useState<Set<string>>(new Set());

  useEffect(() => {
    async function loadRecipients() {
      if (!isAuthConfigured()) return;
      const session = await getSession();
      if (!session?.user) return;
      try {
        const r = await getMyShareRecipients();
        setRecipients(r);
      } catch {}
    }
    loadRecipients();
  }, []);

  // Load available test types
  useEffect(() => {
    sidecarApi.listTestTypes().then((types) => {
      setAvailableTypes(
        types.map((t) => ({
          test_type_id: t.id,
          display_name: t.name,
          keywords: [],
          category: t.category,
        }))
      );
    }).catch(() => {});
  }, []);

  const fetchTemplates = useCallback(async () => {
    try {
      const [res, shared] = await Promise.all([
        sidecarApi.listTemplates(),
        sidecarApi.listSharedTemplates().catch(() => [] as SharedTemplate[]),
      ]);
      setTemplates(res.items);
      setSharedTemplates(shared);
    } catch {
      showToast("error", "Failed to load templates.");
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    fetchTemplates();
  }, [fetchTemplates]);

  const openCreate = () => {
    setForm(EMPTY_FORM);
    setEditingId(null);
    setCollapsedCategories(new Set());
    setShowForm(true);
  };

  const openEdit = (tpl: Template) => {
    setForm({
      name: tpl.name,
      test_types: tpl.test_types ?? (tpl.test_type ? [tpl.test_type] : []),
      tone: tpl.tone ?? "",
      structure_instructions: tpl.structure_instructions ?? "",
      closing_text: tpl.closing_text ?? "",
    });
    setEditingId(tpl.id);
    setCollapsedCategories(new Set());
    setShowForm(true);
  };

  const closeForm = () => {
    setShowForm(false);
    setEditingId(null);
    setForm(EMPTY_FORM);
  };

  const handleSave = async () => {
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      const payload = {
        name: form.name.trim(),
        test_types: form.test_types.length > 0 ? form.test_types : undefined,
        tone: form.tone.trim() || undefined,
        structure_instructions:
          form.structure_instructions.trim() || undefined,
        closing_text: form.closing_text.trim() || undefined,
      };

      if (editingId != null) {
        await sidecarApi.updateTemplate(editingId, payload);
        queueUpsertAfterMutation("templates", editingId).catch(() => {});
        showToast("success", "Template updated.");
      } else {
        const created = await sidecarApi.createTemplate(payload);
        queueUpsertAfterMutation("templates", created.id).catch(() => {});
        showToast("success", "Template created.");
      }
      closeForm();
      fetchTemplates();
    } catch {
      showToast("error", "Failed to save template.");
    } finally {
      setSaving(false);
    }
  };

  const handleToggleDefault = async (tpl: Template) => {
    const newDefault = !tpl.is_default;
    const typeNames = tpl.test_types?.length
      ? typeDisplayNames(tpl.test_types, availableTypes).join(", ")
      : tpl.test_type ?? "";
    try {
      await sidecarApi.updateTemplate(tpl.id, { is_default: newDefault });
      queueUpsertAfterMutation("templates", tpl.id).catch(() => {});
      fetchTemplates();
      showToast("success", newDefault ? `"${tpl.name}" set as default for ${typeNames}.` : "Default removed.");
    } catch {
      showToast("error", "Failed to update default.");
    }
  };

  const handleDelete = async (id: string | number) => {
    try {
      const tpl = templates.find((t) => t.id === id);
      await sidecarApi.deleteTemplate(id);
      setTemplates((prev) => prev.filter((t) => t.id !== id));
      if (tpl?.sync_id) {
        deleteFromSupabase("templates", tpl.sync_id).catch(() => {});
      }
      showToast("success", "Template deleted.");
    } catch {
      showToast("error", "Failed to delete template.");
    } finally {
      setDeletingId(null);
    }
  };

  const toggleType = (typeId: string) => {
    setForm((prev) => ({
      ...prev,
      test_types: prev.test_types.includes(typeId)
        ? prev.test_types.filter((t) => t !== typeId)
        : [...prev.test_types, typeId],
    }));
  };

  const toggleCategory = (label: string) => {
    setCollapsedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  };

  /** Render type badges for a template card. */
  const renderTypeBadges = (tpl: Template) => {
    const types = tpl.test_types ?? (tpl.test_type ? [tpl.test_type] : []);
    if (types.length === 0) return null;
    const names = typeDisplayNames(types, availableTypes);
    const show = names.slice(0, 3);
    const extra = names.length - show.length;
    return (
      <>
        {show.map((name) => (
          <span key={name} className="template-badge">{name}</span>
        ))}
        {extra > 0 && (
          <span className="template-badge template-badge--more">+{extra} more</span>
        )}
      </>
    );
  };

  const hasTypes = (tpl: Template) => {
    const types = tpl.test_types ?? (tpl.test_type ? [tpl.test_type] : []);
    return types.length > 0;
  };

  if (loading) {
    return (
      <div className="templates-screen">
        <p>Loading templates...</p>
      </div>
    );
  }

  return (
    <div className="templates-screen">
      <header className="templates-header">
        <h2 className="templates-title">Templates</h2>
        <p className="templates-description">
          Reusable formatting presets that control the tone, structure, and
          closing text of your explanations. Assign a template to a test type
          to automatically apply it during analysis.
        </p>
        <button className="templates-create-btn" onClick={openCreate}>
          New Template
        </button>
      </header>

      {templates.length === 0 && (
        <div className="templates-empty">
          <p>No templates yet. Create one to get started.</p>
        </div>
      )}

      <div className="templates-list">
        {templates.map((tpl) => (
          <div key={tpl.id} className="template-card">
            <div className="template-card-info">
              <div className="template-card-name">{tpl.name}</div>
              <div className="template-card-meta">
                {renderTypeBadges(tpl)}
                {tpl.tone && (
                  <span className="template-badge">{tpl.tone}</span>
                )}
                {tpl.is_default ? (
                  <span className="template-badge template-badge--default">Default</span>
                ) : null}
              </div>
            </div>
            <div className="template-card-actions">
              {deletingId === tpl.id ? (
                <div className="template-delete-confirm">
                  <span>Delete?</span>
                  <button
                    className="template-confirm-yes"
                    onClick={() => handleDelete(tpl.id)}
                  >
                    Yes
                  </button>
                  <button
                    className="template-confirm-no"
                    onClick={() => setDeletingId(null)}
                  >
                    No
                  </button>
                </div>
              ) : (
                <>
                  {hasTypes(tpl) && (
                    <button
                      className={`template-default-btn${tpl.is_default ? " template-default-btn--active" : ""}`}
                      onClick={() => handleToggleDefault(tpl)}
                      title={tpl.is_default ? "Remove as default" : "Set as default for assigned types"}
                    >
                      {tpl.is_default ? "Default" : "Set Default"}
                    </button>
                  )}
                  <button
                    className="template-edit-btn"
                    onClick={() => openEdit(tpl)}
                  >
                    Edit
                  </button>
                  <button
                    className="template-delete-btn"
                    onClick={() => setDeletingId(tpl.id)}
                  >
                    Delete
                  </button>
                </>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Shared Templates */}
      {sharedTemplates.length > 0 && (
        <div className="templates-shared-section">
          <h3 className="templates-shared-title">Shared Templates</h3>
          <p className="templates-shared-desc">
            These templates are shared by colleagues and can be used in your
            reports. They are read-only.
          </p>
          <div className="templates-list">
            {sharedTemplates.map((tpl) => (
              <div key={tpl.sync_id} className="template-card template-card--shared">
                <div className="template-card-info">
                  <div className="template-card-name">{tpl.name}</div>
                  <div className="template-card-meta">
                    <span className="template-badge template-badge--shared">
                      Shared by {tpl.sharer_email}
                    </span>
                    {(tpl.test_types ?? (tpl.test_type ? [tpl.test_type] : [])).map((t) => {
                      const match = availableTypes.find((at) => at.test_type_id === t);
                      return (
                        <span key={t} className="template-badge">
                          {match ? match.display_name : t}
                        </span>
                      );
                    })}
                    {tpl.tone && (
                      <span className="template-badge">{tpl.tone}</span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {recipients.length > 0 && (
        <p className="templates-shared-footer">
          Shared with: {recipients.map(r => r.recipient_email).join(", ")}
        </p>
      )}

      {showForm && (
        <div className="template-form-overlay" onClick={closeForm}>
          <div
            className="template-form"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="template-form-title">
              {editingId != null ? "Edit Template" : "New Template"}
            </h3>

            <div className="template-form-group">
              <label className="template-form-label">Name</label>
              <input
                className="template-form-input"
                type="text"
                value={form.name}
                onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
                placeholder="e.g. Cardiology Summary"
                maxLength={100}
              />
            </div>

            <div className="template-form-group">
              <label className="template-form-label">
                Test Types (optional)
                {form.test_types.length > 0 && (
                  <span className="template-type-count">
                    {form.test_types.length} selected
                  </span>
                )}
              </label>
              {availableTypes.length > 0 ? (
                <div className="template-type-picker">
                  {groupTypesByCategory(availableTypes).map(([label, types]) => (
                    <div key={label} className="template-type-category">
                      <button
                        type="button"
                        className="template-type-category-header"
                        onClick={() => toggleCategory(label)}
                      >
                        <span className={`settings-collapse-arrow${!collapsedCategories.has(label) ? " settings-collapse-arrow--open" : ""}`}>
                          &#9656;
                        </span>
                        {label}
                      </button>
                      {!collapsedCategories.has(label) && (
                        <div className="template-type-category-buttons">
                          {types.map((t) => (
                            <button
                              key={t.test_type_id}
                              type="button"
                              className={`detection-type-btn${form.test_types.includes(t.test_type_id) ? " detection-type-btn--active" : ""}`}
                              onClick={() => toggleType(t.test_type_id)}
                            >
                              {t.display_name}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="template-type-loading">Loading test types...</p>
              )}
            </div>

            <div className="template-form-group">
              <label className="template-form-label">Tone (optional)</label>
              <input
                className="template-form-input"
                type="text"
                value={form.tone}
                onChange={(e) => setForm((prev) => ({ ...prev, tone: e.target.value }))}
                placeholder="e.g. Warm and reassuring"
              />
            </div>

            <div className="template-form-group">
              <label className="template-form-label">
                Structure Instructions (optional)
              </label>
              <textarea
                className="template-form-textarea"
                value={form.structure_instructions}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, structure_instructions: e.target.value }))
                }
                placeholder="e.g. Start with a brief overview, then discuss abnormal values..."
                rows={4}
              />
            </div>

            <div className="template-form-group">
              <label className="template-form-label">
                Closing Text (optional)
              </label>
              <textarea
                className="template-form-textarea"
                value={form.closing_text}
                onChange={(e) => setForm((prev) => ({ ...prev, closing_text: e.target.value }))}
                placeholder="e.g. Please discuss these results with your provider at your next visit."
                rows={3}
              />
            </div>

            <div className="template-form-actions">
              <button
                className="template-form-cancel"
                onClick={closeForm}
              >
                Cancel
              </button>
              <button
                className="template-form-save"
                onClick={handleSave}
                disabled={saving || !form.name.trim()}
              >
                {saving ? "Saving..." : editingId != null ? "Update" : "Create"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
