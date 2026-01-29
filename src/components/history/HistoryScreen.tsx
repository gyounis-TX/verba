import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { sidecarApi } from "../../services/sidecarApi";
import { useToast } from "../shared/Toast";
import type { HistoryListItem } from "../../types/sidecar";
import "./HistoryScreen.css";

export function HistoryScreen() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [items, setItems] = useState<HistoryListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const limit = 20;

  const fetchHistory = useCallback(
    async (searchTerm: string, newOffset: number) => {
      setLoading(true);
      try {
        const res = await sidecarApi.listHistory(
          newOffset,
          limit,
          searchTerm || undefined,
        );
        if (newOffset === 0) {
          setItems(res.items);
        } else {
          setItems((prev) => [...prev, ...res.items]);
        }
        setTotal(res.total);
      } catch {
        showToast("error", "Failed to load history.");
      } finally {
        setLoading(false);
      }
    },
    [showToast],
  );

  useEffect(() => {
    fetchHistory("", 0);
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [fetchHistory]);

  const handleSearchChange = (value: string) => {
    setSearch(value);
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    debounceRef.current = setTimeout(() => {
      setOffset(0);
      fetchHistory(value, 0);
    }, 300);
  };

  const handleLoadMore = () => {
    const newOffset = offset + limit;
    setOffset(newOffset);
    fetchHistory(search, newOffset);
  };

  const handleCardClick = async (id: number) => {
    try {
      const detail = await sidecarApi.getHistoryDetail(id);
      navigate("/results", {
        state: { explainResponse: detail.full_response, fromHistory: true },
      });
    } catch {
      showToast("error", "Failed to load analysis details.");
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await sidecarApi.deleteHistory(id);
      setItems((prev) => prev.filter((item) => item.id !== id));
      setTotal((prev) => prev - 1);
      showToast("success", "Record deleted.");
    } catch {
      showToast("error", "Failed to delete record.");
    } finally {
      setDeletingId(null);
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

  return (
    <div className="history-screen">
      <header className="history-header">
        <h2 className="history-title">Analysis History</h2>
      </header>

      <div className="history-search">
        <input
          type="text"
          className="history-search-input"
          placeholder="Search history..."
          value={search}
          onChange={(e) => handleSearchChange(e.target.value)}
        />
      </div>

      {!loading && items.length === 0 && (
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
        {items.map((item) => (
          <div key={item.id} className="history-card">
            <div
              className="history-card-content"
              onClick={() => handleCardClick(item.id)}
            >
              <div className="history-card-top">
                <span className="history-date">{formatDate(item.created_at)}</span>
                <span className="history-type-badge">
                  {item.test_type_display}
                </span>
              </div>
              {item.filename && (
                <span className="history-filename">{item.filename}</span>
              )}
              <p className="history-summary">{item.summary}</p>
            </div>
            <div className="history-card-actions">
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
    </div>
  );
}
