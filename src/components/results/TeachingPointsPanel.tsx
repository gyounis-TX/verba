import { useState, useEffect, useMemo } from "react";
import type { TeachingPoint, SharedTeachingPoint } from "../../types/sidecar";
import { sidecarApi } from "../../services/sidecarApi";
import { queueUpsertAfterMutation } from "../../services/syncEngine";

interface TeachingPointsPanelProps {
  teachingPoints: TeachingPoint[];
  setTeachingPoints: React.Dispatch<React.SetStateAction<TeachingPoint[]>>;
  sharedTeachingPoints: SharedTeachingPoint[];
  newTeachingPoint: string;
  setNewTeachingPoint: (value: string) => void;
  effectiveTestType: string;
  effectiveTestTypeDisplay: string;
  showToast: (type: "success" | "error" | "info", message: string) => void;
  showUndoToast: (message: string, onUndo: () => void, duration?: number) => void;
  letterMode?: boolean;
}

export function TeachingPointsPanel({
  teachingPoints,
  setTeachingPoints,
  sharedTeachingPoints,
  newTeachingPoint,
  setNewTeachingPoint,
  effectiveTestType,
  effectiveTestTypeDisplay,
  showToast,
  showUndoToast,
  letterMode,
}: TeachingPointsPanelProps) {
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [editingTypeId, setEditingTypeId] = useState<string | number | null>(null);
  const [historyTypes, setHistoryTypes] = useState<{ test_type: string; test_type_display: string }[]>([]);
  const [saveType, setSaveType] = useState<string>("__current__");

  useEffect(() => {
    sidecarApi.listHistoryTestTypes().then(setHistoryTypes).catch(() => {});
  }, []);

  // Default save dropdown to current report's type
  useEffect(() => {
    setSaveType("__current__");
  }, [effectiveTestType]);

  const totalCount = teachingPoints.length + sharedTeachingPoints.length;

  // Deduplicated sorted set of all test_type values across own + shared points
  const uniqueTypes = useMemo(() => {
    const types = new Set<string>();
    for (const tp of teachingPoints) {
      if (tp.test_type) types.add(tp.test_type);
    }
    for (const sp of sharedTeachingPoints) {
      if (sp.test_type) types.add(sp.test_type);
    }
    return [...types].sort();
  }, [teachingPoints, sharedTeachingPoints]);

  const getDisplayName = (typeId: string): string => {
    const found = historyTypes.find(t => t.test_type === typeId);
    return found?.test_type_display ?? typeId.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
  };

  // Filter logic: "" = all, "__global__" = only null test_type, specific = that type + global
  const filteredTeachingPoints = useMemo(() => {
    if (!typeFilter) return teachingPoints;
    if (typeFilter === "__global__") return teachingPoints.filter((tp) => !tp.test_type);
    return teachingPoints.filter((tp) => !tp.test_type || tp.test_type === typeFilter);
  }, [teachingPoints, typeFilter]);

  const filteredSharedPoints = useMemo(() => {
    if (!typeFilter) return sharedTeachingPoints;
    if (typeFilter === "__global__") return sharedTeachingPoints.filter((sp) => !sp.test_type);
    return sharedTeachingPoints.filter((sp) => !sp.test_type || sp.test_type === typeFilter);
  }, [sharedTeachingPoints, typeFilter]);

  const handleSave = async () => {
    if (!newTeachingPoint.trim()) return;
    const testType = saveType === "__all__" ? undefined : (saveType === "__current__" ? effectiveTestType : saveType);
    try {
      const tp = await sidecarApi.createTeachingPoint({
        text: newTeachingPoint.trim(),
        test_type: testType,
      });
      setTeachingPoints((prev) => [tp, ...prev]);
      setNewTeachingPoint("");
      queueUpsertAfterMutation("teaching_points", tp.id).catch(() => {});
    } catch {
      showToast("error", "Failed to save teaching point.");
    }
  };

  const handleDelete = (id: string | number) => {
    const point = teachingPoints.find((p) => p.id === id);
    if (!point) return;

    // Optimistic removal
    setTeachingPoints((prev) => prev.filter((p) => p.id !== id));

    // Schedule actual deletion after undo window
    const timer = setTimeout(async () => {
      try {
        await sidecarApi.deleteTeachingPoint(id);
      } catch {
        setTeachingPoints((prev) => [point, ...prev]);
        showToast("error", "Failed to delete teaching point.");
      }
    }, 5200);

    showUndoToast("Teaching point deleted.", () => {
      clearTimeout(timer);
      setTeachingPoints((prev) => [point, ...prev]);
      showToast("success", "Teaching point restored.");
    });
  };

  const handleTypeChange = async (id: string | number, newType: string) => {
    setEditingTypeId(null);
    const prev = teachingPoints.find((tp) => tp.id === id);
    if (!prev) return;

    const resolvedType = newType === "__all__" ? null : newType;
    if (resolvedType === (prev.test_type ?? null)) return;

    setTeachingPoints((pts) =>
      pts.map((tp) => (tp.id === id ? { ...tp, test_type: resolvedType } : tp)),
    );
    try {
      await sidecarApi.updateTeachingPoint(id, { test_type: resolvedType });
      queueUpsertAfterMutation("teaching_points", id).catch(() => {});
    } catch {
      setTeachingPoints((pts) =>
        pts.map((tp) => (tp.id === id ? { ...tp, test_type: prev.test_type } : tp)),
      );
      showToast("error", "Failed to update teaching point type.");
    }
  };

  return (
    <details className="teaching-points-panel teaching-points-collapsible">
      <summary className="teaching-points-header">
        <h3>Teaching Points</h3>
        {totalCount > 0 && (
          <span className="teaching-points-count">{totalCount}</span>
        )}
      </summary>
      <div className="teaching-points-body">
        <p className="teaching-points-desc">
          {letterMode
            ? "Add personalized instructions that customize how AI generates letters. These points can be stylistic or clinical. Explify will remember and apply these to all future outputs."
            : "Add personalized instructions that customize how AI interprets and explains results. These points can be stylistic or clinical. Explify will remember and apply these to all future explanations."}
        </p>

        {/* Filter dropdown */}
        {uniqueTypes.length > 0 && (
          <div className="teaching-points-filter-row">
            <select
              className="teaching-points-filter-select"
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
            >
              <option value="">All teaching points</option>
              <option value="__global__">Global only</option>
              {uniqueTypes.map((t) => (
                <option key={t} value={t}>{getDisplayName(t)}</option>
              ))}
            </select>
          </div>
        )}

        <div className="teaching-point-input-row">
          <textarea
            className="teaching-point-input"
            autoComplete="off"
            placeholder={letterMode
              ? "e.g. Always use a warm, conversational tone"
              : "e.g. Always mention diastolic dysfunction grading"}
            value={newTeachingPoint}
            onChange={(e) => setNewTeachingPoint(e.target.value)}
            rows={3}
          />
          <div className="teaching-point-save-row">
            <select
              className="teaching-point-type-dropdown"
              value={saveType}
              onChange={(e) => setSaveType(e.target.value)}
            >
              {!letterMode && (
                <option value="__current__">{effectiveTestTypeDisplay}</option>
              )}
              <option value="__all__">All types</option>
              {historyTypes
                .filter((ht) => ht.test_type !== effectiveTestType)
                .map((ht) => (
                  <option key={ht.test_type} value={ht.test_type}>
                    {ht.test_type_display}
                  </option>
                ))}
            </select>
            <button
              className="teaching-point-save-btn"
              disabled={!newTeachingPoint.trim()}
              onClick={handleSave}
            >
              Save
            </button>
          </div>
        </div>
        {filteredTeachingPoints.length > 0 && (
          <div className="own-teaching-points">
            <span className="own-teaching-points-label">Your teaching points</span>
            {filteredTeachingPoints.map((tp) => (
              <div key={tp.id} className="own-teaching-point-card">
                <p className="own-teaching-point-text">{tp.text}</p>
                <div className="own-teaching-point-meta">
                  {editingTypeId === tp.id ? (
                    <select
                      className="own-teaching-point-type-select"
                      defaultValue={tp.test_type ?? "__all__"}
                      autoFocus
                      onChange={(e) => handleTypeChange(tp.id, e.target.value)}
                      onBlur={() => setEditingTypeId(null)}
                    >
                      <option value="__all__">All types</option>
                      {historyTypes.map((ht) => (
                        <option key={ht.test_type} value={ht.test_type}>
                          {ht.test_type_display}
                        </option>
                      ))}
                    </select>
                  ) : tp.test_type ? (
                    <span
                      className="own-teaching-point-type"
                      onClick={() => setEditingTypeId(tp.id)}
                      title="Click to change type"
                    >
                      {getDisplayName(tp.test_type)}
                    </span>
                  ) : (
                    <span
                      className="own-teaching-point-type own-teaching-point-type--global"
                      onClick={() => setEditingTypeId(tp.id)}
                      title="Click to change type"
                    >
                      All types
                    </span>
                  )}
                  <button
                    className="own-teaching-point-delete"
                    onClick={() => handleDelete(tp.id)}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
        {filteredSharedPoints.length > 0 && (
          <div className="shared-teaching-points">
            <span className="shared-teaching-points-label">Shared with you</span>
            {filteredSharedPoints.map((sp) => (
              <div key={sp.sync_id} className="shared-teaching-point-card">
                <p className="shared-teaching-point-text">{sp.text}</p>
                <div className="shared-teaching-point-meta">
                  <span className="shared-teaching-point-sharer">
                    Shared by {sp.sharer_email}
                  </span>
                  {sp.test_type ? (
                    <span className="shared-teaching-point-type">
                      {getDisplayName(sp.test_type)}
                    </span>
                  ) : (
                    <span className="shared-teaching-point-type shared-teaching-point-type--global">All types</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </details>
  );
}
