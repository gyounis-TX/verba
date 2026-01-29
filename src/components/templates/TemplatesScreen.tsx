import { useState, useEffect, useCallback } from "react";
import { sidecarApi } from "../../services/sidecarApi";
import { useToast } from "../shared/Toast";
import type { Template } from "../../types/sidecar";
import "./TemplatesScreen.css";

interface FormState {
  name: string;
  test_type: string;
  tone: string;
  structure_instructions: string;
  closing_text: string;
}

const EMPTY_FORM: FormState = {
  name: "",
  test_type: "",
  tone: "",
  structure_instructions: "",
  closing_text: "",
};

export function TemplatesScreen() {
  const { showToast } = useToast();
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const fetchTemplates = useCallback(async () => {
    try {
      const res = await sidecarApi.listTemplates();
      setTemplates(res.items);
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
    setShowForm(true);
  };

  const openEdit = (tpl: Template) => {
    setForm({
      name: tpl.name,
      test_type: tpl.test_type ?? "",
      tone: tpl.tone ?? "",
      structure_instructions: tpl.structure_instructions ?? "",
      closing_text: tpl.closing_text ?? "",
    });
    setEditingId(tpl.id);
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
        test_type: form.test_type.trim() || undefined,
        tone: form.tone.trim() || undefined,
        structure_instructions:
          form.structure_instructions.trim() || undefined,
        closing_text: form.closing_text.trim() || undefined,
      };

      if (editingId != null) {
        await sidecarApi.updateTemplate(editingId, payload);
        showToast("success", "Template updated.");
      } else {
        await sidecarApi.createTemplate(payload);
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

  const handleDelete = async (id: number) => {
    try {
      await sidecarApi.deleteTemplate(id);
      setTemplates((prev) => prev.filter((t) => t.id !== id));
      showToast("success", "Template deleted.");
    } catch {
      showToast("error", "Failed to delete template.");
    } finally {
      setDeletingId(null);
    }
  };

  const updateField = (field: keyof FormState, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
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
                {tpl.test_type && (
                  <span className="template-badge">{tpl.test_type}</span>
                )}
                {tpl.tone && (
                  <span className="template-badge">{tpl.tone}</span>
                )}
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
                onChange={(e) => updateField("name", e.target.value)}
                placeholder="e.g. Cardiology Summary"
                maxLength={100}
              />
            </div>

            <div className="template-form-group">
              <label className="template-form-label">
                Test Type (optional)
              </label>
              <input
                className="template-form-input"
                type="text"
                value={form.test_type}
                onChange={(e) => updateField("test_type", e.target.value)}
                placeholder="e.g. cbc, lipid_panel"
              />
            </div>

            <div className="template-form-group">
              <label className="template-form-label">Tone (optional)</label>
              <input
                className="template-form-input"
                type="text"
                value={form.tone}
                onChange={(e) => updateField("tone", e.target.value)}
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
                  updateField("structure_instructions", e.target.value)
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
                onChange={(e) => updateField("closing_text", e.target.value)}
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
