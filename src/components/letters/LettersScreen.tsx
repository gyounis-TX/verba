import { useState, useEffect, useCallback } from "react";
import { useLocation } from "react-router-dom";
import { sidecarApi } from "../../services/sidecarApi";
import { queueUpsertAfterMutation, deleteFromSupabase } from "../../services/syncEngine";
import { useToast } from "../shared/Toast";
import type { LetterResponse } from "../../types/sidecar";
import "./LettersScreen.css";

export function LettersScreen() {
  const { showToast } = useToast();
  const location = useLocation();
  const locationState = location.state as { letterId?: number } | null;

  const [letter, setLetter] = useState<LetterResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  const fetchLetter = useCallback(async () => {
    setLoading(true);
    try {
      if (locationState?.letterId) {
        const l = await sidecarApi.getLetter(locationState.letterId);
        setLetter(l);
      } else {
        // Get the most recent letter
        const res = await sidecarApi.listLetters(0, 1);
        if (res.items.length > 0) {
          setLetter(res.items[0]);
        } else {
          setLetter(null);
        }
      }
    } catch {
      showToast("error", "Failed to load letter.");
    } finally {
      setLoading(false);
    }
  }, [showToast, locationState?.letterId]);

  useEffect(() => {
    fetchLetter();
  }, [fetchLetter]);

  const handleCopy = useCallback(async () => {
    if (!letter) return;
    try {
      await navigator.clipboard.writeText(letter.content);
      showToast("success", "Copied to clipboard.");
    } catch {
      showToast("error", "Failed to copy.");
    }
  }, [letter, showToast]);

  const handleToggleLike = useCallback(async () => {
    if (!letter) return;
    try {
      const newLiked = !letter.liked;
      await sidecarApi.toggleLetterLiked(letter.id, newLiked);
      setLetter((prev) => prev ? { ...prev, liked: newLiked } : null);
      queueUpsertAfterMutation("letters", letter.id).catch(() => {});
      showToast("success", newLiked ? "Liked!" : "Like removed.");
    } catch {
      showToast("error", "Failed to update like status.");
    }
  }, [letter, showToast]);

  const handleStartEdit = () => {
    if (!letter) return;
    setEditContent(letter.content);
    setIsEditing(true);
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditContent("");
  };

  const handleSaveEdit = useCallback(async () => {
    if (!letter || !editContent.trim()) return;
    setIsSaving(true);
    try {
      const updated = await sidecarApi.updateLetter(letter.id, editContent);
      setLetter(updated);
      setIsEditing(false);
      queueUpsertAfterMutation("letters", letter.id).catch(() => {});
      showToast("success", "Letter updated.");
    } catch {
      showToast("error", "Failed to save letter.");
    } finally {
      setIsSaving(false);
    }
  }, [letter, editContent, showToast]);

  const handleDelete = useCallback(async () => {
    if (!letter) return;
    if (!window.confirm("Delete this letter?")) return;
    try {
      const syncId = letter.sync_id;
      await sidecarApi.deleteLetter(letter.id);
      setLetter(null);
      if (syncId) {
        deleteFromSupabase("letters", syncId).catch(() => {});
      }
      showToast("success", "Letter deleted.");
    } catch {
      showToast("error", "Failed to delete letter.");
    }
  }, [letter, showToast]);

  const formatDate = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  };

  return (
    <div className="letters-screen">
      <header className="letters-header">
        <h2 className="letters-title">Letters</h2>
        <p className="letters-description">
          Most recent generated letter for patients.
        </p>
      </header>

      {loading ? (
        <div className="letters-loading">
          <div className="spinner" />
          <p>Loading letter...</p>
        </div>
      ) : !letter ? (
        <div className="letters-empty">
          <p>
            No letters yet. Use the "Help Me" section on the Import screen to
            generate patient-facing content.
          </p>
        </div>
      ) : (
        <div className="letter-single-view">
          <div className="letter-card">
            <div className="letter-card-header">
              <span className="letter-type-badge">{letter.letter_type}</span>
              <span className="letter-date">{formatDate(letter.created_at)}</span>
            </div>
            <p className="letter-prompt">{letter.prompt}</p>

            {isEditing ? (
              <div className="letter-edit-area">
                <textarea
                  className="letter-edit-textarea"
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  rows={12}
                />
                <div className="letter-edit-actions">
                  <button
                    className="letter-action-btn letter-action-btn--primary"
                    onClick={handleSaveEdit}
                    disabled={isSaving}
                  >
                    {isSaving ? "Saving..." : "Save"}
                  </button>
                  <button
                    className="letter-action-btn"
                    onClick={handleCancelEdit}
                    disabled={isSaving}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="letter-content">{letter.content}</div>
            )}

            <div className="letter-actions">
              <button
                className={`letter-like-btn${letter.liked ? " letter-like-btn--active" : ""}`}
                onClick={handleToggleLike}
              >
                {letter.liked ? "\u2665 Liked" : "\u2661 Like"}
              </button>
              <button className="letter-action-btn" onClick={handleCopy}>
                Copy
              </button>
              {!isEditing && (
                <button className="letter-action-btn" onClick={handleStartEdit}>
                  Edit
                </button>
              )}
              <button
                className="letter-action-btn letter-action-btn--danger"
                onClick={handleDelete}
              >
                Delete
              </button>
            </div>

            {(letter.model_used || letter.input_tokens != null) && (
              <footer className="letter-meta">
                <span>
                  {letter.model_used && `Model: ${letter.model_used}`}
                  {letter.input_tokens != null &&
                    ` | Tokens: ${letter.input_tokens} in / ${letter.output_tokens ?? 0} out`}
                </span>
              </footer>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
