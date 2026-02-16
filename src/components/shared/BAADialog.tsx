import { useState, useEffect, useRef, useCallback } from "react";
import "./BAADialog.css";

interface BAADialogProps {
  onAccept: () => void;
  onDecline: () => void;
}

/** Minimal markdown to HTML (same approach as LegalPage). */
function renderMarkdown(md: string): string {
  const lines = md.split("\n");
  const html: string[] = [];
  let inList = false;

  for (const raw of lines) {
    const line = raw.trimEnd();

    if (line.startsWith("### ")) {
      if (inList) { html.push("</ul>"); inList = false; }
      html.push(`<h4>${inline(line.slice(4))}</h4>`);
      continue;
    }
    if (line.startsWith("## ")) {
      if (inList) { html.push("</ul>"); inList = false; }
      html.push(`<h3>${inline(line.slice(3))}</h3>`);
      continue;
    }
    if (line.startsWith("# ")) {
      if (inList) { html.push("</ul>"); inList = false; }
      html.push(`<h2>${inline(line.slice(2))}</h2>`);
      continue;
    }

    if (/^[-*] /.test(line)) {
      if (!inList) { html.push("<ul>"); inList = true; }
      html.push(`<li>${inline(line.slice(2))}</li>`);
      continue;
    }

    if (inList) { html.push("</ul>"); inList = false; }

    if (!line.trim()) continue;

    html.push(`<p>${inline(line)}</p>`);
  }

  if (inList) html.push("</ul>");
  return html.join("\n");
}

function inline(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, "<code>$1</code>")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
}

export function BAADialog({ onAccept, onDecline }: BAADialogProps) {
  const [html, setHtml] = useState("");
  const [loading, setLoading] = useState(true);
  const [scrolledToBottom, setScrolledToBottom] = useState(false);
  const [checked, setChecked] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch("/legal/baa.md")
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load BAA");
        return res.text();
      })
      .then((md) => {
        setHtml(renderMarkdown(md));
        setLoading(false);
      })
      .catch(() => {
        setHtml("<p>Failed to load the Business Associate Agreement. Please try again later.</p>");
        setLoading(false);
      });
  }, []);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    // Consider "scrolled to bottom" when within 30px of the end
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 30;
    if (atBottom) setScrolledToBottom(true);
  }, []);

  // Check if content is short enough to not need scrolling
  useEffect(() => {
    if (!html || loading) return;
    // Small delay to let the DOM render
    const timer = setTimeout(() => {
      const el = scrollRef.current;
      if (!el) return;
      if (el.scrollHeight <= el.clientHeight + 30) {
        setScrolledToBottom(true);
      }
    }, 100);
    return () => clearTimeout(timer);
  }, [html, loading]);

  const canAccept = scrolledToBottom && checked;

  return (
    <div className="baa-overlay" role="dialog" aria-modal="true" aria-labelledby="baa-title">
      <div className="baa-card">
        <h2 className="baa-title" id="baa-title">Business Associate Agreement</h2>
        <div
          className="baa-scroll"
          ref={scrollRef}
          onScroll={handleScroll}
        >
          {loading ? (
            <p>Loading...</p>
          ) : (
            <div dangerouslySetInnerHTML={{ __html: html }} />
          )}
        </div>
        <div className="baa-checkbox-row">
          <input
            type="checkbox"
            id="baa-agree"
            checked={checked}
            onChange={(e) => setChecked(e.target.checked)}
            disabled={!scrolledToBottom}
          />
          <label htmlFor="baa-agree">
            I have read and agree to the Business Associate Agreement
          </label>
        </div>
        <div className="baa-actions">
          <button
            className="baa-accept-btn"
            onClick={onAccept}
            disabled={!canAccept}
          >
            I Accept
          </button>
          <button className="baa-decline-btn" onClick={onDecline}>
            Decline
          </button>
        </div>
      </div>
    </div>
  );
}
