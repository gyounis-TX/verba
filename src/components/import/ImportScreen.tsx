import { useState, useRef, useCallback, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { sidecarApi } from "../../services/sidecarApi";
import { useToast } from "../shared/Toast";
import type { ExtractionResult, Template } from "../../types/sidecar";
import "./ImportScreen.css";

type ImportMode = "pdf" | "text";
type ImportStatus = "idle" | "extracting" | "success" | "error";

export function ImportScreen() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [mode, setMode] = useState<ImportMode>("pdf");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [pastedText, setPastedText] = useState("");
  const [status, setStatus] = useState<ImportStatus>("idle");
  const [result, setResult] = useState<ExtractionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [clinicalContext, setClinicalContext] = useState("");
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<
    number | undefined
  >(undefined);

  useEffect(() => {
    sidecarApi
      .listTemplates()
      .then((res) => setTemplates(res.items))
      .catch(() => {
        showToast("error", "Failed to load templates.");
      });
  }, [showToast]);

  const resetState = useCallback(() => {
    setStatus("idle");
    setResult(null);
    setError(null);
  }, []);

  const handleModeChange = useCallback(
    (newMode: ImportMode) => {
      setMode(newMode);
      resetState();
    },
    [resetState],
  );

  const validateFile = (file: File): string | null => {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      return "Only PDF files are accepted.";
    }
    if (file.size === 0) {
      return "File is empty.";
    }
    if (file.size > 50 * 1024 * 1024) {
      return "File is too large. Maximum size is 50 MB.";
    }
    return null;
  };

  const handleFileSelect = useCallback(
    (file: File) => {
      const validationError = validateFile(file);
      if (validationError) {
        setError(validationError);
        setSelectedFile(null);
        return;
      }
      setSelectedFile(file);
      resetState();
    },
    [resetState],
  );

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        handleFileSelect(file);
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
      const file = e.dataTransfer.files[0];
      if (file) {
        handleFileSelect(file);
      }
    },
    [handleFileSelect],
  );

  const handleExtract = useCallback(async () => {
    setStatus("extracting");
    setError(null);
    setResult(null);

    try {
      let extractionResult: ExtractionResult;

      if (mode === "pdf") {
        if (!selectedFile) {
          setError("No file selected.");
          setStatus("error");
          return;
        }
        extractionResult = await sidecarApi.extractPdf(selectedFile);
      } else {
        if (!pastedText.trim()) {
          setError("Please enter some text.");
          setStatus("error");
          return;
        }
        extractionResult = await sidecarApi.extractText(pastedText);
      }

      setResult(extractionResult);
      setStatus("success");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Extraction failed.";
      setError(msg);
      setStatus("error");
      showToast("error", msg);
    }
  }, [mode, selectedFile, pastedText, showToast]);

  const handleProceed = useCallback(() => {
    if (result) {
      navigate("/processing", {
        state: {
          extractionResult: result,
          clinicalContext: clinicalContext.trim() || undefined,
          templateId: selectedTemplateId,
        },
      });
    }
  }, [navigate, result, clinicalContext, selectedTemplateId]);

  const canExtract =
    status !== "extracting" &&
    ((mode === "pdf" && selectedFile !== null) ||
      (mode === "text" && pastedText.trim().length > 0));

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="import-screen">
      <header className="import-header">
        <h2 className="import-title">Import Report</h2>
        <p className="import-description">
          Upload a PDF report or paste text from your EMR system.
        </p>
      </header>

      <div className="mode-toggle">
        <button
          className={`mode-toggle-btn ${mode === "pdf" ? "mode-toggle-btn--active" : ""}`}
          onClick={() => handleModeChange("pdf")}
        >
          Upload PDF
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
            className={`drop-zone ${isDragOver ? "drop-zone--active" : ""} ${selectedFile ? "drop-zone--has-file" : ""}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              onChange={handleInputChange}
              className="drop-zone-input"
            />
            {selectedFile ? (
              <div className="drop-zone-file-info">
                <span className="file-name">{selectedFile.name}</span>
                <span className="file-size">
                  {formatFileSize(selectedFile.size)}
                </span>
              </div>
            ) : (
              <div className="drop-zone-prompt">
                <p className="drop-zone-primary">
                  Drag and drop a PDF here, or click to browse
                </p>
                <p className="drop-zone-secondary">PDF files up to 50 MB</p>
              </div>
            )}
          </div>
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
        {status === "extracting" ? "Extracting..." : "Extract Text"}
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
            <pre className="preview-text">
              {result.full_text.slice(0, 2000)}
              {result.full_text.length > 2000 && "\n\n... (truncated)"}
            </pre>
          </div>

          <div className="clinical-context-group">
            <label className="clinical-context-label">
              Clinical Reason for Test (Optional)
            </label>
            <textarea
              className="clinical-context-input"
              placeholder="e.g. Chest pain, shortness of breath, follow-up for diabetes..."
              value={clinicalContext}
              onChange={(e) => setClinicalContext(e.target.value)}
              rows={3}
            />
          </div>

          {templates.length > 0 && (
            <div className="clinical-context-group">
              <label className="clinical-context-label">
                Template (Optional)
              </label>
              <select
                className="clinical-context-input"
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

          <button className="proceed-btn" onClick={handleProceed}>
            Continue to Processing
          </button>
        </div>
      )}
    </div>
  );
}
