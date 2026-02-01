import { useState, useRef, useCallback, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { sidecarApi } from "../../services/sidecarApi";
import { useToast } from "../shared/Toast";
import type { ExtractionResult, Template } from "../../types/sidecar";
import "./ImportScreen.css";

type HelpMeStatus = "idle" | "generating" | "success" | "error";

type ImportMode = "pdf" | "text";
type ImportStatus = "idle" | "extracting" | "success" | "error";

interface FileExtractionEntry {
  result?: ExtractionResult;
  error?: string;
  status: "pending" | "extracting" | "success" | "error";
}

function fileKey(file: File): string {
  return `${file.name}::${file.size}`;
}

export function ImportScreen() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [mode, setMode] = useState<ImportMode>("pdf");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [pastedText, setPastedText] = useState("");
  const [status, setStatus] = useState<ImportStatus>("idle");
  const [result, setResult] = useState<ExtractionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<
    number | undefined
  >(undefined);

  // Clinical context state
  const [clinicalContext, setClinicalContext] = useState("");
  const [selectedReasons, setSelectedReasons] = useState<Set<string>>(new Set());
  const [quickReasons, setQuickReasons] = useState<string[]>([]);

  // Help Me state
  const [helpMeText, setHelpMeText] = useState("");
  const [helpMeStatus, setHelpMeStatus] = useState<HelpMeStatus>("idle");

  // Batch extraction state
  const [extractionResults, setExtractionResults] = useState<
    Map<string, FileExtractionEntry>
  >(new Map());
  const [selectedResultKey, setSelectedResultKey] = useState<string | null>(
    null,
  );

  // PHI scrub preview state
  const [scrubbedText, setScrubbedText] = useState<string | null>(null);
  const [scrubbedClinicalContext, setScrubbedClinicalContext] = useState<string | null>(null);
  const [isScrubbing, setIsScrubbing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function loadTemplates(attempts = 5, backoffMs = 1000) {
      for (let i = 0; i < attempts; i++) {
        try {
          const res = await sidecarApi.listTemplates();
          if (!cancelled) setTemplates(res.items);
          return;
        } catch {
          if (i < attempts - 1) {
            await new Promise((r) => setTimeout(r, backoffMs * (i + 1)));
          }
        }
      }
      // Templates are optional — silently fall back to empty list
    }
    async function loadSettings(attempts = 5, backoffMs = 1000) {
      for (let i = 0; i < attempts; i++) {
        try {
          const s = await sidecarApi.getSettings();
          if (!cancelled) setQuickReasons(s.quick_reasons);
          return;
        } catch {
          if (i < attempts - 1) {
            await new Promise((r) => setTimeout(r, backoffMs * (i + 1)));
          }
        }
      }
    }
    loadTemplates();
    loadSettings();
    return () => {
      cancelled = true;
    };
  }, []);

  const resetState = useCallback(() => {
    setStatus("idle");
    setResult(null);
    setError(null);
    setExtractionResults(new Map());
    setSelectedResultKey(null);
    setScrubbedText(null);
    setScrubbedClinicalContext(null);
    // Clear stale results so ResultsScreen doesn't restore a prior analysis.
    try { sessionStorage.removeItem("explify_results_state"); } catch { /* ignore */ }
  }, []);

  // Fetch scrubbed preview when extraction succeeds
  useEffect(() => {
    if (!result) return;
    let cancelled = false;
    setIsScrubbing(true);
    sidecarApi
      .scrubPreview(result.full_text, clinicalContext || undefined)
      .then((res) => {
        if (!cancelled) {
          setScrubbedText(res.scrubbed_text);
          setScrubbedClinicalContext(res.scrubbed_clinical_context);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setScrubbedText(result.full_text);
          setScrubbedClinicalContext(clinicalContext);
        }
      })
      .finally(() => {
        if (!cancelled) setIsScrubbing(false);
      });
    return () => { cancelled = true; };
  }, [result, clinicalContext]);

  const handleModeChange = useCallback(
    (newMode: ImportMode) => {
      setMode(newMode);
      resetState();
    },
    [resetState],
  );

  const validateFile = (file: File): string | null => {
    const name = file.name.toLowerCase();
    const validExts = [".pdf", ".jpg", ".jpeg", ".png", ".txt"];
    const hasValidExt = validExts.some((ext) => name.endsWith(ext));
    if (!hasValidExt) {
      return `"${file.name}": Unsupported file type. Accepted: PDF, JPG, PNG, TXT.`;
    }
    if (file.size === 0) {
      return `"${file.name}": File is empty.`;
    }
    if (file.size > 50 * 1024 * 1024) {
      return `"${file.name}": File is too large. Maximum size is 50 MB.`;
    }
    return null;
  };

  const handleFileSelect = useCallback(
    (files: File[]) => {
      const validFiles: File[] = [];
      const errors: string[] = [];
      for (const file of files) {
        const validationError = validateFile(file);
        if (validationError) {
          errors.push(validationError);
        } else {
          validFiles.push(file);
        }
      }
      if (errors.length > 0) {
        setError(errors.join(" "));
      }
      if (validFiles.length > 0) {
        setSelectedFiles((prev) => {
          const existingKeys = new Set(prev.map(fileKey));
          const newFiles = validFiles.filter(
            (f) => !existingKeys.has(fileKey(f)),
          );
          return [...prev, ...newFiles];
        });
        resetState();
      } else if (validFiles.length === 0 && errors.length > 0) {
        setSelectedFiles([]);
      }
    },
    [resetState],
  );

  const handleRemoveFile = useCallback(
    (index: number) => {
      setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
      resetState();
    },
    [resetState],
  );

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (files && files.length > 0) {
        handleFileSelect(Array.from(files));
      }
    },
    [handleFileSelect],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      const files = Array.from(e.dataTransfer.files);
      if (files.length > 0) {
        handleFileSelect(files);
      }
    },
    [handleFileSelect],
  );

  const handleExtract = useCallback(async () => {
    setStatus("extracting");
    setError(null);
    setResult(null);

    try {
      if (mode === "pdf") {
        if (selectedFiles.length === 0) {
          setError("No files selected.");
          setStatus("error");
          return;
        }

        const results = new Map<string, FileExtractionEntry>();
        // Initialize all as pending
        for (const file of selectedFiles) {
          results.set(fileKey(file), { status: "pending" });
        }
        setExtractionResults(new Map(results));

        let lastSuccessKey: string | null = null;

        for (const file of selectedFiles) {
          const key = fileKey(file);
          results.set(key, { status: "extracting" });
          setExtractionResults(new Map(results));

          try {
            const extractionResult = await sidecarApi.extractFile(file);
            results.set(key, {
              status: "success",
              result: extractionResult,
            });
            lastSuccessKey = key;
          } catch (err) {
            const msg =
              err instanceof Error ? err.message : "Extraction failed.";
            results.set(key, { status: "error", error: msg });
          }
          setExtractionResults(new Map(results));
        }

        // Count successes
        const successes = [...results.values()].filter(
          (e) => e.status === "success",
        );
        if (successes.length === 0) {
          setStatus("error");
          setError("All file extractions failed.");
          return;
        }

        // If single success, auto-select it
        if (successes.length === 1 && lastSuccessKey) {
          setSelectedResultKey(lastSuccessKey);
          setResult(successes[0].result!);
        } else if (lastSuccessKey) {
          setSelectedResultKey(lastSuccessKey);
          setResult(
            results.get(lastSuccessKey)?.result ?? successes[0].result!,
          );
        }

        setStatus("success");
      } else {
        if (!pastedText.trim()) {
          setError("Please enter some text.");
          setStatus("error");
          return;
        }
        const extractionResult = await sidecarApi.extractText(pastedText);
        setResult(extractionResult);
        setStatus("success");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Extraction failed.";
      setError(msg);
      setStatus("error");
      showToast("error", msg);
    }
  }, [mode, selectedFiles, pastedText, showToast]);

  const handleSelectResult = useCallback(
    (key: string) => {
      setSelectedResultKey(key);
      const entry = extractionResults.get(key);
      if (entry?.result) {
        setResult(entry.result);
      }
    },
    [extractionResults],
  );

  const handleProceed = useCallback(() => {
    if (result) {
      navigate("/processing", {
        state: {
          extractionResult: result,
          templateId: selectedTemplateId,
          clinicalContext: clinicalContext.trim() || undefined,
        },
      });
    }
  }, [navigate, result, selectedTemplateId, clinicalContext]);

  const handleHelpMe = useCallback(async () => {
    if (!helpMeText.trim()) return;
    setHelpMeStatus("generating");
    try {
      await sidecarApi.generateLetter({
        prompt: helpMeText.trim(),
        letter_type: "general",
      });
      setHelpMeStatus("success");
      setHelpMeText("");
      showToast("success", "Letter generated.");
      navigate("/letters");
    } catch {
      setHelpMeStatus("error");
      showToast("error", "Failed to generate letter. Check your API key in Settings.");
    }
  }, [helpMeText, showToast]);

  const canExtract =
    status !== "extracting" &&
    ((mode === "pdf" && selectedFiles.length > 0) ||
      (mode === "text" && pastedText.trim().length > 0));

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const successCount = [...extractionResults.values()].filter(
    (e) => e.status === "success",
  ).length;

  return (
    <div className="import-screen">
      <header className="import-header">
        <h2 className="import-title">Import Report</h2>
        <p className="import-description">
          Upload files (PDF, images, text) or paste text from your EMR system.
        </p>
      </header>

      <div className="import-grid">
        {/* Left Column — Clinical Context */}
        <div className="import-left-panel">
          {templates.length > 0 && (
            <div className="import-field">
              <label className="import-field-label">Template</label>
              <span className="import-field-subtitle">Optional</span>
              <select
                className="import-field-select"
                value={selectedTemplateId ?? ""}
                onChange={(e) =>
                  setSelectedTemplateId(
                    e.target.value ? Number(e.target.value) : undefined,
                  )
                }
              >
                <option value="">No template</option>
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                    {t.test_type ? ` (${t.test_type})` : ""}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="import-field">
            <label className="import-field-label import-field-label--bold">
              Clinical Context
            </label>
            <span className="import-field-subtitle">Optional</span>
            {quickReasons.length > 0 && (
              <div className="quick-reasons">
                {quickReasons.map((reason) => (
                  <button
                    key={reason}
                    className={`quick-reason-btn ${selectedReasons.has(reason) ? "quick-reason-btn--active" : ""}`}
                    onClick={() => {
                      setSelectedReasons((prev) => {
                        const next = new Set(prev);
                        if (next.has(reason)) {
                          next.delete(reason);
                        } else {
                          next.add(reason);
                        }
                        setClinicalContext(Array.from(next).join(", "));
                        return next;
                      });
                    }}
                  >
                    {reason}
                  </button>
                ))}
              </div>
            )}
            <textarea
              className="import-field-textarea"
              placeholder="e.g., Chest pain, follow up pericardial effusion, or paste last clinic note text"
              value={clinicalContext}
              onChange={(e) => {
                setClinicalContext(e.target.value);
                setSelectedReasons(new Set());
              }}
              rows={3}
            />
          </div>

          {/* Scrubbed Clinical Context Preview */}
          {status === "success" && scrubbedClinicalContext && clinicalContext.trim() && (
            <div className="import-field">
              <label className="import-field-label">Clinical Context Preview (PHI Scrubbed)</label>
              <div className="scrubbed-preview-box">
                {scrubbedClinicalContext}
              </div>
            </div>
          )}

          {/* Extraction Preview (moved to left column) */}
          {status === "success" && result && (
            <div className="extraction-preview">
              <h3 className="preview-title">Extraction Complete</h3>

              <div className="preview-stats">
                <div className="stat">
                  <span className="stat-label">Pages</span>
                  <span className="stat-value">{result.total_pages}</span>
                </div>
                <div className="stat">
                  <span className="stat-label">Characters</span>
                  <span className="stat-value">
                    {result.total_chars.toLocaleString()}
                  </span>
                </div>
                {result.detection && (
                  <div className="stat">
                    <span className="stat-label">Type</span>
                    <span className="stat-value">
                      {result.detection.overall_type}
                    </span>
                  </div>
                )}
                {result.tables.length > 0 && (
                  <div className="stat">
                    <span className="stat-label">Tables</span>
                    <span className="stat-value">{result.tables.length}</span>
                  </div>
                )}
              </div>

              {result.warnings.length > 0 && (
                <div className="preview-warnings">
                  {result.warnings.map((w, i) => (
                    <p key={i} className="warning-text">
                      {w}
                    </p>
                  ))}
                </div>
              )}

              <div className="preview-text-container">
                {isScrubbing ? (
                  <div className="extraction-progress">
                    <div className="spinner" />
                    <p>Scrubbing PHI...</p>
                  </div>
                ) : (
                  <pre className="preview-text">
                    {scrubbedText ?? result.full_text}
                  </pre>
                )}
              </div>

              <p className="phi-notice">
                No PHI is stored or sent to the AI. All identifiable information is redacted before processing.
              </p>

              <button className="proceed-btn" onClick={handleProceed}>
                Continue to Processing
              </button>
            </div>
          )}
        </div>

        {/* Right Column — Import & Help Me */}
        <div className="import-right-panel">
          <div className="mode-toggle">
            <button
              className={`mode-toggle-btn ${mode === "pdf" ? "mode-toggle-btn--active" : ""}`}
              onClick={() => handleModeChange("pdf")}
            >
              Upload File
            </button>
            <button
              className={`mode-toggle-btn ${mode === "text" ? "mode-toggle-btn--active" : ""}`}
              onClick={() => handleModeChange("text")}
            >
              Paste Text
            </button>
          </div>

          {mode === "pdf" && (
            <div className="input-panel">
              <div
                className={`drop-zone ${isDragOver ? "drop-zone--active" : ""} ${selectedFiles.length > 0 ? "drop-zone--has-file" : ""}`}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.jpg,.jpeg,.png,.txt,application/pdf,image/jpeg,image/png,text/plain"
                  multiple
                  onChange={handleInputChange}
                  className="drop-zone-input"
                />
                {selectedFiles.length > 0 ? (
                  <div className="drop-zone-file-info">
                    <span className="file-name">
                      {selectedFiles.length} file{selectedFiles.length !== 1 ? "s" : ""} selected
                    </span>
                    <span className="file-size">
                      Click or drop to add more
                    </span>
                  </div>
                ) : (
                  <div className="drop-zone-prompt">
                    <p className="drop-zone-primary">
                      Drag and drop files here, or click to browse
                    </p>
                    <p className="drop-zone-secondary">
                      PDF, JPG, PNG, or TXT files up to 50 MB each. Multiple files supported.
                    </p>
                  </div>
                )}
              </div>

              {selectedFiles.length > 0 && (
                <div className="file-list">
                  {selectedFiles.map((file, index) => {
                    const key = fileKey(file);
                    const entry = extractionResults.get(key);
                    return (
                      <div key={key} className="file-list-item">
                        <span className="file-list-name">{file.name}</span>
                        <span className="file-list-size">
                          {formatFileSize(file.size)}
                        </span>
                        {entry && (
                          <span
                            className={`file-list-status file-list-status--${entry.status}`}
                          >
                            {entry.status === "pending" && "Pending"}
                            {entry.status === "extracting" && "Extracting..."}
                            {entry.status === "success" && "Done"}
                            {entry.status === "error" && (entry.error ?? "Failed")}
                          </span>
                        )}
                        <button
                          className="file-list-remove"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleRemoveFile(index);
                          }}
                          aria-label={`Remove ${file.name}`}
                        >
                          &times;
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {mode === "text" && (
            <div className="input-panel">
              <textarea
                className="text-input"
                placeholder="Paste your lab report or diagnostic text here..."
                value={pastedText}
                onChange={(e) => {
                  setPastedText(e.target.value);
                  resetState();
                }}
                rows={12}
              />
              <div className="text-input-footer">
                <span className="char-count">
                  {pastedText.length.toLocaleString()} characters
                </span>
              </div>
            </div>
          )}

          <button
            className="extract-btn"
            onClick={handleExtract}
            disabled={!canExtract}
          >
            {status === "extracting"
              ? "Extracting..."
              : mode === "pdf" && selectedFiles.length > 1
                ? `Extract All (${selectedFiles.length})`
                : "Extract Text"}
          </button>

          {error && (
            <div className="import-error">
              <p>{error}</p>
            </div>
          )}

          {status === "extracting" && (
            <div className="extraction-progress">
              <div className="spinner" />
              <p>Analyzing document{selectedFiles.length > 1 ? "s" : ""}...</p>
            </div>
          )}

          {status === "success" && successCount > 1 && (
            <div className="batch-results-selector">
              <h3 className="preview-title">
                {successCount} files extracted. Select one to process:
              </h3>
              {selectedFiles.map((file) => {
                const key = fileKey(file);
                const entry = extractionResults.get(key);
                if (entry?.status !== "success") return null;
                return (
                  <button
                    key={key}
                    className={`batch-result-item ${selectedResultKey === key ? "batch-result-item--selected" : ""}`}
                    onClick={() => handleSelectResult(key)}
                  >
                    {file.name}
                  </button>
                );
              })}
            </div>
          )}

          {/* Help Me Section */}
          <div className="help-me-section">
            <h3 className="help-me-title">Help Me</h3>
            <p className="help-me-description">
              Need help explaining something to a patient? Describe your question,
              topic, or situation below and we'll generate a clear, patient-friendly
              explanation, letter, or response. Results appear in the Letters section.
            </p>
            <textarea
              className="help-me-input"
              placeholder="e.g., Explain to the patient why their potassium is slightly elevated and what dietary changes might help..."
              value={helpMeText}
              onChange={(e) => {
                setHelpMeText(e.target.value);
                if (helpMeStatus !== "idle") setHelpMeStatus("idle");
              }}
              rows={4}
            />
            <div className="help-me-footer">
              <span className="char-count">
                {helpMeText.length.toLocaleString()} characters
              </span>
              <button
                className="help-me-btn"
                onClick={handleHelpMe}
                disabled={!helpMeText.trim() || helpMeStatus === "generating"}
              >
                {helpMeStatus === "generating" ? "Generating..." : "Generate"}
              </button>
            </div>
            {helpMeStatus === "success" && (
              <p className="help-me-success">
                Letter generated successfully. View it in the Letters section.
              </p>
            )}
            {helpMeStatus === "error" && (
              <p className="help-me-error">
                Failed to generate. Please check your API key in Settings.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
