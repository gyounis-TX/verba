import { useState, useRef, useCallback, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { sidecarApi } from "../../services/sidecarApi";
import { useToast } from "../shared/Toast";
import type { ExtractionResult, Template, SharedTemplate, DetectTypeResponse } from "../../types/sidecar";
import { groupTypesByCategory } from "../../utils/testTypeCategories";
import QuickNormalModal from "./QuickNormalModal";
import InterpretModal from "./InterpretModal";
import { isAdmin } from "../../services/adminAuth";
import { getSession } from "../../services/supabase";
import { isSupabaseConfigured } from "../../services/syncEngine";
import "./ImportScreen.css";
import "../shared/TypeModal.css";

type ImportMode = "pdf" | "text";
type ImportStatus = "idle" | "extracting" | "success" | "error";
type DetectionStatus = "idle" | "detecting" | "success" | "low_confidence" | "failed" | "error";

interface FileExtractionEntry {
  result?: ExtractionResult;
  error?: string;
  status: "pending" | "extracting" | "success" | "error";
  detectionStatus?: DetectionStatus;
  detectionResult?: DetectTypeResponse | null;
  manualTestType?: string | null;
}

interface TextPasteEntry {
  id: number;
  label: string;
  text: string;
}

function fileKey(file: File): string {
  return `${file.name}::${file.size}`;
}

function textEntryKey(entry: TextPasteEntry): string {
  return `text::${entry.id}`;
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
  textEntries: TextPasteEntry[];
  textEntryNextId: number;
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
    textEntries: [],
    textEntryNextId: 1,
  };
}

let _cache: ImportStateCache = freshCache();

/** Clear all import state (for navigation back to import screen) */
export function clearImportCache(): void {
  _cache = freshCache();
}

