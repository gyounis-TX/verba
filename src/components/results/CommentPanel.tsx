import { useState } from "react";

interface CommentPanelProps {
  commentMode: "long" | "short" | "sms";
  setCommentMode: (mode: "long" | "short" | "sms") => void;
  isEditing: boolean;
  editedSummary: string;
  setEditedSummary: (value: string) => void;
  onMarkDirty: () => void;
  commentPreviewText: string;
  isGeneratingComment: boolean;
  isGeneratingLong: boolean;
  isGeneratingSms: boolean;
  onCopy: () => void;
  onExportPdf: () => void;
  isExporting: boolean;
  isLiked: boolean;
  onToggleLike: () => void;
  smsEnabled: boolean;
  testTypeDisplay?: string;
  onChangeType?: () => void;
  qualityRating?: number | null;
  onRate?: (rating: number, note?: string) => void;
}

export function CommentPanel({
  commentMode,
  setCommentMode,
  isEditing,
  editedSummary,
  setEditedSummary,
  onMarkDirty,
  commentPreviewText,
  isGeneratingComment,
  isGeneratingLong,
  isGeneratingSms,
  onCopy,
  onExportPdf,
  isExporting,
  isLiked,
  onToggleLike,
  smsEnabled,
  testTypeDisplay,
  onChangeType,
  qualityRating,
  onRate,
}: CommentPanelProps) {
  const [hoverRating, setHoverRating] = useState(0);
  const [showFeedbackInput, setShowFeedbackInput] = useState(false);
  const [feedbackNote, setFeedbackNote] = useState("");
  const [pendingRating, setPendingRating] = useState(0);

  const handleStarClick = (star: number) => {
    if (star <= 3) {
      setPendingRating(star);
      setShowFeedbackInput(true);
    } else {
      onRate?.(star);
      setShowFeedbackInput(false);
    }
  };

  const submitFeedback = () => {
    onRate?.(pendingRating, feedbackNote || undefined);
    setShowFeedbackInput(false);
    setFeedbackNote("");
    setPendingRating(0);
  };

  const isLoading =
    (isGeneratingComment && commentMode === "short") ||
    (isGeneratingLong && commentMode === "long") ||
    (isGeneratingSms && commentMode === "sms");

  return (
    <div className="results-comment-panel">
      <div className="comment-panel-header">
        <h3>Result Comment</h3>
        <div className="comment-panel-actions">
          <button
            className={`like-btn${isLiked ? " like-btn--active" : ""}`}
            onClick={onToggleLike}
          >
            {isLiked ? "\u2665 Liked" : "\u2661 Like"}
          </button>
          {onRate && (
            <div className="star-rating" onMouseLeave={() => setHoverRating(0)}>
              {[1, 2, 3, 4, 5].map((star) => (
                <button
                  key={star}
                  className={`star-btn${(hoverRating || pendingRating || qualityRating || 0) >= star ? " star-btn--filled" : ""}`}
                  onMouseEnter={() => setHoverRating(star)}
                  onClick={() => handleStarClick(star)}
                  title={`Rate ${star}/5`}
                >
                  {(hoverRating || pendingRating || qualityRating || 0) >= star ? "\u2605" : "\u2606"}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
      {showFeedbackInput && (
        <div className="feedback-input-row">
          <input
            className="feedback-input"
            type="text"
            autoComplete="off"
            placeholder="What could be improved?"
            value={feedbackNote}
            onChange={(e) => setFeedbackNote(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submitFeedback()}
            autoFocus
          />
          <button className="feedback-submit-btn" onClick={submitFeedback}>
            Submit
          </button>
          <button
            className="feedback-cancel-btn"
            onClick={() => { setShowFeedbackInput(false); setPendingRating(0); }}
          >
            Skip
          </button>
        </div>
      )}
      <div className="comment-type-toggle">
        <button
          className={`comment-type-btn${commentMode === "short" ? " comment-type-btn--active" : ""}`}
          onClick={() => setCommentMode("short")}
        >
          Short Comment
        </button>
        <button
          className={`comment-type-btn${commentMode === "long" ? " comment-type-btn--active" : ""}`}
          onClick={() => setCommentMode("long")}
        >
          Long Comment
        </button>
        {smsEnabled && (
          <button
            className={`comment-type-btn${commentMode === "sms" ? " comment-type-btn--active" : ""}`}
            onClick={() => setCommentMode("sms")}
          >
            SMS
          </button>
        )}
      </div>
      {isEditing && (
        <textarea
          className="summary-textarea"
          autoComplete="off"
          value={editedSummary}
          onChange={(e) => {
            setEditedSummary(e.target.value);
            onMarkDirty();
          }}
          rows={6}
        />
      )}
      {isLoading ? (
        <div className="comment-generating">
          {commentMode === "sms"
            ? "Generating SMS summary..."
            : commentMode === "short"
              ? "Generating short comment..."
              : "Generating detailed explanation..."}
        </div>
      ) : (
        <div className="comment-preview">{commentPreviewText}</div>
      )}
      <span className="comment-char-count">{commentPreviewText.length} chars</span>
      {testTypeDisplay && (
        <div className="comment-test-type">
          <span className="comment-test-type-label">Identified as:</span>{" "}
          <span className="comment-test-type-value">{testTypeDisplay}</span>
          {onChangeType && (
            <button className="comment-change-type-btn" onClick={onChangeType}>
              Change
            </button>
          )}
        </div>
      )}
      <button className="comment-copy-btn" onClick={onCopy}>
        Copy to Clipboard
      </button>
      <div className="comment-export-row">
        <button
          className="comment-export-btn"
          onClick={onExportPdf}
          disabled={isExporting}
        >
          {isExporting ? "Exporting\u2026" : "Export PDF"}
        </button>
        <button className="comment-export-btn" onClick={() => window.print()}>
          Print
        </button>
      </div>
    </div>
  );
}
