import { useState, useRef, useCallback, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { sidecarApi } from "../../services/sidecarApi";
import { useToast } from "../shared/Toast";
import type { ExtractionResult, Template, SharedTemplate, DetectTypeResponse, TestTypeInfo } from "../../types/sidecar";
import "./ImportScreen.css";

type ImportMode = "pdf" | "text";
type ImportStatus = "idle" | "extracting" | "success" | "error";
type DetectionStatus = "idle" | "detecting" | "success" | "low_confidence" | "failed" | "error";

interface FileExtractionEntry {
  result?: ExtractionResult;
  error?: string;
  status: "pending" | "extracting" | "success" | "error";
}

function fileKey(file: File): string {
  return `${file.name}::${file.size}`;
}

// Module-level cache — survives component unmount during navigation.
// Cleared when the user processes or purges the import.
interface ImportStateCache {
  mode: ImportMode;
  selectedFiles: File[];
  pastedText: string;
  status: ImportStatus;
  result: ExtractionResult | null;
  error: string | null;
  extractionResults: Map<string, FileExtractionEntry>;
  selectedResultKey: string | null;
  clinicalContext: string;
  selectedReasons: Set<string>;
  selectedTemplateValue: string;
  scrubbedText: string | null;
  scrubbedClinicalContext: string | null;
  testTypeHint: string;
  detectionStatus: DetectionStatus;
  detectionResult: DetectTypeResponse | null;
  manualTestType: string | null;
}

function freshCache(): ImportStateCache {
  return {
    mode: "text",
    selectedFiles: [],
    pastedText: "",
    status: "idle",
    result: null,
    error: null,
    extractionResults: new Map(),
    selectedResultKey: null,
    clinicalContext: "",
    selectedReasons: new Set(),
    selectedTemplateValue: "",
    scrubbedText: null,
    scrubbedClinicalContext: null,
    testTypeHint: "",
    detectionStatus: "idle",
    detectionResult: null,
    manualTestType: null,
  };
}

let _cache: ImportStateCache = freshCache();

const CATEGORY_LABELS: Record<string, string> = {
  cardiac: "Cardiac",
  vascular: "Vascular",
  lab: "Laboratory",
  imaging_ct: "CT Scans",
  imaging_mri: "MRI",
  imaging_ultrasound: "Ultrasound",
  imaging_xray: "X-Ray / Radiography",
  pulmonary: "Pulmonary",
  neurophysiology: "Neurophysiology",
  endoscopy: "Endoscopy",
  pathology: "Pathology",
};

const CATEGORY_ORDER = [
  "cardiac", "vascular", "lab",
  "imaging_ct", "imaging_mri", "imaging_ultrasound", "imaging_xray",
  "pulmonary", "neurophysiology", "endoscopy", "pathology",
];

function groupTypesByCategory(types: TestTypeInfo[]): [string, TestTypeInfo[]][] {
  const groups = new Map<string, TestTypeInfo[]>();
  for (const t of types) {
    const cat = t.category ?? "other";
    if (!groups.has(cat)) groups.set(cat, []);
    groups.get(cat)!.push(t);
  }
  const result: [string, TestTypeInfo[]][] = [];
  for (const cat of CATEGORY_ORDER) {
    const items = groups.get(cat);
    if (items) {
      result.push([CATEGORY_LABELS[cat] ?? cat, items]);
      groups.delete(cat);
    }
  }
  // Append any remaining categories not in the predefined order
  for (const [cat, items] of groups) {
    const label = CATEGORY_LABELS[cat] ?? cat.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
    result.push([label, items]);
  }
  return result;
}

export function ImportScreen() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [selectedFiles, setSelectedFiles] = useState<File[]>(_cache.selectedFiles);
  const mode: ImportMode = selectedFiles.length > 0 ? "pdf" : "text";
  const [pastedText, setPastedText] = useState(_cache.pastedText);
  const [status, setStatus] = useState<ImportStatus>(_cache.status);
  const [result, setResult] = useState<ExtractionResult | null>(_cache.result);
  const [error, setError] = useState<string | null>(_cache.error);
  const [isDragOver, setIsDragOver] = useState(false);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [sharedTemplates, setSharedTemplates] = useState<SharedTemplate[]>([]);
  const [selectedTemplateValue, setSelectedTemplateValue] = useState(
    _cache.selectedTemplateValue,
  );

  // Clinical context state
  const [clinicalContext, setClinicalContext] = useState(_cache.clinicalContext);
  const [selectedReasons, setSelectedReasons] = useState<Set<string>>(_cache.selectedReasons);
  const [quickReasons, setQuickReasons] = useState<string[]>([]);

  // Batch extraction state
  const [extractionResults, setExtractionResults] = useState<
    Map<string, FileExtractionEntry>
  >(_cache.extractionResults);
  const [selectedResultKey, setSelectedResultKey] = useState<string | null>(
    _cache.selectedResultKey,
  );

  // PHI scrub preview state
  const [scrubbedText, setScrubbedText] = useState<string | null>(_cache.scrubbedText);
  const [scrubbedClinicalContext, setScrubbedClinicalContext] = useState<string | null>(_cache.scrubbedClinicalContext);
  const [isScrubbing, setIsScrubbing] = useState(false);

  // Test type detection state
  const [testTypeHint, setTestTypeHint] = useState(_cache.testTypeHint);
  const [detectionStatus, setDetectionStatus] = useState<DetectionStatus>(_cache.detectionStatus);
  const [detectionResult, setDetectionResult] = useState<DetectTypeResponse | null>(_cache.detectionResult);
  const [manualTestType, setManualTestType] = useState<string | null>(_cache.manualTestType);

  // Sync component state → module-level cache so it survives navigation
  useEffect(() => {
    _cache = {
      mode, selectedFiles, pastedText, status, result, error,
      extractionResults, selectedResultKey, clinicalContext,
      selectedReasons, selectedTemplateValue, scrubbedText,
      scrubbedClinicalContext, testTypeHint, detectionStatus,
      detectionResult, manualTestType,
    };
  });

  useEffect(() => {
    let cancelled = false;
    async function loadTemplates(attempts = 5, backoffMs = 1000) {
      for (let i = 0; i < attempts; i++) {
        try {
          const [res, shared] = await Promise.all([
            sidecarApi.listTemplates(),
            sidecarApi.listSharedTemplates().catch(() => [] as SharedTemplate[]),
          ]);
          if (!cancelled) {
            setTemplates(res.items);
            setSharedTemplates(shared);
          }
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
    setDetectionStatus("idle");
    setDetectionResult(null);
    setManualTestType(null);
    _cache = freshCache();
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

  // Auto-detect test type when extraction succeeds
  useEffect(() => {
    if (!result) return;
    let cancelled = false;
    setDetectionStatus("detecting");
    setManualTestType(null);
    sidecarApi
      .detectTestType(result, testTypeHint || undefined)
      .then((res) => {
        if (cancelled) return;
        setDetectionResult(res);
        if (res.confidence >= 0.4 && res.test_type != null) {
          setDetectionStatus("success");
        } else if (res.confidence > 0 && res.test_type != null) {
          setDetectionStatus("low_confidence");
        } else {
          setDetectionStatus("failed");
        }
      })
      .catch(() => {
        if (!cancelled) setDetectionStatus("error");
      });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result]);

  const handleRedetect = useCallback(() => {
    if (!result) return;
    setDetectionStatus("detecting");
    setManualTestType(null);
    sidecarApi
      .detectTestType(result, testTypeHint || undefined)
      .then((res) => {
        setDetectionResult(res);
        if (res.confidence >= 0.4 && res.test_type != null) {
          setDetectionStatus("success");
        } else if (res.confidence > 0 && res.test_type != null) {
          setDetectionStatus("low_confidence");
        } else {
          setDetectionStatus("failed");
        }
      })
      .catch(() => {
        setDetectionStatus("error");
      });
  }, [result, testTypeHint]);

  const resolvedTestType =
    (manualTestType != null && manualTestType.trim() !== "" ? manualTestType.trim() : null) ??
    (testTypeHint.trim() || null) ??
    (detectionStatus === "success" ? detectionResult?.test_type ?? undefined : undefined);

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
      if (files.length === 0) return;
      // Only allow a single file
      const file = files[0];
      const validationError = validateFile(file);
      if (validationError) {
        setError(validationError);
        setSelectedFiles([]);
      } else {
        setError(null);
        setSelectedFiles([file]);
        setPastedText("");
        resetState();
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
    const currentTarget = e.currentTarget as HTMLElement;
    const relatedTarget = e.relatedTarget as Node | null;
    if (!relatedTarget || !currentTarget.contains(relatedTarget)) {
      setIsDragOver(false);
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      const files = Array.from(e.dataTransfer.files);
      if (files.length > 0) {
        handleFileSelect([files[0]]);
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

        // Classify the input
        const classification = await sidecarApi.classifyInput(pastedText);

        if (classification.classification === "question") {
          // Generate a letter and navigate to results in letter mode
          const letter = await sidecarApi.generateLetter({
            prompt: pastedText.trim(),
            letter_type: "general",
          });
          _cache = freshCache();
          navigate("/results", {
            state: {
              letterMode: true,
              letterId: letter.id,
              letterContent: letter.content,
              letterPrompt: pastedText.trim(),
            },
          });
          return;
        }

        // It's a report — extract as before
        const extractionResult = await sidecarApi.extractText(pastedText);
        setResult(extractionResult);
        setStatus("success");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Analysis failed.";
      setError(msg);
      setStatus("error");
      showToast("error", msg);
    }
  }, [mode, selectedFiles, pastedText, showToast, navigate]);

  const handleProceed = useCallback(() => {
    if (result && resolvedTestType) {
      _cache = freshCache();
      const state: Record<string, unknown> = {
        extractionResult: result,
        clinicalContext: clinicalContext.trim() || undefined,
        testType: resolvedTestType,
      };
      if (selectedTemplateValue.startsWith("own:")) {
        state.templateId = Number(selectedTemplateValue.slice(4));
      } else if (selectedTemplateValue.startsWith("shared:")) {
        state.sharedTemplateSyncId = selectedTemplateValue.slice(7);
      }
      navigate("/processing", { state });
    }
  }, [navigate, result, selectedTemplateValue, clinicalContext, resolvedTestType]);

  const canExtract =
    status !== "extracting" &&
    (selectedFiles.length > 0 || pastedText.trim().length > 0);

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="import-screen">
      <header className="import-header">
        <h2 className="import-title">Import</h2>
        <p className="import-description">
          Upload files (PDF, images, text), paste results from EHR, or ask a question.
        </p>
      </header>

      <div className="import-grid">
        {/* Left Column — Input */}
        <div className="import-left-panel">
          <div
            className={`input-panel unified-input${isDragOver ? " unified-input--drag-over" : ""}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,.txt,application/pdf,image/jpeg,image/png,text/plain"
              onChange={handleInputChange}
              className="drop-zone-input"
            />
            {selectedFiles.length > 0 ? (
              <div className="unified-file-display">
                <div className="file-list-item">
                  <span className="file-list-name">{selectedFiles[0].name}</span>
                  <span className="file-list-size">
                    {formatFileSize(selectedFiles[0].size)}
                  </span>
                  {(() => {
                    const entry = extractionResults.get(fileKey(selectedFiles[0]));
                    return entry ? (
                      <span className={`file-list-status file-list-status--${entry.status}`}>
                        {entry.status === "pending" && "Pending"}
                        {entry.status === "extracting" && "Extracting..."}
                        {entry.status === "success" && "Done"}
                        {entry.status === "error" && (entry.error ?? "Failed")}
                      </span>
                    ) : null;
                  })()}
                  <button
                    className="file-list-remove"
                    onClick={() => handleRemoveFile(0)}
                    aria-label={`Remove ${selectedFiles[0].name}`}
                  >
                    &times;
                  </button>
                </div>
                <p className="unified-file-hint">Drop a different file to replace</p>
              </div>
            ) : (
              <>
                <textarea
                  className="text-input"
                  placeholder={"\u2022 Paste a test result\n\u2022 Drag and drop a PDF, JPG, PNG, or TXT file (up to 50 MB)\n\u2022 Ask for help explaining a question, topic, or situation to a patient"}
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
                  <button
                    type="button"
                    className="browse-file-btn"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    or browse files
                  </button>
                </div>
              </>
            )}
          </div>

          <button
            className="extract-btn"
            onClick={handleExtract}
            disabled={!canExtract}
          >
            {status === "extracting" ? "Analyzing..." : "Analyze"}
          </button>

          {error && (
            <div className="import-error">
              <p>{error}</p>
            </div>
          )}

          {status === "extracting" && (
            <div className="extraction-progress">
              <div className="spinner" />
              <p>Analyzing document...</p>
            </div>
          )}

          {/* Extraction Preview */}
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

              {/* Detection Status */}
              <div className="detection-status">
                {detectionStatus === "detecting" && (
                  <div className="detection-detecting">
                    <div className="spinner" />
                    <span>Detecting report type...</span>
                  </div>
                )}
                {detectionStatus === "success" && detectionResult && (
                  <div className="detection-success">
                    {manualTestType == null ? (
                      <>
                        <span className="detection-badge--success">
                          {detectionResult.available_types.find(
                            (t) => t.test_type_id === detectionResult.test_type,
                          )?.display_name ?? detectionResult.test_type}
                        </span>
                        <span className="detection-confidence">
                          {Math.round(detectionResult.confidence * 100)}% confidence
                          {detectionResult.detection_method === "llm" && " (AI-assisted)"}
                        </span>
                        <button
                          className="redetect-btn"
                          onClick={() => setManualTestType("")}
                        >
                          Change
                        </button>
                      </>
                    ) : (
                      <div className="detection-override">
                        <input
                          type="text"
                          className="import-field-textarea"
                          style={{ resize: "none", minHeight: "auto" }}
                          placeholder='e.g., "calcium score", "stress test"'
                          value={manualTestType}
                          onChange={(e) =>
                            setManualTestType(e.target.value || "")
                          }
                        />
                        <button
                          className="redetect-btn"
                          onClick={() => setManualTestType(null)}
                        >
                          Cancel
                        </button>
                      </div>
                    )}
                  </div>
                )}
                {(detectionStatus === "low_confidence" ||
                  detectionStatus === "failed" ||
                  detectionStatus === "error") && (
                  <div className="detection-fallback">
                    <p className="detection-fallback-message">
                      <span className="detection-fallback-icon">{"\u26A0"}</span>
                      {detectionStatus === "low_confidence" && detectionResult
                        ? `Low confidence detection: ${
                            detectionResult.available_types.find(
                              (t) => t.test_type_id === detectionResult.test_type,
                            )?.display_name ?? detectionResult.test_type
                          }. Please confirm or select the correct report type below.`
                        : "Could not automatically identify the report type. Select a type below or enter it manually to continue."}
                    </p>
                    {detectionResult?.available_types && detectionResult.available_types.length > 0 && (
                      <div className="detection-type-buttons">
                        {groupTypesByCategory(detectionResult.available_types).map(([label, types]) => (
                          <div key={label} className="detection-type-group">
                            <span className="detection-type-group-label">{label}</span>
                            <div className="detection-type-group-buttons">
                              {types.map((t) => (
                                <button
                                  key={t.test_type_id}
                                  type="button"
                                  className={`detection-type-btn${manualTestType === t.test_type_id ? " detection-type-btn--active" : ""}`}
                                  onClick={() => setManualTestType(t.test_type_id)}
                                >
                                  {t.display_name}
                                </button>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    <input
                      type="text"
                      className="import-field-textarea"
                      style={{ resize: "none", minHeight: "auto" }}
                      placeholder='Or type a report type, e.g. "calcium score", "renal ultrasound"'
                      value={manualTestType ?? ""}
                      onChange={(e) =>
                        setManualTestType(e.target.value || null)
                      }
                    />
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

              <button
                className="proceed-btn"
                onClick={handleProceed}
                disabled={!resolvedTestType || detectionStatus === "detecting"}
              >
                Continue to Processing
              </button>
            </div>
          )}
        </div>

        {/* Right Column — Settings */}
        <div className="import-right-panel">
          {(templates.length > 0 || sharedTemplates.length > 0) && (
            <div className="import-field">
              <label className="import-field-label">Template</label>
              <span className="import-field-subtitle">Optional</span>
              <select
                className="import-field-select"
                value={selectedTemplateValue}
                onChange={(e) => setSelectedTemplateValue(e.target.value)}
              >
                <option value="">No template</option>
                {templates.length > 0 && (
                  <optgroup label="My Templates">
                    {templates.map((t) => (
                      <option key={t.id} value={`own:${t.id}`}>
                        {t.name}
                        {t.test_type ? ` (${t.test_type})` : ""}
                      </option>
                    ))}
                  </optgroup>
                )}
                {sharedTemplates.length > 0 && (
                  <optgroup label="Shared Templates">
                    {sharedTemplates.map((t) => (
                      <option key={t.sync_id} value={`shared:${t.sync_id}`}>
                        {t.name} — Shared by {t.sharer_email}
                      </option>
                    ))}
                  </optgroup>
                )}
              </select>
            </div>
          )}

          <div className="import-field">
            <label className="import-field-label import-field-label--bold">
              Clinical Context
            </label>
            <span className="import-field-subtitle">Optional but recommended — more context = more personalized interpretation</span>
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
              placeholder="Paste the patient's office note, HPI, or relevant history here. Example: chest pain, follow up pericardial effusion, or full clinic note text."
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

          {/* Test Type Hint */}
          <div className="import-field">
            <label className="import-field-label">Test Type Hint</label>
            <span className="import-field-subtitle">
              Optional — helps identify the report type
            </span>
            <div className="test-type-hint-row">
              <input
                type="text"
                className="import-field-textarea"
                style={{ resize: "none", minHeight: "auto" }}
                placeholder='e.g., "echocardiogram", "lipid panel", "stress test"'
                value={testTypeHint}
                onChange={(e) => setTestTypeHint(e.target.value)}
              />
              {status === "success" && result && testTypeHint.trim() && (
                <button
                  className="redetect-btn"
                  onClick={handleRedetect}
                  disabled={detectionStatus === "detecting"}
                >
                  Re-detect
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