export function ImportScreen() {
  const navigate = useNavigate();
  const location = useLocation();
  const { showToast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const extractionResultsRef = useRef<Map<string, FileExtractionEntry>>(new Map());

  // Check for preserved context from "Same Patient" navigation
  const locationState = location.state as {
    preservedClinicalContext?: string;
    preservedQuickReasons?: string[];
  } | null;

  const [selectedFiles, setSelectedFiles] = useState<File[]>(_cache.selectedFiles);
  const mode: ImportMode = selectedFiles.length > 0 ? "pdf" : "text";
  const [pastedText, setPastedText] = useState(_cache.pastedText);
  const [status, setStatus] = useState<ImportStatus>(_cache.status);
  const [result, setResult] = useState<ExtractionResult | null>(_cache.result);
  const [error, setError] = useState<string | null>(_cache.error);
  const [isDragOver, setIsDragOver] = useState(false);
  const [expandedPreviews, setExpandedPreviews] = useState<Set<string>>(new Set());
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
  const [phiFound, setPhiFound] = useState<string[]>([]);
  const [redactionCount, setRedactionCount] = useState(0);

  // Multi-text paste state
  const [textEntries, setTextEntries] = useState<TextPasteEntry[]>(_cache.textEntries);
  const [textEntryNextId, setTextEntryNextId] = useState(_cache.textEntryNextId);

  // Test type detection state
  const [testTypeHint, setTestTypeHint] = useState(_cache.testTypeHint);
  const [detectionStatus, setDetectionStatus] = useState<DetectionStatus>(_cache.detectionStatus);
  const [detectionResult, setDetectionResult] = useState<DetectTypeResponse | null>(_cache.detectionResult);
  const [manualTestType, setManualTestType] = useState<string | null>(_cache.manualTestType);

  // Type selection modal state
  const [showTypeModal, setShowTypeModal] = useState(false);
  const [modalSelectedType, setModalSelectedType] = useState<string | null>(null);
  const [modalCustomType, setModalCustomType] = useState("");
  const [modalEditingKey, setModalEditingKey] = useState<string | null>(null);

  // Quick Normal modal state
  const [showQuickNormal, setShowQuickNormal] = useState(false);

  // Interpret modal state (admin-only)
  const [showInterpret, setShowInterpret] = useState(false);
  const [userEmail, setUserEmail] = useState<string | null>(null);

  // Single-report preview collapse state
  const [singlePreviewExpanded, setSinglePreviewExpanded] = useState(false);

  // Patient mismatch warning state
  const [showMismatchModal, setShowMismatchModal] = useState(false);
  const [pendingProceedState, setPendingProceedState] = useState<Record<string, unknown> | null>(null);

  // Track whether we've applied location state (to avoid re-applying on re-renders)
  const [appliedLocationState, setAppliedLocationState] = useState(false);

  // Apply preserved context from "Same Patient" navigation
  useEffect(() => {
    if (!appliedLocationState && locationState) {
      if (locationState.preservedClinicalContext) {
        setClinicalContext(locationState.preservedClinicalContext);
      }
      if (locationState.preservedQuickReasons) {
        setSelectedReasons(new Set(locationState.preservedQuickReasons));
      }
      setAppliedLocationState(true);
      // Clear location state to prevent re-applying on future renders
      window.history.replaceState({}, document.title);
    }
  }, [locationState, appliedLocationState]);

  // Fetch user email for admin check
  useEffect(() => {
    if (!isSupabaseConfigured()) return;
    getSession().then((session) => {
      setUserEmail(session?.user?.email ?? null);
    });
  }, []);

  // Sync component state → module-level cache so it survives navigation
  useEffect(() => {
    _cache = {
      mode, selectedFiles, pastedText, status, result, error,
      extractionResults, selectedResultKey, clinicalContext,
      selectedReasons, selectedTemplateValue, scrubbedText,
      scrubbedClinicalContext, testTypeHint, detectionStatus,
      detectionResult, manualTestType, textEntries, textEntryNextId,
    };
    extractionResultsRef.current = extractionResults;
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
          setPhiFound(res.phi_found ?? []);
          setRedactionCount(res.redaction_count ?? 0);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setScrubbedText(result.full_text);
          setScrubbedClinicalContext(clinicalContext);
          setPhiFound([]);
          setRedactionCount(0);
        }
      })
      .finally(() => {
        if (!cancelled) setIsScrubbing(false);
      });
    return () => { cancelled = true; };
  }, [result, clinicalContext]);

  // Auto-detect test type when extraction succeeds (single report only)
  useEffect(() => {
    if (!result) return;
    // Suppress in batch mode — each entry detects independently
    if ([...extractionResults.values()].filter(e => e.status === "success").length > 1) return;
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

  // Auto-open type selection modal when detection is uncertain (single report only)
  useEffect(() => {
    // Suppress in batch mode — cards have inline controls
    if (extractionResults.size > 1) return;
    if (
      (detectionStatus === "low_confidence" || detectionStatus === "failed" || detectionStatus === "error") &&
      manualTestType == null
    ) {
      if (detectionStatus === "low_confidence" && detectionResult?.test_type) {
        setModalSelectedType(detectionResult.test_type);
      } else {
        setModalSelectedType(null);
      }
      setModalCustomType("");
      setShowTypeModal(true);
    }
  }, [detectionStatus, detectionResult, manualTestType, extractionResults.size]);

  const resolvedTestType =
    (manualTestType != null && manualTestType.trim() !== "" ? manualTestType.trim() : null) ??
    (testTypeHint.trim() || null) ??
    (detectionStatus === "success" ? detectionResult?.test_type ?? undefined : undefined);

  /** Resolve test type for an individual batch entry. */
  const resolveEntryTestType = (entry: FileExtractionEntry): string | undefined => {
    if (entry.manualTestType != null && entry.manualTestType.trim() !== "") return entry.manualTestType.trim();
    if ((entry.detectionStatus === "success" || entry.detectionStatus === "low_confidence") && entry.detectionResult?.test_type) return entry.detectionResult.test_type;
    return undefined;
  };

  const validateFile = (file: File): string | null => {
    const name = file.name.toLowerCase();
    const validExts = [".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".txt"];
    const hasValidExt = validExts.some((ext) => name.endsWith(ext));
    if (!hasValidExt) {
      return `"${file.name}": Unsupported file type. Accepted: PDF, JPG, PNG, TIF, TXT.`;
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
      const validFiles: File[] = [];
      for (const file of files) {
        const validationError = validateFile(file);
        if (validationError) {
          showToast("error", validationError);
        } else {
          validFiles.push(file);
        }
      }
      if (validFiles.length === 0) return;
      setError(null);
      const maxFiles = 5 - textEntries.length;
      setSelectedFiles((prev) => [...prev, ...validFiles].slice(0, maxFiles));
      setPastedText("");
      resetState();
    },
    [resetState, showToast, textEntries.length],
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
      const nonEmptyText = textEntries.filter((e) => e.text.trim().length > 0);

      if (selectedFiles.length > 0 || nonEmptyText.length > 1) {
        // Batch mode: extract all files + text entries into one results Map
        if (selectedFiles.length === 0 && nonEmptyText.length === 0) {
          setError("No files or text entries to analyze.");
          setStatus("error");
          return;
        }

        const results = new Map<string, FileExtractionEntry>();
        const prevResults = extractionResultsRef.current;

        // Initialize all as pending (reuse cached extractions)
        for (const file of selectedFiles) {
          const key = fileKey(file);
          const cached = prevResults.get(key);
          results.set(key, cached?.status === "success" && cached.result ? cached : { status: "pending" });
        }
        for (const entry of nonEmptyText) {
          const key = textEntryKey(entry);
          const cached = prevResults.get(key);
          results.set(key, cached?.status === "success" && cached.result ? cached : { status: "pending" });
        }
        setExtractionResults(new Map(results));

        let lastSuccessKey: string | null = null;

        // Phase 1: Extract all files (sequential, skip already-extracted)
        for (const file of selectedFiles) {
          const key = fileKey(file);
          const existing = results.get(key);
          if (existing?.status === "success" && existing.result) {
            lastSuccessKey = key;
            continue;
          }

          results.set(key, { status: "extracting" });
          setExtractionResults(new Map(results));

          try {
            const extractionResult = await sidecarApi.extractFile(file);
            results.set(key, { status: "success", result: extractionResult });
            lastSuccessKey = key;
            setExtractionResults(new Map(results));
          } catch (err) {
            const msg = err instanceof Error ? err.message : "Extraction failed.";
            results.set(key, { status: "error", error: msg });
            setExtractionResults(new Map(results));
          }
        }

        // Phase 1b: Extract all text entries (sequential, skip already-extracted)
        for (const entry of nonEmptyText) {
          const key = textEntryKey(entry);
          const existing = results.get(key);
          if (existing?.status === "success" && existing.result) {
            lastSuccessKey = key;
            continue;
          }

          results.set(key, { status: "extracting" });
          setExtractionResults(new Map(results));

          try {
            const extractionResult = await sidecarApi.extractText(entry.text);
            extractionResult.filename = entry.label;
            results.set(key, { status: "success", result: extractionResult });
            lastSuccessKey = key;
            setExtractionResults(new Map(results));
          } catch (err) {
            const msg = err instanceof Error ? err.message : "Extraction failed.";
            results.set(key, { status: "error", error: msg });
            setExtractionResults(new Map(results));
          }
        }

        // Phase 2: Detect types sequentially (no concurrent sidecar calls)
        const keysToDetect = [...results.entries()]
          .filter(([, e]) => e.status === "success" && e.result && !e.detectionResult)
          .map(([k]) => k);

        for (const detKey of keysToDetect) {
          const entry = results.get(detKey)!;
          results.set(detKey, { ...entry, detectionStatus: "detecting" });
          setExtractionResults(new Map(results));

          try {
            const res = await sidecarApi.detectTestType(entry.result!, testTypeHint || undefined);
            const ds: DetectionStatus = res.confidence >= 0.4 && res.test_type != null
              ? "success"
              : res.confidence > 0 && res.test_type != null
                ? "low_confidence"
                : "failed";
            results.set(detKey, { ...results.get(detKey)!, detectionStatus: ds, detectionResult: res });
          } catch {
            results.set(detKey, { ...results.get(detKey)!, detectionStatus: "error" });
          }
          setExtractionResults(new Map(results));
        }

        // Count successes
        const successes = [...results.values()].filter(
          (e) => e.status === "success",
        );
        if (successes.length === 0) {
          setStatus("error");
          setError("All extractions failed.");
          return;
        }

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
        // Single text: either textEntries[0] or pastedText
        const text = nonEmptyText.length === 1 ? nonEmptyText[0].text : pastedText;
        if (!text.trim()) {
          setError("Please enter some text.");
          setStatus("error");
          return;
        }

        // Classify the input
        const classification = await sidecarApi.classifyInput(text);

        if (classification.classification === "question") {
          // Generate a letter and navigate to results in letter mode
          const letter = await sidecarApi.generateLetter({
            prompt: text.trim(),
            letter_type: "general",
          });
          _cache = freshCache();
          navigate("/results", {
            state: {
              letterMode: true,
              letterId: letter.id,
              letterContent: letter.content,
              letterPrompt: text.trim(),
            },
          });
          return;
        }

        // It's a report — extract as before
        const extractionResult = await sidecarApi.extractText(text);
        setResult(extractionResult);
        setStatus("success");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Analysis failed.";
      setError(msg);
      setStatus("error");
      showToast("error", msg);
    }
  }, [selectedFiles, pastedText, textEntries, showToast, navigate]);

  const doProceed = useCallback((state: Record<string, unknown>) => {
    navigate("/processing", { state });
  }, [navigate]);

  const handleProceed = useCallback(async () => {
    // Collect all successful extraction results
    const successfulResults: Array<{ key: string; result: ExtractionResult }> = [];
    const testTypes: Record<string, string> = {};
    for (const [key, entry] of extractionResults) {
      if (entry.status === "success" && entry.result) {
        successfulResults.push({ key, result: entry.result });
        const entryType = resolveEntryTestType(entry);
        if (entryType) testTypes[key] = entryType;
      }
    }

    // Batch mode: derive primary type from first entry
    const isBatch = successfulResults.length > 1;
    const effectiveTestType = isBatch
      ? (testTypes[successfulResults[0].key] ?? resolvedTestType)
      : resolvedTestType;
    const effectiveResult = isBatch
      ? (successfulResults[0].result ?? result)
      : result;

    if (effectiveResult && effectiveTestType) {
      const state: Record<string, unknown> = {
        extractionResult: effectiveResult,
        clinicalContext: clinicalContext.trim() || undefined,
        testType: effectiveTestType,
        quickReasons: selectedReasons.size > 0 ? Array.from(selectedReasons) : undefined,
      };
      if (selectedTemplateValue.startsWith("own:")) {
        state.templateId = Number(selectedTemplateValue.slice(4));
      } else if (selectedTemplateValue.startsWith("shared:")) {
        state.sharedTemplateSyncId = selectedTemplateValue.slice(7);
      }
      if (isBatch) {
        state.batchExtractionResults = successfulResults;
        state.testTypes = testTypes;

        // Patient mismatch check: compare fingerprints across batch entries
        try {
          const texts = successfulResults.map(r => r.result.full_text);
          const fingerprints = await sidecarApi.computePatientFingerprints(texts);
          const nonEmpty = fingerprints.filter(f => f !== "");
          if (nonEmpty.length >= 2) {
            const unique = new Set(nonEmpty);
            if (unique.size > 1) {
              // Fingerprints differ — show warning modal
              setPendingProceedState(state);
              setShowMismatchModal(true);
              return;
            }
          }
        } catch {
          // Fingerprint check is non-critical — proceed anyway
        }
      }
      doProceed(state);
    }
  }, [doProceed, result, selectedTemplateValue, clinicalContext, selectedReasons, resolvedTestType, extractionResults, resolveEntryTestType]);

  const canExtract =
    status !== "extracting" &&
    (selectedFiles.length > 0 ||
      pastedText.trim().length > 0 ||
      textEntries.some((e) => e.text.trim().length > 0));

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
          Upload files (PDF, images, TIF, text), paste results from EHR, or ask a question.
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
              accept=".pdf,.jpg,.jpeg,.png,.tif,.tiff,.txt,application/pdf,image/jpeg,image/png,image/tiff,text/plain"
              multiple
              onChange={handleInputChange}
              className="drop-zone-input"
            />
            {selectedFiles.length > 0 || textEntries.length > 0 ? (
              <div className="unified-file-display">
                {/* File cards */}
                {selectedFiles.map((file, idx) => (
                  <div key={fileKey(file)} className="file-list-item">
                    <span className="file-list-name">{file.name}</span>
                    <span className="file-list-size">
                      {formatFileSize(file.size)}
                    </span>
                    {(() => {
                      const entry = extractionResults.get(fileKey(file));
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
                      onClick={() => handleRemoveFile(idx)}
                      aria-label={`Remove ${file.name}`}
                    >
                      &times;
                    </button>
                  </div>
                ))}

                {/* Text entry cards */}
                {textEntries.map((entry) => (
                  <div key={entry.id} className="text-entry-card">
                    <div className="text-entry-header">
                      <input
                        className="text-entry-label"
                        value={entry.label}
                        onChange={(e) => {
                          setTextEntries((prev) =>
                            prev.map((te) =>
                              te.id === entry.id ? { ...te, label: e.target.value } : te
                            )
                          );
                        }}
                      />
                      {(() => {
                        const exEntry = extractionResults.get(textEntryKey(entry));
                        return exEntry ? (
                          <span className={`file-list-status file-list-status--${exEntry.status}`}>
                            {exEntry.status === "pending" && "Pending"}
                            {exEntry.status === "extracting" && "Extracting..."}
                            {exEntry.status === "success" && "Done"}
                            {exEntry.status === "error" && (exEntry.error ?? "Failed")}
                          </span>
                        ) : null;
                      })()}
                      <button
                        className="file-list-remove"
                        onClick={() => {
                          setTextEntries((prev) => {
                            const next = prev.filter((te) => te.id !== entry.id);
                            if (next.length <= 1 && selectedFiles.length === 0) {
                              // Demote to single-paste mode only when no files present
                              setPastedText(next.length === 1 ? next[0].text : "");
                              return [];
                            }
                            return next;
                          });
                          resetState();
                        }}
                        aria-label={`Remove ${entry.label}`}
                      >
                        &times;
                      </button>
                    </div>
                    <textarea
                      className="text-entry-textarea"
                      placeholder="Paste report text here..."
                      value={entry.text}
                      onChange={(e) => {
                        setTextEntries((prev) =>
                          prev.map((te) =>
                            te.id === entry.id ? { ...te, text: e.target.value } : te
                          )
                        );
                        resetState();
                      }}
                      rows={6}
                    />
                    <span className="char-count">
                      {entry.text.length.toLocaleString()} characters
                    </span>
                  </div>
                ))}

                {/* Add buttons (when under cap) */}
                {selectedFiles.length + textEntries.length < 5 && (
                  <div className="batch-add-buttons">
                    <button
                      type="button"
                      className="batch-add-more-btn"
                      onClick={() => fileInputRef.current?.click()}
                    >
                      + Add file
                    </button>
                    <button
                      type="button"
                      className="batch-add-more-btn"
                      onClick={() => {
                        const nextId = textEntryNextId;
                        setTextEntries((prev) => [
                          ...prev,
                          { id: nextId, label: `Report ${selectedFiles.length + prev.length + 1}`, text: "" },
                        ]);
                        setTextEntryNextId(nextId + 1);
                      }}
                    >
                      + Add pasted report
                    </button>
                  </div>
                )}
                <p className="unified-file-hint">
                  {`${selectedFiles.length + textEntries.length} of 5 reports`}
                </p>
              </div>
            ) : (
              <>
                <textarea
                  className="text-input"
                  placeholder={"\u2022 Paste a test result. Include header with title of test or lab\n\u2022 Drag and drop a PDF, JPG, PNG, TIF, or TXT file (up to 50 MB)\n\u2022 Ask for help explaining a question, topic, or situation to a patient"}
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
                  <div className="text-input-footer-right">
                    <button
                      type="button"
                      className="batch-add-more-btn-inline"
                      onClick={() => {
                        const id1 = textEntryNextId;
                        const id2 = textEntryNextId + 1;
                        setTextEntries([
                          { id: id1, label: "Report 1", text: pastedText },
                          { id: id2, label: "Report 2", text: "" },
                        ]);
                        setTextEntryNextId(id2 + 1);
                        setPastedText("");
                      }}
                    >
                      + Add another report
                    </button>
                    <button
                      type="button"
                      className="browse-file-btn"
                      onClick={() => fileInputRef.current?.click()}
                    >
                      Browse files
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>

          <div className="extract-btn-row">
            <button
              className="extract-btn"
              onClick={handleExtract}
              disabled={!canExtract}
            >
              {status === "extracting"
                ? "Analyzing..."
                : selectedFiles.length + textEntries.length > 1
                  ? `Analyze All (${selectedFiles.length + textEntries.length} reports)`
                  : "Analyze"}
            </button>
            <button
              className="start-over-btn"
              onClick={() => {
                setSelectedFiles([]);
                setPastedText("");
                setTextEntries([]);
                setTextEntryNextId(1);
                setClinicalContext("");
                resetState();
              }}
            >
              Start Over
            </button>
          </div>

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

              {/* Multi-result: collapsible cards for each extraction */}
              {(() => {
                const successEntries = [...extractionResults.entries()].filter(
                  ([, e]) => e.status === "success",
                );
                if (successEntries.length > 1) {
                  return (
                    <div className="multi-preview-cards">
                      {successEntries.map(([key, entry]) => {
                        const r = entry.result!;
                        const label = key.startsWith("text::")
                          ? (textEntries.find(
                              (te) => te.id === parseInt(key.slice(6), 10),
                            )?.label ?? "Text")
                          : key.split("::")[0];
                        const isExpanded = expandedPreviews.has(key);
                        const resolvedType = resolveEntryTestType(entry);
                        return (
                          <div key={key} className={`preview-card${isExpanded ? " preview-card--expanded" : ""}`}>
                            <button
                              className="preview-card-header"
                              onClick={() => {
                                setExpandedPreviews((prev) => {
                                  const next = new Set(prev);
                                  if (next.has(key)) next.delete(key);
                                  else next.add(key);
                                  return next;
                                });
                              }}
                            >
                              <span className="preview-card-label">{label}</span>
                              <span className="preview-card-stats">
                                {r.total_pages} pg &middot; {r.total_chars.toLocaleString()} chars
                              </span>
                              <span className={`preview-card-chevron${isExpanded ? " preview-card-chevron--open" : ""}`}>
                                &#9662;
                              </span>
                            </button>
                            {/* Per-card detection badge */}
                            <div className="preview-card-detection">
                              {entry.detectionStatus === "detecting" && (
                                <span className="detection-badge-inline">
                                  <span className="spinner-inline" /> Detecting...
                                </span>
                              )}
                              {entry.detectionStatus === "success" && entry.detectionResult && !entry.manualTestType && (
                                <span className="detection-badge-inline">
                                  <span className="detection-badge--success">
                                    {entry.detectionResult.available_types.find(
                                      (t) => t.test_type_id === entry.detectionResult!.test_type,
                                    )?.display_name ?? entry.detectionResult.test_type}
                                  </span>
                                  <span className="detection-confidence">
                                    {Math.round(entry.detectionResult.confidence * 100)}%
                                  </span>
                                  <button
                                    className="redetect-btn"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setModalEditingKey(key);
                                      setModalSelectedType(entry.detectionResult?.test_type ?? null);
                                      setModalCustomType("");
                                      setShowTypeModal(true);
                                    }}
                                  >
                                    Change
                                  </button>
                                </span>
                              )}
                              {entry.manualTestType && (
                                <span className="detection-badge-inline">
                                  <span className="detection-badge--success">
                                    {entry.detectionResult?.available_types?.find(
                                      (t) => t.test_type_id === entry.manualTestType,
                                    )?.display_name ?? entry.manualTestType}
                                  </span>
                                  <button
                                    className="redetect-btn"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setModalEditingKey(key);
                                      setModalSelectedType(entry.manualTestType ?? null);
                                      setModalCustomType("");
                                      setShowTypeModal(true);
                                    }}
                                  >
                                    Change
                                  </button>
                                </span>
                              )}
                              {!entry.manualTestType && (entry.detectionStatus === "low_confidence" || entry.detectionStatus === "failed" || entry.detectionStatus === "error") && (
                                <span className="detection-badge-inline">
                                  <span className="detection-fallback-icon">{"\u26A0"}</span>
                                  <span className="detection-fallback-text">
                                    {entry.detectionStatus === "low_confidence" && entry.detectionResult
                                      ? `Low: ${entry.detectionResult.available_types?.find(
                                          (t) => t.test_type_id === entry.detectionResult!.test_type,
                                        )?.display_name ?? entry.detectionResult.test_type}`
                                      : "Not detected"}
                                  </span>
                                  <button
                                    className="redetect-btn"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setModalEditingKey(key);
                                      if (entry.detectionStatus === "low_confidence" && entry.detectionResult?.test_type) {
                                        setModalSelectedType(entry.detectionResult.test_type);
                                      } else {
                                        setModalSelectedType(null);
                                      }
                                      setModalCustomType("");
                                      setShowTypeModal(true);
                                    }}
                                  >
                                    Select type
                                  </button>
                                </span>
                              )}
                              {!resolvedType && entry.detectionStatus !== "detecting" && (
                                <span className="detection-badge-inline detection-badge-inline--warning">
                                  Type required
                                </span>
                              )}
                            </div>
                            {isExpanded && (
                              <div className="preview-card-body">
                                <pre className="preview-text">{r.full_text}</pre>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  );
                }

                // Single result — collapsible stats + text preview
                return (
                  <div className="single-preview-collapsible">
                    <button
                      className="preview-card-header"
                      onClick={() => setSinglePreviewExpanded((prev) => !prev)}
                    >
                      <span className="preview-card-label">Extraction Preview</span>
                      <span className="preview-card-stats">
                        {result.total_pages} pg &middot; {result.total_chars.toLocaleString()} chars
                        {result.tables.length > 0 && ` \u00b7 ${result.tables.length} tables`}
                      </span>
                      <span className={`preview-card-chevron${singlePreviewExpanded ? " preview-card-chevron--open" : ""}`}>
                        &#9662;
                      </span>
                    </button>
                    {singlePreviewExpanded && (
                      <div className="single-preview-body">
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
                      </div>
                    )}
                  </div>
                );
              })()}

              {/* Detection Status — hidden in batch mode (per-card badges used instead) */}
              {[...extractionResults.values()].filter(e => e.status === "success").length <= 1 && (
                <div className="detection-status">
                  {detectionStatus === "detecting" && (
                    <div className="detection-detecting">
                      <div className="spinner" />
                      <span>Detecting report type...</span>
                    </div>
                  )}
                  {detectionStatus === "success" && detectionResult && (
                    <div className="detection-success">
                      <span className="detection-badge--success">
                        {detectionResult.available_types.find(
                          (t) => t.test_type_id === (manualTestType || detectionResult.test_type),
                        )?.display_name ?? manualTestType ?? detectionResult.test_type}
                      </span>
                      {!manualTestType && (
                        <span className="detection-confidence">
                          {Math.round(detectionResult.confidence * 100)}% confidence
                          {detectionResult.detection_method === "llm" && " (AI-assisted)"}
                        </span>
                      )}
                      <button
                        className="redetect-btn"
                        onClick={() => {
                          setModalSelectedType(manualTestType || detectionResult.test_type);
                          setModalCustomType("");
                          setShowTypeModal(true);
                        }}
                      >
                        Change
                      </button>
                    </div>
                  )}
                  {(detectionStatus === "low_confidence" ||
                    detectionStatus === "failed" ||
                    detectionStatus === "error") && (
                    <div className="detection-fallback-compact">
                      {manualTestType ? (
                        <>
                          <span className="detection-badge--success">
                            {detectionResult?.available_types?.find(
                              (t) => t.test_type_id === manualTestType,
                            )?.display_name ?? manualTestType}
                          </span>
                          <button
                            className="redetect-btn"
                            onClick={() => {
                              setModalSelectedType(manualTestType);
                              setModalCustomType("");
                              setShowTypeModal(true);
                            }}
                          >
                            Change
                          </button>
                        </>
                      ) : (
                        <>
                          <span className="detection-fallback-icon">{"\u26A0"}</span>
                          <span className="detection-fallback-text">
                            {detectionStatus === "low_confidence" && detectionResult
                              ? `Low confidence: ${
                                  detectionResult.available_types?.find(
                                    (t) => t.test_type_id === detectionResult.test_type,
                                  )?.display_name ?? detectionResult.test_type
                                }`
                              : "Report type not detected."}
                          </span>
                          <button
                            className="redetect-btn"
                            onClick={() => {
                              if (detectionStatus === "low_confidence" && detectionResult?.test_type) {
                                setModalSelectedType(detectionResult.test_type);
                              }
                              setShowTypeModal(true);
                            }}
                          >
                            Select type
                          </button>
                        </>
                      )}
                    </div>
                  )}
                </div>
              )}

              <div className={`phi-badge ${isScrubbing ? "phi-badge--scanning" : redactionCount > 0 ? "phi-badge--found" : "phi-badge--clean"}`}>
                {isScrubbing ? (
                  <>
                    <span className="phi-badge-icon"><span className="spinner-inline" /></span>
                    <span>Scanning for PHI...</span>
                  </>
                ) : redactionCount > 0 ? (
                  <>
                    <span className="phi-badge-icon">{"\uD83D\uDEE1\uFE0F"}</span>
                    <span>{redactionCount} {redactionCount === 1 ? "item" : "items"} redacted ({phiFound.join(", ")})</span>
                  </>
                ) : (
                  <>
                    <span className="phi-badge-icon">{"\uD83D\uDEE1\uFE0F"}</span>
                    <span>No PHI detected &mdash; safe to process</span>
                  </>
                )}
              </div>

              {(() => {
                const successEntries = [...extractionResults.values()].filter(e => e.status === "success");
                const isSingleReport = successEntries.length <= 1;
                const isLikelyNormal = isSingleReport && detectionStatus === "success" && detectionResult?.is_likely_normal === true;
                const proceedDisabled = (() => {
                  if (successEntries.length > 1) {
                    return successEntries.some(e => e.detectionStatus === "detecting");
                  }
                  return !resolvedTestType || detectionStatus === "detecting";
                })();

                return (
                  <div className="proceed-actions">
                    {isAdmin(userEmail) && isSingleReport && (
                      <button
                        className="proceed-btn--quick-normal"
                        onClick={() => setShowInterpret(true)}
                        disabled={proceedDisabled}
                      >
                        Interpret
                      </button>
                    )}
                    {isLikelyNormal && (
                      <button
                        className="proceed-btn--quick-normal"
                        onClick={() => setShowQuickNormal(true)}
                        disabled={proceedDisabled}
                      >
                        Quick Normal
                      </button>
                    )}
                    <button
                      className="proceed-btn"
                      onClick={handleProceed}
                      disabled={proceedDisabled}
                    >
                      {isLikelyNormal ? "Full Analysis" : "Continue to Processing"}
                    </button>
                  </div>
                );
              })()}
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
              Clinical Context <span className="import-field-optional">(optional)</span>
            </label>
            <span className="import-field-subtitle">More context = more personalized</span>
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
              rows={7}
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
            <label className="import-field-label">
              Test Type Hint <span className="import-field-optional">(optional)</span>
            </label>
            <span className="import-field-subtitle">
              Helps identify the report type
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

      {/* Type Selection Modal */}
      {showTypeModal && (() => {
        // Resolve which detection result to show — entry-specific in batch mode, global otherwise
        const modalDetection = modalEditingKey
          ? extractionResults.get(modalEditingKey)?.detectionResult ?? detectionResult
          : detectionResult;
        const modalDetStatus = modalEditingKey
          ? extractionResults.get(modalEditingKey)?.detectionStatus ?? detectionStatus
          : detectionStatus;
        return (
        <div className="type-modal-backdrop" onClick={() => { setShowTypeModal(false); setModalEditingKey(null); }}>
          <div className="type-modal" onClick={(e) => e.stopPropagation()}>
            <h3 className="type-modal-title">Select Report Type</h3>
            <p className="type-modal-subtitle">
              {modalDetStatus === "low_confidence" && modalDetection
                ? `We detected this might be a ${
                    modalDetection.available_types?.find(
                      (t) => t.test_type_id === modalDetection.test_type,
                    )?.display_name ?? modalDetection.test_type
                  } (${Math.round(modalDetection.confidence * 100)}% confidence). Please confirm or select the correct type.`
                : "Could not automatically identify the report type. Please select the correct type below."}
            </p>

            {modalDetection?.available_types && modalDetection.available_types.length > 0 && (
              <div className="type-modal-categories">
                {groupTypesByCategory(modalDetection.available_types).map(([label, types]) => (
                  <div key={label} className="type-modal-category">
                    <span className="type-modal-category-label">{label}</span>
                    <div className="type-modal-category-buttons">
                      {types.map((t) => (
                        <button
                          key={t.test_type_id}
                          className={`detection-type-btn${
                            modalSelectedType === t.test_type_id && !modalCustomType
                              ? " detection-type-btn--active"
                              : ""
                          }`}
                          onClick={() => {
                            setModalSelectedType(t.test_type_id);
                            setModalCustomType("");
                          }}
                        >
                          {t.display_name}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div className="type-modal-other">
              <label className="type-modal-other-label">Other:</label>
              <input
                type="text"
                className="type-modal-other-input"
                placeholder='e.g. "calcium score", "renal ultrasound"'
                value={modalCustomType}
                onChange={(e) => {
                  setModalCustomType(e.target.value);
                  if (e.target.value) setModalSelectedType(null);
                }}
              />
            </div>

            <div className="type-modal-actions">
              <button
                className="type-modal-cancel"
                onClick={() => { setShowTypeModal(false); setModalEditingKey(null); }}
              >
                Cancel
              </button>
              <button
                className="type-modal-confirm"
                disabled={!modalSelectedType && !modalCustomType.trim()}
                onClick={() => {
                  const chosen = modalCustomType.trim() || modalSelectedType;
                  if (modalEditingKey) {
                    // Per-card modal: write to the specific entry
                    setExtractionResults((prev) => {
                      const next = new Map(prev);
                      const entry = next.get(modalEditingKey);
                      if (entry) next.set(modalEditingKey, { ...entry, manualTestType: chosen });
                      return next;
                    });
                    setModalEditingKey(null);
                  } else {
                    // Global modal: existing single-report behavior
                    setManualTestType(chosen);
                  }
                  setShowTypeModal(false);
                }}
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
        );
      })()}

      {/* Quick Normal Modal */}
      {showQuickNormal && result && resolvedTestType && (
        <QuickNormalModal
          extractionResult={result}
          testType={resolvedTestType}
          testTypeDisplay={
            detectionResult?.available_types?.find(
              (t) => t.test_type_id === resolvedTestType,
            )?.display_name ?? resolvedTestType
          }
          clinicalContext={clinicalContext.trim() || undefined}
          quickReasons={selectedReasons.size > 0 ? Array.from(selectedReasons) : undefined}
          onClose={() => setShowQuickNormal(false)}
          onViewFullAnalysis={() => {
            setShowQuickNormal(false);
            handleProceed();
          }}
        />
      )}

      {/* Interpret Modal (admin-only) */}
      {showInterpret && result && resolvedTestType && (
        <InterpretModal
          extractionResult={result}
          testType={resolvedTestType}
          testTypeDisplay={
            detectionResult?.available_types?.find(
              (t) => t.test_type_id === resolvedTestType,
            )?.display_name ?? resolvedTestType
          }
          onClose={() => setShowInterpret(false)}
        />
      )}

      {/* Patient Mismatch Warning Modal */}
      {showMismatchModal && (
        <div className="type-modal-backdrop" onClick={() => setShowMismatchModal(false)}>
          <div className="type-modal" onClick={(e) => e.stopPropagation()}>
            <h3 className="type-modal-title">Patient Mismatch Detected</h3>
            <p className="type-modal-subtitle">
              These reports may belong to different patients based on the patient
              identifiers found in the text. Processing reports from different
              patients together may produce inaccurate cross-references.
            </p>
            <div className="type-modal-actions">
              <button
                className="type-modal-cancel"
                onClick={() => {
                  setShowMismatchModal(false);
                  setPendingProceedState(null);
                }}
              >
                Go Back
              </button>
              <button
                className="type-modal-confirm"
                onClick={() => {
                  setShowMismatchModal(false);
                  if (pendingProceedState) {
                    doProceed(pendingProceedState);
                    setPendingProceedState(null);
                  }
                }}
              >
                Continue Anyway
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
