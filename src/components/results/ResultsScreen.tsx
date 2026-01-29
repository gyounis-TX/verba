import { useEffect, useState, useCallback } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import type {
  ExplainResponse,
  ExtractionResult,
  MeasurementExplanation,
  FindingExplanation,
  ParsedMeasurement,
  LiteracyLevel,
} from "../../types/sidecar";
import { sidecarApi } from "../../services/sidecarApi";
import { useToast } from "../shared/Toast";
import { GlossaryTooltip } from "./GlossaryTooltip";
import "./ResultsScreen.css";

const SEVERITY_LABELS: Record<string, string> = {
  normal: "Normal",
  mildly_abnormal: "Mildly Abnormal",
  moderately_abnormal: "Moderately Abnormal",
  severely_abnormal: "Severely Abnormal",
  undetermined: "Undetermined",
};

const SEVERITY_ICONS: Record<string, string> = {
  normal: "\u2713",
  mildly_abnormal: "\u26A0",
  moderately_abnormal: "\u25B2",
  severely_abnormal: "\u2716",
  undetermined: "\u2014",
};

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

const LITERACY_OPTIONS: { value: LiteracyLevel; label: string }[] = [
  { value: "grade_4", label: "Grade 4" },
  { value: "grade_6", label: "Grade 6" },
  { value: "grade_8", label: "Grade 8" },
  { value: "clinical", label: "Clinical" },
];

function buildCopyText(
  summary: string,
  findings: { finding: string; explanation: string }[],
  questions: string[],
  disclaimer: string,
): string {
  const parts: string[] = [];
  parts.push("SUMMARY");
  parts.push(summary);
  if (findings.length > 0) {
    parts.push("");
    parts.push("KEY FINDINGS");
    for (const f of findings) {
      parts.push(`- ${f.finding}: ${f.explanation}`);
    }
  }
  if (questions.length > 0) {
    parts.push("");
    parts.push("QUESTIONS TO ASK YOUR DOCTOR");
    for (const q of questions) {
      parts.push(`- ${q}`);
    }
  }
  parts.push("");
  parts.push(disclaimer);
  return parts.join("\n");
}

