import type { FindingExplanation } from "../../types/sidecar";
import { GlossaryTooltip } from "./GlossaryTooltip";

const FINDING_SEVERITY_COLORS: Record<string, string> = {
  normal: "var(--color-accent-600)",
  mild: "#d97706",
  moderate: "#ea580c",
  severe: "#dc2626",
  informational: "var(--color-primary-600)",
};

const FINDING_SEVERITY_ICONS: Record<string, string> = {
  normal: "\u2713",
  mild: "\u26A0",
  moderate: "\u25B2",
  severe: "\u2716",
  informational: "\u24D8",
};

interface KeyFindingsPanelProps {
  findings: FindingExplanation[];
  isEditing: boolean;
  editedFindings: { finding: string; explanation: string }[];
  onEditFinding: (index: number, field: "finding" | "explanation", value: string) => void;
  glossary: Record<string, string>;
}

export function KeyFindingsPanel({
  findings,
  isEditing,
  editedFindings,
  onEditFinding,
  glossary,
}: KeyFindingsPanelProps) {
  if (findings.length === 0) return null;

  return (
    <details open className="results-section results-collapsible">
      <summary className="section-heading">
        Key Findings
        <span className="section-count">{findings.length}</span>
      </summary>
      <div className="section-body">
        <div className="findings-list">
          {findings.map((f: FindingExplanation, i: number) => (
            <div key={i} className="finding-card">
              <div className="finding-header">
                <span
                  className={`finding-severity finding-severity--${f.severity}`}
                  aria-label={`Severity: ${f.severity}`}
                  style={{
                    backgroundColor:
                      FINDING_SEVERITY_COLORS[f.severity] ||
                      "var(--color-gray-400)",
                  }}
                >
                  {FINDING_SEVERITY_ICONS[f.severity] || "\u2014"}
                </span>
                <span className="finding-title">
                  {isEditing ? (
                    <input
                      className="finding-edit-input"
                      value={editedFindings[i]?.finding ?? f.finding}
                      onChange={(e) => onEditFinding(i, "finding", e.target.value)}
                    />
                  ) : (
                    <GlossaryTooltip
                      text={f.finding}
                      glossary={glossary}
                    />
                  )}
                </span>
              </div>
              {isEditing ? (
                <textarea
                  className="finding-edit-textarea"
                  autoComplete="off"
                  value={editedFindings[i]?.explanation ?? f.explanation}
                  onChange={(e) => onEditFinding(i, "explanation", e.target.value)}
                  rows={3}
                />
              ) : (
                <p className="finding-explanation">
                  <GlossaryTooltip
                    text={f.explanation}
                    glossary={glossary}
                  />
                </p>
              )}
            </div>
          ))}
        </div>
      </div>
    </details>
  );
}
