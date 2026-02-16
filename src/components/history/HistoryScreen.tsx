import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { sidecarApi } from "../../services/sidecarApi";
import { queueUpsertAfterMutation, deleteFromSupabase } from "../../services/syncEngine";
import { useToast } from "../shared/Toast";
import type { HistoryListItem, LetterResponse } from "../../types/sidecar";
import "./HistoryScreen.css";

type Tab = "reports" | "letters";
type ItemId = string | number;

export function HistoryScreen() {
  const navigate = useNavigate();
  const { showToast, showUndoToast } = useToast();
  const [activeTab, setActiveTab] = useState<Tab>("reports");

  // Reports state
  const [items, setItems] = useState<HistoryListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<ItemId | null>(null);
  const [likedOnly, setLikedOnly] = useState(false);
  const [testTypeFilter, setTestTypeFilter] = useState("");
  const [availableTestTypes, setAvailableTestTypes] = useState<string[]>([]);
  const [compareMode, setCompareMode] = useState(false);
  const [selectedForCompare, setSelectedForCompare] = useState<Set<ItemId>>(new Set());
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const limit = 20;

  // Letters state
  const [letters, setLetters] = useState<LetterResponse[]>([]);
  const [lettersTotal, setLettersTotal] = useState(0);
  const [lettersOffset, setLettersOffset] = useState(0);
  const [lettersSearch, setLettersSearch] = useState("");
  const [lettersLikedOnly, setLettersLikedOnly] = useState(false);
  const [lettersLoading, setLettersLoading] = useState(false);
  const lettersDebounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const lettersLimit = 20;

  const fetchHistory = useCallback(
    async (searchTerm: string, newOffset: number, filterLiked: boolean) => {
      setLoading(true);
      try {
        const res = await sidecarApi.listHistory(
          newOffset,
          limit,
          searchTerm || undefined,
          filterLiked || undefined,
        );
        if (newOffset === 0) {
          setItems(res.items);
        } else {
          setItems((prev) => [...prev, ...res.items]);
        }
        setTotal(res.total);

        // Extract unique test types for filter dropdown (only on first load)
        if (newOffset === 0 && !searchTerm && !filterLiked) {
          const types = [...new Set(res.items.map((i) => i.test_type_display))];
          setAvailableTestTypes((prev) => {
            const combined = new Set([...prev, ...types]);
            return [...combined].sort();
          });
        }
      } catch {
        showToast("error", "Failed to load history.");
      } finally {
        setLoading(false);
      }
    },
    [showToast],
  );

  const fetchLetters = useCallback(
    async (searchTerm: string, newOffset: number, filterLiked: boolean) => {
      setLettersLoading(true);
      try {
        const res = await sidecarApi.listLetters(
          newOffset,
          lettersLimit,
          searchTerm || undefined,
          filterLiked || undefined,
        );
        if (newOffset === 0) {
          setLetters(res.items);
        } else {
          setLetters((prev) => [...prev, ...res.items]);
        }
        setLettersTotal(res.total);
      } catch {
        showToast("error", "Failed to load letters.");
      } finally {
        setLettersLoading(false);
      }
    },
    [showToast],
  );

  useEffect(() => {
    fetchHistory("", 0, likedOnly);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [fetchHistory, likedOnly]);

  useEffect(() => {
    if (activeTab === "letters") {
      fetchLetters("", 0, lettersLikedOnly);
    }
    return () => {
      if (lettersDebounceRef.current) clearTimeout(lettersDebounceRef.current);
    };
  }, [activeTab, fetchLetters, lettersLikedOnly]);

  const handleSearchChange = (value: string) => {
    setSearch(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setOffset(0);
      fetchHistory(value, 0, likedOnly);
    }, 300);
  };

  const handleLettersSearchChange = (value: string) => {
    setLettersSearch(value);
    if (lettersDebounceRef.current) clearTimeout(lettersDebounceRef.current);
    lettersDebounceRef.current = setTimeout(() => {
      setLettersOffset(0);
      fetchLetters(value, 0, lettersLikedOnly);
    }, 300);
  };

  const handleLoadMore = () => {
    const newOffset = offset + limit;
    setOffset(newOffset);
    fetchHistory(search, newOffset, likedOnly);
  };

  const handleLettersLoadMore = () => {
    const newOffset = lettersOffset + lettersLimit;
    setLettersOffset(newOffset);
    fetchLetters(lettersSearch, newOffset, lettersLikedOnly);
  };

  const handleCardClick = async (id: ItemId) => {
    try {
      const detail = await sidecarApi.getHistoryDetail(id);
      navigate("/results", {
        state: {
          explainResponse: detail.full_response,
          fromHistory: true,
          historyId: detail.id,
          historyLiked: detail.liked,
        },
      });
    } catch {
      showToast("error", "Failed to load analysis details.");
    }
  };

  const handleLetterClick = (letterId: ItemId) => {
    navigate("/letters", { state: { letterId } });
  };

  const pendingDeleteRef = useRef<Map<ItemId, ReturnType<typeof setTimeout>>>(new Map());

  const handleDelete = (id: ItemId) => {
    const item = items.find((i) => i.id === id);
    if (!item) return;
    setDeletingId(null);

    // Optimistic removal
    setItems((prev) => prev.filter((i) => i.id !== id));
    setTotal((prev) => prev - 1);

    // Schedule actual deletion after undo window
    const timer = setTimeout(async () => {
      pendingDeleteRef.current.delete(id);
      try {
        await sidecarApi.deleteHistory(id);
        if (item.sync_id) {
          deleteFromSupabase("history", item.sync_id).catch(() => {});
        }
      } catch {
        // Deletion failed — restore the item
        setItems((prev) => [item, ...prev]);
        setTotal((prev) => prev + 1);
        showToast("error", "Failed to delete record.");
      }
    }, 5200);
    pendingDeleteRef.current.set(id, timer);

    showUndoToast("Record deleted.", () => {
      // Undo: cancel the pending deletion and restore the item
      const pending = pendingDeleteRef.current.get(id);
      if (pending) {
        clearTimeout(pending);
        pendingDeleteRef.current.delete(id);
      }
      setItems((prev) => [item, ...prev].sort((a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      ));
      setTotal((prev) => prev + 1);
      showToast("success", "Record restored.");
    });
  };

  const handleToggleLikedFilter = () => {
    setLikedOnly((prev) => !prev);
    setOffset(0);
  };

  const handleToggleCompareMode = () => {
    setCompareMode((prev) => !prev);
    setSelectedForCompare(new Set());
  };

  const handleToggleCompareSelect = (id: ItemId) => {
    setSelectedForCompare((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else if (next.size < 2) {
        next.add(id);
      }
      return next;
    });
  };

  const handleCompare = () => {
    if (selectedForCompare.size !== 2) return;
    const ids = [...selectedForCompare] as [ItemId, ItemId];
    navigate("/comparison", { state: { historyIds: ids } });
  };

  const handleToggleLike = async (id: ItemId, currentLiked: boolean) => {
    try {
      const newLiked = !currentLiked;
      await sidecarApi.toggleHistoryLiked(id, newLiked);
      setItems((prev) =>
        prev.map((item) =>
          item.id === id ? { ...item, liked: newLiked } : item,
        ),
      );
      queueUpsertAfterMutation("history", id).catch(() => {});
      showToast("success", newLiked ? "Liked!" : "Like removed.");
    } catch {
      showToast("error", "Failed to update like status.");
    }
  };

  const handleToggleLetterLike = async (id: ItemId, currentLiked: boolean) => {
    try {
      const newLiked = !currentLiked;
      await sidecarApi.toggleLetterLiked(id, newLiked);
      setLetters((prev) =>
        prev.map((l) => (l.id === id ? { ...l, liked: newLiked } : l)),
      );
      queueUpsertAfterMutation("letters", id).catch(() => {});
      showToast("success", newLiked ? "Liked!" : "Like removed.");
    } catch {
      showToast("error", "Failed to update like status.");
    }
  };

  const formatDate = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const filteredItems = testTypeFilter
    ? items.filter((i) => i.test_type_display === testTypeFilter)
    : items;

  return (
    <div className="history-screen">
      <header className="history-header">
        <h2 className="history-title">History</h2>
      </header>

      {/* Tab Navigation */}
      <div className="history-tabs">
        <button
          className={`history-tab${activeTab === "reports" ? " history-tab--active" : ""}`}
          onClick={() => setActiveTab("reports")}
        >
          Reports
        </button>
        <button
          className={`history-tab${activeTab === "letters" ? " history-tab--active" : ""}`}
          onClick={() => setActiveTab("letters")}
        >
          Letters
        </button>
      </div>

      {/* Reports Tab */}
      {activeTab === "reports" && (
        <>
          <div className="history-search">
            <input
              type="text"
              className="history-search-input"
              placeholder="Search history..."
              value={search}
              onChange={(e) => handleSearchChange(e.target.value)}
            />
          </div>

          <div className="history-filters">
            <button
              className={`history-filter-btn${likedOnly ? " history-filter-btn--active" : ""}`}
              onClick={handleToggleLikedFilter}
            >
              {likedOnly ? "\u2665 Liked Only" : "\u2661 Liked Only"}
            </button>
            {availableTestTypes.length > 0 && (
              <select
                className="history-type-filter"
                value={testTypeFilter}
                onChange={(e) => setTestTypeFilter(e.target.value)}
              >
                <option value="">All Types</option>
                {availableTestTypes.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            )}
            <button
              className={`history-filter-btn history-compare-toggle${compareMode ? " history-filter-btn--compare-active" : ""}`}
              onClick={handleToggleCompareMode}
            >
              {compareMode ? "Cancel Compare" : "Compare"}
            </button>
          </div>

          {!loading && filteredItems.length === 0 && (
            <div className="history-empty">
              {search ? (
                <p>No results for &ldquo;{search}&rdquo;.</p>
              ) : (
                <>
                  <p>No analysis history yet.</p>
                  <p className="history-empty-hint">
                    Results will appear here after you analyze a report.
                  </p>
                </>
              )}
            </div>
          )}

          <div className="history-list">
            {filteredItems.map((item) => (
              <div key={item.id} className={`history-card${compareMode && selectedForCompare.has(item.id) ? " history-card--selected" : ""}`}>
                {compareMode && (
                  <label className="history-compare-checkbox" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selectedForCompare.has(item.id)}
                      onChange={() => handleToggleCompareSelect(item.id)}
                      disabled={!selectedForCompare.has(item.id) && selectedForCompare.size >= 2}
                    />
                  </label>
                )}
                <div
                  className="history-card-content"
                  onClick={() => compareMode ? handleToggleCompareSelect(item.id) : handleCardClick(item.id)}
                >
                  <div className="history-card-top">
                    <span className="history-date">{formatDate(item.created_at)}</span>
                    <span className="history-type-badge">
                      {item.test_type_display}
                    </span>
                    {item.liked && (
                      <span className="history-liked-badge">{"\u2665"}</span>
                    )}
                  </div>
                  {item.filename && (
                    <span className="history-filename">{item.filename}</span>
                  )}
                  <p className="history-summary">{item.summary}</p>
                </div>
                <div className="history-card-actions">
                  <button
                    className={`history-like-action${item.liked ? " history-like-action--active" : ""}`}
                    onClick={() => handleToggleLike(item.id, item.liked)}
                  >
                    {item.liked ? "\u2665 Liked" : "\u2661 Like"}
                  </button>
                  {deletingId === item.id ? (
                    <div className="history-confirm-bar">
                      <span>Delete this record?</span>
                      <button
                        className="history-confirm-yes"
                        onClick={() => handleDelete(item.id)}
                      >
                        Yes
                      </button>
                      <button
                        className="history-confirm-no"
                        onClick={() => setDeletingId(null)}
                      >
                        No
                      </button>
                    </div>
                  ) : (
                    <button
                      className="history-delete-btn"
                      onClick={() => setDeletingId(item.id)}
                    >
                      Delete
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>

          {compareMode && (
            <button
              className="history-compare-btn"
              disabled={selectedForCompare.size !== 2}
              onClick={handleCompare}
            >
              Compare Selected ({selectedForCompare.size}/2)
            </button>
          )}

          {items.length < total && (
            <button
              className="history-load-more"
              onClick={handleLoadMore}
              disabled={loading}
            >
              {loading ? "Loading..." : "Load more"}
            </button>
          )}

          {loading && items.length === 0 && (
            <div className="history-loading">
              <p>Loading history...</p>
            </div>
          )}
        </>
      )}

      {/* Letters Tab */}
      {activeTab === "letters" && (
        <>
          <div className="history-search">
            <input
              type="text"
              className="history-search-input"
              placeholder="Search letters..."
              value={lettersSearch}
              onChange={(e) => handleLettersSearchChange(e.target.value)}
            />
          </div>

          <div className="history-filters">
            <button
              className={`history-filter-btn${lettersLikedOnly ? " history-filter-btn--active" : ""}`}
              onClick={() => {
                setLettersLikedOnly((prev) => !prev);
                setLettersOffset(0);
              }}
            >
              {lettersLikedOnly ? "\u2665 Liked Only" : "\u2661 Liked Only"}
            </button>
          </div>

          {!lettersLoading && letters.length === 0 && (
            <div className="history-empty">
              {lettersSearch ? (
                <p>No results for &ldquo;{lettersSearch}&rdquo;.</p>
              ) : (
                <>
                  <p>No letters yet.</p>
                  <p className="history-empty-hint">
                    Letters will appear here after you generate them.
                  </p>
                </>
              )}
            </div>
          )}

          <div className="history-list">
            {letters.map((letter) => (
              <div key={letter.id} className="history-card">
                <div
                  className="history-card-content"
                  onClick={() => handleLetterClick(letter.id)}
                >
                  <div className="history-card-top">
                    <span className="history-date">{formatDate(letter.created_at)}</span>
                    <span className="history-type-badge">{letter.letter_type}</span>
                    {letter.liked && (
                      <span className="history-liked-badge">{"\u2665"}</span>
                    )}
                  </div>
                  <p className="history-summary">{letter.prompt}</p>
                  {(letter.model_used || letter.input_tokens != null) && (
                    <span className="history-meta-line">
                      {letter.model_used && `${letter.model_used}`}
                      {letter.input_tokens != null &&
                        ` | ${letter.input_tokens} in / ${letter.output_tokens ?? 0} out`}
                    </span>
                  )}
                </div>
                <div className="history-card-actions">
                  <button
                    className={`history-like-action${letter.liked ? " history-like-action--active" : ""}`}
                    onClick={() => handleToggleLetterLike(letter.id, letter.liked)}
                  >
                    {letter.liked ? "\u2665 Liked" : "\u2661 Like"}
                  </button>
                </div>
              </div>
            ))}
          </div>

          {letters.length < lettersTotal && (
            <button
              className="history-load-more"
              onClick={handleLettersLoadMore}
              disabled={lettersLoading}
            >
              {lettersLoading ? "Loading..." : "Load more"}
            </button>
          )}

          {lettersLoading && letters.length === 0 && (
            <div className="history-loading">
              <p>Loading letters...</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