export function ResultsScreen() {
  const location = useLocation();
  const navigate = useNavigate();
  const locationState = location.state as {
    explainResponse?: ExplainResponse;
    fromHistory?: boolean;
    extractionResult?: ExtractionResult;
    clinicalContext?: string;
    templateId?: number;
  } | null;

  const initialResponse = locationState?.explainResponse ?? null;
  const fromHistory = locationState?.fromHistory ?? false;
  const extractionResult = locationState?.extractionResult ?? null;
  const clinicalContext = locationState?.clinicalContext;
  const templateId = locationState?.templateId;

  const { showToast } = useToast();
  const [currentResponse, setCurrentResponse] =
    useState<ExplainResponse | null>(initialResponse);
  const [glossary, setGlossary] = useState<Record<string, string>>({});
  const [isExporting, setIsExporting] = useState(false);

  // Refinement state
  const [selectedLiteracy, setSelectedLiteracy] =
    useState<LiteracyLevel>("grade_6");
  const [isRegenerating, setIsRegenerating] = useState(false);

  // Edit state
  const [isEditing, setIsEditing] = useState(false);
  const [editedSummary, setEditedSummary] = useState("");
  const [editedFindings, setEditedFindings] = useState<
    { finding: string; explanation: string }[]
  >([]);
  const [editedQuestions, setEditedQuestions] = useState<string[]>([]);
  const [isDirty, setIsDirty] = useState(false);

  // Sync edit state when response changes
  useEffect(() => {
    if (!currentResponse) return;
    const expl = currentResponse.explanation;
    setEditedSummary(expl.overall_summary);
    setEditedFindings(
      expl.key_findings.map((f) => ({
        finding: f.finding,
        explanation: f.explanation,
      })),
    );
    setEditedQuestions([...expl.questions_for_doctor]);
    setIsDirty(false);
    setIsEditing(false);
  }, [currentResponse]);

  useEffect(() => {
    if (!currentResponse) return;
    const testType = currentResponse.parsed_report.test_type;
    sidecarApi
      .getGlossary(testType)
      .then((res) => setGlossary(res.glossary))
      .catch(() => {
        showToast("error", "Could not load glossary for tooltips.");
      });
  }, [currentResponse, showToast]);

  const canRefine = !fromHistory && extractionResult != null;

  const handleRegenerate = useCallback(async () => {
    if (!extractionResult) return;
    setIsRegenerating(true);
    try {
      const response = await sidecarApi.explainReport({
        extraction_result: extractionResult,
        test_type: currentResponse?.parsed_report.test_type,
        literacy_level: selectedLiteracy,
        clinical_context: clinicalContext,
        template_id: templateId,
      });
      setCurrentResponse(response);
      showToast("success", "Explanation regenerated.");
    } catch {
      showToast("error", "Failed to regenerate explanation.");
    } finally {
      setIsRegenerating(false);
    }
  }, [extractionResult, currentResponse, selectedLiteracy, clinicalContext, templateId, showToast]);

  const handleExportPdf = useCallback(async () => {
    if (!currentResponse) return;
    setIsExporting(true);
    try {
      const blob = await sidecarApi.exportPdf(currentResponse);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "verba-report.pdf";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      showToast("success", "PDF exported successfully.");
    } catch {
      showToast("error", "Failed to export PDF.");
    } finally {
      setIsExporting(false);
    }
  }, [currentResponse, showToast]);

  const handleCopy = useCallback(async () => {
    if (!currentResponse) return;
    const expl = currentResponse.explanation;
    const summary = isDirty ? editedSummary : expl.overall_summary;
    const findings = isDirty ? editedFindings : expl.key_findings;
    const questions = isDirty ? editedQuestions : expl.questions_for_doctor;
    const text = buildCopyText(summary, findings, questions, expl.disclaimer);
    try {
      await navigator.clipboard.writeText(text);
      showToast("success", "Copied to clipboard.");
      // Future: capture learning event
    } catch {
      showToast("error", "Failed to copy to clipboard.");
    }
  }, [
    currentResponse,
    isDirty,
    editedSummary,
    editedFindings,
    editedQuestions,
    showToast,
  ]);

  const markDirty = () => {
    if (!isDirty) setIsDirty(true);
  };

  if (!currentResponse) {
    return (
      <div className="results-screen">
        <h2 className="results-title">No Results</h2>
        <p className="results-empty">
          No analysis results found. Please import and process a report
          first.
        </p>
        <button
          className="results-back-btn"
          onClick={() => navigate("/")}
        >
          Back to Import
        </button>
      </div>
    );
  }

  const { explanation, parsed_report } = currentResponse;
  const displaySummary = isDirty ? editedSummary : explanation.overall_summary;
  const displayFindings = isDirty
    ? editedFindings.map((f, i) => ({
        ...(explanation.key_findings[i] ?? { severity: "informational" }),
        finding: f.finding,
        explanation: f.explanation,
      }))
    : explanation.key_findings;
  const displayQuestions = isDirty
    ? editedQuestions
    : explanation.questions_for_doctor;

  const measurementMap = new Map<string, ParsedMeasurement>();
  if (parsed_report.measurements) {
    for (const m of parsed_report.measurements) {
      measurementMap.set(m.abbreviation, m);
    }
  }

  return (
    <div className="results-screen">
      <header className="results-header">
        <h2 className="results-title">Report Explanation</h2>
        <span className="results-test-type">
          {parsed_report.test_type_display}
        </span>
        {fromHistory && (
          <span className="results-from-history">Viewed from history</span>
        )}
      </header>

      {/* Export Toolbar */}
      <div className="export-toolbar">
        <button
          className="export-btn"
          onClick={handleExportPdf}
          disabled={isExporting}
        >
          {isExporting ? "Exporting\u2026" : "Export PDF"}
        </button>
        <button className="export-btn" onClick={() => window.print()}>
          Print
        </button>
        <button className="export-btn" onClick={handleCopy}>
          Copy Explanation
        </button>
      </div>

      {/* Refine Toolbar */}
      {canRefine && (
        <div className="refine-toolbar">
          <label className="refine-label">
            Literacy:
            <select
              className="refine-select"
              value={selectedLiteracy}
              onChange={(e) =>
                setSelectedLiteracy(e.target.value as LiteracyLevel)
              }
            >
              {LITERACY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
          <button
            className="refine-btn"
            onClick={handleRegenerate}
            disabled={isRegenerating}
          >
            {isRegenerating ? "Regenerating\u2026" : "Regenerate"}
          </button>
          <button
            className={`edit-toggle-btn ${isEditing ? "edit-toggle-btn--active" : ""}`}
            onClick={() => setIsEditing(!isEditing)}
          >
            {isEditing ? "Stop Editing" : "Edit Text"}
          </button>
          {isDirty && <span className="edit-indicator">Edited</span>}
        </div>
      )}

      {/* Overall Summary */}
      <section className="results-section">
        <h3 className="section-heading">Summary</h3>
        {isEditing ? (
          <textarea
            className="summary-textarea"
            value={editedSummary}
            onChange={(e) => {
              setEditedSummary(e.target.value);
              markDirty();
            }}
            rows={6}
          />
        ) : (
          <p className="summary-text">
            <GlossaryTooltip text={displaySummary} glossary={glossary} />
          </p>
        )}
      </section>

      {/* Key Findings */}
      {displayFindings.length > 0 && (
        <details open className="results-section results-collapsible">
          <summary className="section-heading">
            Key Findings
            <span className="section-count">
              {displayFindings.length}
            </span>
          </summary>
          <div className="section-body">
            <div className="findings-list">
              {displayFindings.map(
                (f: FindingExplanation, i: number) => (
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
                            onChange={(e) => {
                              const updated = [...editedFindings];
                              updated[i] = {
                                ...updated[i],
                                finding: e.target.value,
                              };
                              setEditedFindings(updated);
                              markDirty();
                            }}
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
                        value={
                          editedFindings[i]?.explanation ?? f.explanation
                        }
                        onChange={(e) => {
                          const updated = [...editedFindings];
                          updated[i] = {
                            ...updated[i],
                            explanation: e.target.value,
                          };
                          setEditedFindings(updated);
                          markDirty();
                        }}
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
                ),
              )}
            </div>
          </div>
        </details>
      )}

      {/* Measurements Table */}
      {explanation.measurements.length > 0 && (
        <details open className="results-section results-collapsible">
          <summary className="section-heading">
            Measurements
            <span className="section-count">
              {explanation.measurements.length}
            </span>
          </summary>
          <div className="section-body">
            <div className="measurements-table-container">
              <table
                className="measurements-table"
                aria-label="Measurement results"
              >
                <thead>
                  <tr>
                    <th scope="col">Measurement</th>
                    <th scope="col">Value</th>
                    <th scope="col">Normal Range</th>
                    <th scope="col">Status</th>
                    <th scope="col">Explanation</th>
                  </tr>
                </thead>
                <tbody>
                  {explanation.measurements.map(
                    (m: MeasurementExplanation, i: number) => {
                      const parsed = measurementMap.get(m.abbreviation);
                      return (
                        <tr
                          key={i}
                          className={`measurement-row measurement-row--${m.status}`}
                        >
                          <td className="measurement-name">
                            <GlossaryTooltip
                              text={m.abbreviation}
                              glossary={glossary}
                            />
                          </td>
                          <td className="measurement-value">
                            {m.value} {m.unit}
                          </td>
                          <td className="measurement-range">
                            {parsed?.reference_range || "--"}
                          </td>
                          <td className="measurement-status">
                            <span
                              className={`status-badge status-badge--${m.status}`}
                              aria-label={`Status: ${SEVERITY_LABELS[m.status] || m.status}`}
                            >
                              <span className="status-badge__icon">
                                {SEVERITY_ICONS[m.status] || ""}
                              </span>{" "}
                              {SEVERITY_LABELS[m.status] || m.status}
                            </span>
                          </td>
                          <td className="measurement-explanation">
                            <GlossaryTooltip
                              text={m.plain_language}
                              glossary={glossary}
                            />
                          </td>
                        </tr>
                      );
                    },
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </details>
      )}

      {/* Questions for Doctor */}
      {displayQuestions.length > 0 && (
        <details open className="results-section results-collapsible">
          <summary className="section-heading">
            Questions to Ask Your Doctor
            <span className="section-count">
              {displayQuestions.length}
            </span>
          </summary>
          <div className="section-body">
            <ul className="questions-list">
              {displayQuestions.map((q: string, i: number) => (
                <li key={i} className="question-item">
                  {isEditing ? (
                    <input
                      className="question-edit-input"
                      value={editedQuestions[i] ?? q}
                      onChange={(e) => {
                        const updated = [...editedQuestions];
                        updated[i] = e.target.value;
                        setEditedQuestions(updated);
                        markDirty();
                      }}
                    />
                  ) : (
                    q
                  )}
                </li>
              ))}
            </ul>
          </div>
        </details>
      )}

      {/* Disclaimer */}
      <section className="results-disclaimer">
        <p>{explanation.disclaimer}</p>
      </section>

      {/* Metadata */}
      <footer className="results-footer">
        <span className="results-meta">
          Model: {currentResponse.model_used} | Tokens:{" "}
          {currentResponse.input_tokens} in /{" "}
          {currentResponse.output_tokens} out
        </span>
        {currentResponse.validation_warnings.length > 0 && (
          <details className="validation-warnings">
            <summary>
              Validation Warnings (
              {currentResponse.validation_warnings.length})
            </summary>
            <ul>
              {currentResponse.validation_warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </details>
        )}
      </footer>

      <button
        className="results-back-btn"
        onClick={() => {
          if (isDirty && !window.confirm("You have unsaved edits. Leave anyway?")) {
            return;
          }
          navigate("/");
        }}
      >
        Analyze Another Report
      </button>
    </div>
  );
}
