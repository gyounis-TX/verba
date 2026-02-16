import { useEffect, useState, useCallback } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import type {
  ExplainResponse,
  ExtractionResult,
  MeasurementExplanation,
  ParsedMeasurement,
  LiteracyLevel,
  ExplanationVoice,
  FooterType,
  TeachingPoint,
  SharedTeachingPoint,
  Template,
  SharedTemplate,
  TestTypeInfo,
} from "../../types/sidecar";
import { sidecarApi } from "../../services/sidecarApi";
import { logUsage } from "../../services/usageTracker";
import { queueUpsertAfterMutation } from "../../services/syncEngine";
import { useToast } from "../shared/Toast";
import { clearImportCache } from "../import/ImportScreen";
import { groupTypesByCategory } from "../../utils/testTypeCategories";
import { CommentPanel } from "./CommentPanel";
import { KeyFindingsPanel } from "./KeyFindingsPanel";
import { MeasurementsTable } from "./MeasurementsTable";
import { RefinementSidebar } from "./RefinementSidebar";
import { TeachingPointsPanel } from "./TeachingPointsPanel";
import "./ResultsScreen.css";
import "../shared/TypeModal.css";

function replacePhysician(text: string, physicianName?: string): string {
  if (!physicianName) return text;
  return text
    .replace(/\byour doctor\b/gi, physicianName)
    .replace(/\byour physician\b/gi, physicianName)
    .replace(/\byour healthcare provider\b/gi, physicianName)
    .replace(/\byour provider\b/gi, physicianName);
}

function buildCopyText(
  summary: string,
  findings: { finding: string; explanation: string }[],
  measurements: MeasurementExplanation[],
  footer: string,
  includeKeyFindings: boolean,
  includeMeasurements: boolean,
  nextSteps?: string[],
): string {
  const parts: string[] = [];
  parts.push(summary);
  if (includeKeyFindings && findings.length > 0) {
    parts.push("");
    parts.push("KEY FINDINGS");
    for (const f of findings) {
      parts.push("");
      parts.push(`- ${f.finding}: ${f.explanation}`);
    }
  }
  if (includeMeasurements && measurements.length > 0) {
    parts.push("");
    parts.push("MEASUREMENTS");
    for (const m of measurements) {
      parts.push(`- ${m.abbreviation}: ${m.value} ${m.unit} (${m.plain_language})`);
    }
  }
  if (nextSteps && nextSteps.length > 0 && !(nextSteps.length === 1 && nextSteps[0] === "No comment")) {
    parts.push("");
    parts.push("NEXT STEPS");
    for (const step of nextSteps) {
      parts.push(`- ${step}`);
    }
  }
  if (footer) {
    parts.push("");
    parts.push(footer);
  }
  return parts.join("\n");
}

const SESSION_KEY = "explify_results_nav";

/**
 * Save ONLY non-PHI navigation metadata to sessionStorage.
 * Never persist medical report content, explanations, or clinical context.
 */
function saveSessionState(data: Record<string, unknown>) {
  try {
    const safe: Record<string, unknown> = {};
    // Only keep non-PHI navigation keys
    for (const key of ["fromHistory", "historyId", "historyLiked", "templateId", "letterMode", "letterId"]) {
      if (data[key] !== undefined) safe[key] = data[key];
    }
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(safe));
  } catch { /* quota exceeded — ignore */ }
}

function loadSessionState(): Record<string, unknown> | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function ResultsScreen() {
  const location = useLocation();
  const navigate = useNavigate();
  const locationState = location.state as {
    explainResponse?: ExplainResponse;
    fromHistory?: boolean;
    extractionResult?: ExtractionResult;
    templateId?: number;
    historyId?: string | number;
    historyLiked?: boolean;
    clinicalContext?: string;
    quickReasons?: string[];
    letterMode?: boolean;
    letterId?: string | number;
    letterContent?: string;
    letterPrompt?: string;
    batchResponses?: ExplainResponse[];
    batchLabels?: string[];
  } | null;

  // Restore from sessionStorage if location.state is empty (e.g. after Settings round-trip).
  const session = locationState?.explainResponse ? null : loadSessionState();
  const initialResponse = (locationState?.explainResponse
    ?? session?.explainResponse as ExplainResponse | undefined) ?? null;
  const fromHistory = locationState?.fromHistory ?? (session?.fromHistory as boolean | undefined) ?? false;
  const extractionResult = (locationState?.extractionResult
    ?? session?.extractionResult as ExtractionResult | undefined) ?? null;
  const templateId = locationState?.templateId ?? (session?.templateId as number | undefined);
  const clinicalContext = locationState?.clinicalContext ?? (session?.clinicalContext as string | undefined);
  const quickReasons = locationState?.quickReasons ?? (session?.quickReasons as string[] | undefined);

  // Batch mode state
  const batchResponses = locationState?.batchResponses;
  const batchLabels = locationState?.batchLabels;
  const isBatchMode = batchResponses != null && batchResponses.length > 1;
  const [activeResultTab, setActiveResultTab] = useState(0);

  // Letter mode state
  const letterMode = locationState?.letterMode ?? false;
  const [letterContent, setLetterContent] = useState(locationState?.letterContent ?? "");
  const [letterPrompt] = useState(locationState?.letterPrompt ?? "");
  const [letterId] = useState(locationState?.letterId ?? null);
  const [isRefiningLetter, setIsRefiningLetter] = useState(false);
  const [letterRefineText, setLetterRefineText] = useState("");

  const { showToast, showUndoToast } = useToast();
  const [currentResponse, setCurrentResponse] = useState<ExplainResponse | null>(initialResponse);
  const [glossary, setGlossary] = useState<Record<string, string>>({});
  const [isExporting, setIsExporting] = useState(false);
  const [isLiked, setIsLiked] = useState(
    locationState?.historyLiked ?? (session?.historyLiked as boolean | undefined) ?? false,
  );
  const [historyId, setHistoryId] = useState<string | number | null>(
    locationState?.historyId ?? (session?.historyId as string | number | undefined) ?? null,
  );
  const [qualityRating, setQualityRating] = useState<number | null>(null);
  const [sectionSettings, setSectionSettings] = useState({
    include_key_findings: true,
    include_measurements: true,
    practice_name: null as string | null,
    footer_type: "explify_branding" as FooterType,
    custom_footer_text: null as string | null,
  });
  const [toneSlider, setToneSlider] = useState(3);
  const [detailSlider, setDetailSlider] = useState(3);
  const [isSpanish, setIsSpanish] = useState(false);

  // Comment panel state
  const [commentMode, setCommentMode] = useState<"long" | "short" | "sms">("short");
  const [shortCommentText, setShortCommentText] = useState<string | null>(
    initialResponse?.explanation?.overall_summary ?? null,
  );
  const [longExplanationResponse, setLongExplanationResponse] = useState<ExplainResponse | null>(null);
  const [isGeneratingComment, setIsGeneratingComment] = useState(false);
  const [isGeneratingLong, setIsGeneratingLong] = useState(false);

  // SMS summary state
  const [smsText, setSmsText] = useState<string | null>(null);
  const [isGeneratingSms, setIsGeneratingSms] = useState(false);
  const [smsEnabled, setSmsEnabled] = useState(false);

  // Deep analysis & mode toggles
  const [deepAnalysis, setDeepAnalysis] = useState(false);
  const [highAnxietyMode, setHighAnxietyMode] = useState(false);
  const [anxietyLevel, setAnxietyLevel] = useState(0);
  const [useAnalogies, setUseAnalogies] = useState(true);

  // Physician voice & attribution
  const [explanationVoice, setExplanationVoice] = useState<ExplanationVoice>("third_person");
  const [nameDrop, setNameDrop] = useState(true);
  const [practiceProviders, setPracticeProviders] = useState<string[]>([]);
  const [physicianOverride, setPhysicianOverride] = useState<string | null>(null);

  // Next steps
  const [nextStepsOptions, setNextStepsOptions] = useState<string[]>([]);
  const [checkedNextSteps, setCheckedNextSteps] = useState<Set<string>>(new Set(["No comment"]));

  // Refinement
  const [selectedLiteracy, setSelectedLiteracy] = useState<LiteracyLevel>("grade_8");
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [refinementInstruction, setRefinementInstruction] = useState("");

  // Edit state
  const [isEditing, setIsEditing] = useState(false);
  const [editedSummary, setEditedSummary] = useState("");
  const [editedFindings, setEditedFindings] = useState<{ finding: string; explanation: string }[]>([]);
  const [isDirty, setIsDirty] = useState(false);

  // Settings loaded flag
  const [settingsLoaded, setSettingsLoaded] = useState(false);

  // Extracted text state
  const [showExtractedText, setShowExtractedText] = useState(false);
  const [showReportType, setShowReportType] = useState(false);
  const [scrubbedText, setScrubbedText] = useState<string | null>(null);
  const [isScrubbing, setIsScrubbing] = useState(false);

  // Teaching points state
  const [teachingPoints, setTeachingPoints] = useState<TeachingPoint[]>([]);
  const [sharedTeachingPoints, setSharedTeachingPoints] = useState<SharedTeachingPoint[]>([]);
  const [newTeachingPoint, setNewTeachingPoint] = useState("");

  // Template selection
  const [templates, setTemplates] = useState<Template[]>([]);
  const [sharedTemplates, setSharedTemplates] = useState<SharedTemplate[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | number | undefined>(templateId);

  // Combined synthesis state (batch "All Together" tab)
  const [combinedSummary, setCombinedSummary] = useState<string | null>(null);
  const [isGeneratingCombined, setIsGeneratingCombined] = useState(false);
  const [combinedError, setCombinedError] = useState<string | null>(null);
  const [isEditingCombined, setIsEditingCombined] = useState(false);
  const [editedCombinedSummary, setEditedCombinedSummary] = useState("");

  // Type change modal state
  const [showTypeModal, setShowTypeModal] = useState(false);
  const [modalSelectedType, setModalSelectedType] = useState<string | null>(null);
  const [modalCustomType, setModalCustomType] = useState("");
  const [availableTypes, setAvailableTypes] = useState<TestTypeInfo[]>([]);

  const effectiveTestType = currentResponse?.parsed_report.test_type || "";
  const effectiveTestTypeDisplay = currentResponse?.parsed_report.test_type_display || "this type";

  // ---------------------------------------------------------------------------
  // Effects
  // ---------------------------------------------------------------------------

  // Sync edit state when response changes
  useEffect(() => {
    if (!currentResponse) return;
    const expl = currentResponse.explanation;

    setEditedSummary(expl.overall_summary);
    setEditedFindings(expl.key_findings.map((f) => ({ finding: f.finding, explanation: f.explanation })));
    setIsDirty(false);
    setIsEditing(false);
  }, [currentResponse]);

  // Draft clear is a no-op — drafts are in-memory only (HIPAA: no PHI in localStorage)
  const clearDraft = useCallback(() => {}, []);

  // Load glossary
  useEffect(() => {
    if (!currentResponse) return;
    sidecarApi
      .getGlossary(currentResponse.parsed_report.test_type)
      .then((res) => setGlossary(res.glossary))
      .catch(() => showToast("error", "Could not load glossary for tooltips."));
  }, [currentResponse, showToast]);

  // Load teaching points
  useEffect(() => {
    if (letterMode) {
      Promise.all([
        sidecarApi.listTeachingPoints(),
        sidecarApi.listSharedTeachingPoints().catch(() => [] as SharedTeachingPoint[]),
      ]).then(([pts, shared]) => { setTeachingPoints(pts); setSharedTeachingPoints(shared); }).catch(() => {});
      return;
    }
    if (!currentResponse) return;
    const testType = currentResponse.parsed_report.test_type;
    Promise.all([
      sidecarApi.listTeachingPoints(testType),
      sidecarApi.listSharedTeachingPoints(testType).catch(() => [] as SharedTeachingPoint[]),
    ]).then(([pts, shared]) => { setTeachingPoints(pts); setSharedTeachingPoints(shared); }).catch(() => {});
  }, [currentResponse, letterMode]);

  // Load templates + auto-select default for current test type
  useEffect(() => {
    Promise.all([
      sidecarApi.listTemplates(),
      sidecarApi.listSharedTemplates().catch(() => [] as SharedTemplate[]),
    ]).then(([res, shared]) => {
      setTemplates(res.items);
      setSharedTemplates(shared);
      // Auto-select default template if none was explicitly chosen
      if (selectedTemplateId == null && effectiveTestType) {
        const defaultTpl = res.items.find(
          (t) => t.is_default && t.test_type === effectiveTestType,
        );
        if (defaultTpl) setSelectedTemplateId(defaultTpl.id);
      }
    }).catch(() => {});
  }, []);

  // Load available test types for the change-type modal
  useEffect(() => {
    let cancelled = false;
    async function loadTypes(attempts = 3, backoffMs = 1000) {
      for (let i = 0; i < attempts; i++) {
        try {
          const types = await sidecarApi.listTestTypes();
          if (!cancelled && types.length > 0) {
            setAvailableTypes(types.map((t) => ({
              test_type_id: t.id,
              display_name: t.name,
              keywords: [],
              category: t.category,
            })));
            return;
          }
        } catch { /* retry */ }
        if (i < attempts - 1) {
          await new Promise((r) => setTimeout(r, backoffMs * (i + 1)));
        }
      }
    }
    loadTypes();
    return () => { cancelled = true; };
  }, []);

  // Load settings
  useEffect(() => {
    sidecarApi
      .getSettings()
      .then((s) => {
        setSectionSettings({
          include_key_findings: s.include_key_findings,
          include_measurements: s.include_measurements,
          practice_name: s.practice_name,
          footer_type: s.footer_type ?? "explify_branding",
          custom_footer_text: s.custom_footer_text,
        });
        setToneSlider(s.tone_preference);
        setDetailSlider(s.detail_preference);
        setSelectedLiteracy(s.literacy_level);
        setNextStepsOptions(s.next_steps_options ?? []);
        setExplanationVoice(s.explanation_voice ?? "third_person");
        setNameDrop(s.name_drop ?? true);
        setPracticeProviders(s.practice_providers ?? []);
        setSmsEnabled(s.sms_summary_enabled ?? false);
        setUseAnalogies(s.use_analogies ?? true);
        const defaultMode = s.default_comment_mode ?? "short";
        if (defaultMode === "sms" && s.sms_summary_enabled) {
          setCommentMode("sms");
        } else if (defaultMode === "long") {
          setCommentMode("long");
        } else {
          setCommentMode("short");
        }
        const src = s.physician_name_source ?? "auto_extract";
        if (src === "custom" && s.custom_physician_name) setPhysicianOverride(s.custom_physician_name);
        else if (src === "generic") setPhysicianOverride("");
        setSettingsLoaded(true);
      })
      .catch(() => setSettingsLoaded(true));
  }, []);

  // Session persistence
  useEffect(() => {
    if (!currentResponse) return;
    saveSessionState({
      fromHistory,
      templateId,
      historyId,
      historyLiked: isLiked,
    });
  }, [currentResponse, fromHistory, selectedTemplateId, historyId, isLiked]);

  // Batch tab switching
  useEffect(() => {
    if (!isBatchMode || !batchResponses) return;
    // If on combined tab (index === batchResponses.length), don't update individual report state
    if (activeResultTab >= batchResponses.length) return;
    setCurrentResponse(batchResponses[activeResultTab]);
    setShortCommentText(batchResponses[activeResultTab].explanation.overall_summary);
    setLongExplanationResponse(null);
    setSmsText(null);
    setIsDirty(false);
    setIsEditing(false);
  }, [activeResultTab, isBatchMode, batchResponses]);

  const canRefine = !fromHistory && extractionResult != null;

  // ---------------------------------------------------------------------------
  // Shared request params builder
  // ---------------------------------------------------------------------------
  const buildRequestParams = useCallback((overrides: Record<string, unknown> = {}) => ({
    extraction_result: extractionResult!,
    test_type: effectiveTestType,
    literacy_level: selectedLiteracy,
    template_id: selectedTemplateId,
    clinical_context: clinicalContext,
    tone_preference: toneSlider,
    detail_preference: detailSlider,
    next_steps: [...checkedNextSteps].filter(s => s !== "No comment"),
    explanation_voice: explanationVoice,
    name_drop: nameDrop,
    physician_name_override: physicianOverride !== null ? (physicianOverride || "") : undefined,
    deep_analysis: deepAnalysis || undefined,
    high_anxiety_mode: highAnxietyMode || undefined,
    anxiety_level: anxietyLevel || undefined,
    quick_reasons: quickReasons,
    use_analogies: useAnalogies,
    ...overrides,
  }), [extractionResult, effectiveTestType, selectedLiteracy, selectedTemplateId, clinicalContext, toneSlider, detailSlider, checkedNextSteps, explanationVoice, nameDrop, physicianOverride, deepAnalysis, highAnxietyMode, anxietyLevel, quickReasons, useAnalogies]);

  // ---------------------------------------------------------------------------
  // Callbacks
  // ---------------------------------------------------------------------------

  const handleRegenerate = useCallback(async () => {
    if (!extractionResult) return;
    if (isDirty && !window.confirm("Regenerating will overwrite your edits. Continue?")) return;
    setIsRegenerating(true);
    const isShort = commentMode === "short";
    const isSms = commentMode === "sms";
    try {
      const response = await sidecarApi.explainReport(buildRequestParams({
        short_comment: isShort,
        sms_summary: isSms,
        include_key_findings: (isShort || isSms) ? true : sectionSettings.include_key_findings,
        include_measurements: (isShort || isSms) ? true : sectionSettings.include_measurements,
        refinement_instruction: refinementInstruction.trim() || undefined,
      }));
      if (isSms) setSmsText(response.explanation.overall_summary);
      else if (isShort) setShortCommentText(response.explanation.overall_summary);
      else setLongExplanationResponse(response);
      setCurrentResponse(response);
      logUsage({ model_used: response.model_used, input_tokens: response.input_tokens, output_tokens: response.output_tokens, request_type: "explain", deep_analysis: deepAnalysis });
      // Clear combined summary so it re-generates with updated data
      setCombinedSummary(null);
      setIsDirty(false);
      setIsEditing(false);
      showToast("success", "Explanation regenerated.");
    } catch {
      showToast("error", "Failed to regenerate explanation.");
    } finally {
      setIsRegenerating(false);
    }
  }, [extractionResult, commentMode, buildRequestParams, sectionSettings, refinementInstruction, deepAnalysis, isDirty, showToast]);

  const handleOpenChangeType = useCallback(() => {
    setModalSelectedType(effectiveTestType || null);
    setModalCustomType("");
    setShowTypeModal(true);
  }, [effectiveTestType]);

  const handleConfirmTypeChange = useCallback(async (newTestType: string) => {
    if (!extractionResult) return;
    setShowTypeModal(false);
    setIsRegenerating(true);
    const isShort = commentMode === "short";
    const isSms = commentMode === "sms";
    try {
      const response = await sidecarApi.explainReport(buildRequestParams({
        test_type: newTestType,
        short_comment: isShort,
        sms_summary: isSms,
        include_key_findings: (isShort || isSms) ? true : sectionSettings.include_key_findings,
        include_measurements: (isShort || isSms) ? true : sectionSettings.include_measurements,
        refinement_instruction: refinementInstruction.trim() || undefined,
      }));
      if (isSms) setSmsText(response.explanation.overall_summary);
      else if (isShort) setShortCommentText(response.explanation.overall_summary);
      else setLongExplanationResponse(response);
      setCurrentResponse(response);
      logUsage({ model_used: response.model_used, input_tokens: response.input_tokens, output_tokens: response.output_tokens, request_type: "explain", deep_analysis: deepAnalysis });
      setCombinedSummary(null);
      showToast("success", `Type changed to ${response.parsed_report.test_type_display || newTestType}. Explanation regenerated.`);
    } catch {
      showToast("error", "Failed to regenerate with new type.");
    } finally {
      setIsRegenerating(false);
    }
  }, [extractionResult, commentMode, buildRequestParams, sectionSettings, refinementInstruction, deepAnalysis, showToast]);

  const handleTranslateToggle = useCallback(async () => {
    const translatingToSpanish = !isSpanish;

    if (letterMode) {
      setIsRefiningLetter(true);
      try {
        const translatePrompt = translatingToSpanish
          ? `${letterPrompt}\n\nTranslate the entire letter into Spanish. Keep all medical values and units in their original form. Use simple, patient-friendly Spanish.`
          : letterPrompt;
        const refined = await sidecarApi.generateLetter({ prompt: translatePrompt, letter_type: "general" });
        setLetterContent(refined.content);
        setIsSpanish(translatingToSpanish);
        showToast("success", translatingToSpanish ? "Translated to Spanish." : "Translated to English.");
      } catch {
        showToast("error", "Failed to translate letter.");
      } finally {
        setIsRefiningLetter(false);
      }
      return;
    }

    if (!extractionResult) return;
    setIsRegenerating(true);
    const isShort = commentMode === "short";
    const isSms = commentMode === "sms";
    try {
      const response = await sidecarApi.explainReport(buildRequestParams({
        short_comment: isShort,
        sms_summary: isSms,
        include_key_findings: (isShort || isSms) ? true : sectionSettings.include_key_findings,
        include_measurements: (isShort || isSms) ? true : sectionSettings.include_measurements,
        refinement_instruction: translatingToSpanish
          ? "Translate the entire explanation into Spanish. Keep all medical values and units in their original form. Use simple, patient-friendly Spanish."
          : undefined,
      }));
      if (isSms) setSmsText(response.explanation.overall_summary);
      else if (isShort) setShortCommentText(response.explanation.overall_summary);
      else setLongExplanationResponse(response);
      setCurrentResponse(response);
      logUsage({ model_used: response.model_used, input_tokens: response.input_tokens, output_tokens: response.output_tokens, request_type: "explain", deep_analysis: deepAnalysis });
      setIsSpanish(translatingToSpanish);
      showToast("success", translatingToSpanish ? "Translated to Spanish." : "Translated to English.");
    } catch {
      showToast("error", "Failed to translate explanation.");
    } finally {
      setIsRegenerating(false);
    }
  }, [extractionResult, commentMode, isSpanish, buildRequestParams, sectionSettings, deepAnalysis, showToast, letterMode, letterPrompt]);

  const handleExportPdf = useCallback(async () => {
    if (!currentResponse) return;
    setIsExporting(true);
    try {
      const blob = await sidecarApi.exportPdf(currentResponse);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "explify-report.pdf";
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

  const computedFooter = (() => {
    if (!settingsLoaded) return "";
    switch (sectionSettings.footer_type) {
      case "explify_branding":
        return sectionSettings.practice_name
          ? `Powered by Explify, refined by ${sectionSettings.practice_name}.`
          : "Powered by Explify.";
      case "ai_disclaimer":
        return "This summary was generated with AI assistance and reviewed by your healthcare provider. It is intended for informational purposes only and does not replace professional medical advice.";
      case "custom":
        return sectionSettings.custom_footer_text ?? "";
      case "none":
        return "";
    }
  })();

  const handleToggleLike = useCallback(async () => {
    if (!currentResponse) return;
    let id = historyId;
    try {
      if (id == null) {
        const detail = await sidecarApi.saveHistory({
          test_type: effectiveTestType,
          test_type_display: currentResponse.parsed_report.test_type_display,
          filename: null,
          summary: (currentResponse.explanation.overall_summary || "").slice(0, 200),
          full_response: currentResponse,
          tone_preference: toneSlider,
          detail_preference: detailSlider,
        });
        id = detail.id;
        setHistoryId(id);
        queueUpsertAfterMutation("history", id).catch(() => {});
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      showToast("error", `Failed to save report: ${msg}`);
      return;
    }
    try {
      const newLiked = !isLiked;
      await sidecarApi.toggleHistoryLiked(id, newLiked);
      setIsLiked(newLiked);
      queueUpsertAfterMutation("history", id).catch(() => {});
      showToast("success", newLiked ? "Will process more like this in the future." : "Like removed.");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      showToast("error", `Failed to update like status: ${msg}`);
    }
  }, [currentResponse, historyId, isLiked, effectiveTestType, toneSlider, detailSlider, showToast]);

  const handleRate = useCallback(async (rating: number, note?: string) => {
    if (!historyId) {
      showToast("error", "Save the report first to rate it.");
      return;
    }
    try {
      await sidecarApi.rateHistory(historyId, rating, note);
      setQualityRating(rating);
      showToast("success", rating >= 4
        ? `Rated ${rating}/5 \u2014 this helps personalize future results`
        : note
          ? `Feedback saved \u2014 future results will reflect your input`
          : `Rated ${rating}/5. Add a note to help us improve.`);
    } catch {
      showToast("error", "Failed to save rating.");
    }
  }, [historyId, showToast]);

  const markDirty = () => { if (!isDirty) setIsDirty(true); };

  // On-demand comment generators
  const generateShortComment = useCallback(async () => {
    if (!extractionResult || !currentResponse) return;
    setIsGeneratingComment(true);
    try {
      const response = await sidecarApi.explainReport(buildRequestParams({
        short_comment: true,
        include_key_findings: true,
        include_measurements: true,
      }));
      setShortCommentText(response.explanation.overall_summary);
      logUsage({ model_used: response.model_used, input_tokens: response.input_tokens, output_tokens: response.output_tokens, request_type: "explain", deep_analysis: deepAnalysis });
    } catch {
      showToast("error", "Failed to generate short comment.");
    } finally {
      setIsGeneratingComment(false);
    }
  }, [extractionResult, currentResponse, buildRequestParams, deepAnalysis, showToast]);

  const generateLongExplanation = useCallback(async () => {
    if (!extractionResult || !currentResponse) return;
    setIsGeneratingLong(true);
    try {
      const response = await sidecarApi.explainReport(buildRequestParams({
        short_comment: false,
        include_key_findings: sectionSettings.include_key_findings,
        include_measurements: sectionSettings.include_measurements,
        refinement_instruction: refinementInstruction.trim() || undefined,
      }));
      setLongExplanationResponse(response);
      logUsage({ model_used: response.model_used, input_tokens: response.input_tokens, output_tokens: response.output_tokens, request_type: "explain", deep_analysis: deepAnalysis });
    } catch {
      showToast("error", "Failed to generate detailed explanation.");
    } finally {
      setIsGeneratingLong(false);
    }
  }, [extractionResult, currentResponse, buildRequestParams, sectionSettings, refinementInstruction, deepAnalysis, showToast]);

  const generateSmsText = useCallback(async () => {
    if (!extractionResult || !currentResponse) return;
    setIsGeneratingSms(true);
    try {
      const response = await sidecarApi.explainReport(buildRequestParams({
        sms_summary: true,
        include_key_findings: true,
        include_measurements: true,
      }));
      setSmsText(response.explanation.overall_summary);
      logUsage({ model_used: response.model_used, input_tokens: response.input_tokens, output_tokens: response.output_tokens, request_type: "explain", deep_analysis: deepAnalysis });
    } catch {
      setSmsText("");
      showToast("error", "Failed to generate SMS summary.");
    } finally {
      setIsGeneratingSms(false);
    }
  }, [extractionResult, currentResponse, buildRequestParams, deepAnalysis, showToast]);

  const generateCombinedSummary = useCallback(async () => {
    if (!batchResponses || batchResponses.length < 2) return;
    setIsGeneratingCombined(true);
    setCombinedError(null);
    try {
      const result = await sidecarApi.synthesizeReports(
        batchResponses,
        batchLabels || batchResponses.map((_, i) => `Report ${i + 1}`),
        clinicalContext,
      );
      setCombinedSummary(result.combined_summary);
      setEditedCombinedSummary(result.combined_summary);
      logUsage({
        model_used: result.model_used,
        input_tokens: result.input_tokens,
        output_tokens: result.output_tokens,
        request_type: "synthesize",
      });
    } catch (err) {
      setCombinedError(
        err instanceof Error ? err.message : "Failed to generate combined summary",
      );
    } finally {
      setIsGeneratingCombined(false);
    }
  }, [batchResponses, batchLabels, clinicalContext]);

  // Auto-generate on tab switch
  useEffect(() => {
    if (commentMode === "short" && shortCommentText === null && extractionResult && currentResponse && !isGeneratingComment) generateShortComment();
  }, [commentMode, shortCommentText, extractionResult, currentResponse, isGeneratingComment, generateShortComment]);

  useEffect(() => {
    if (commentMode === "long" && longExplanationResponse === null && extractionResult && currentResponse && !isGeneratingLong) generateLongExplanation();
  }, [commentMode, longExplanationResponse, extractionResult, currentResponse, isGeneratingLong, generateLongExplanation]);

  useEffect(() => {
    if (commentMode === "sms" && smsText === null && extractionResult && currentResponse && !isGeneratingSms) generateSmsText();
  }, [commentMode, smsText, extractionResult, currentResponse, isGeneratingSms, generateSmsText]);

  // Compute preview text
  const commentPreviewText = (() => {
    const physician = physicianOverride ?? currentResponse?.physician_name;
    if (commentMode === "sms") return replacePhysician(smsText ?? "", physician);
    if (commentMode === "short") {
      const base = replacePhysician(shortCommentText ?? "", physician);
      return computedFooter ? base + "\n\n" + computedFooter : base;
    }
    const longSource = longExplanationResponse ?? currentResponse;
    if (!longSource) return "";
    const expl = longSource.explanation;
    const summary = replacePhysician(isDirty ? editedSummary : expl.overall_summary, physician);
    const findings = (isDirty ? editedFindings : expl.key_findings).map((f) => ({
      finding: f.finding,
      explanation: replacePhysician(f.explanation, physician),
    }));
    return buildCopyText(summary, findings, expl.measurements, computedFooter, sectionSettings.include_key_findings, sectionSettings.include_measurements, [...checkedNextSteps]);
  })();

  const handleCopyComment = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(commentPreviewText);
      showToast("success", "Copied to clipboard.");
      if (historyId) {
        sidecarApi.markHistoryCopied(historyId).catch(() => {});
        if (isDirty && commentMode === "long") sidecarApi.saveEditedText(historyId, editedSummary).catch(() => {});
      }
      clearDraft();
    } catch {
      showToast("error", "Failed to copy to clipboard.");
    }
  }, [commentPreviewText, showToast, historyId, isDirty, commentMode, editedSummary, clearDraft]);

  const handleCopyLetter = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(letterContent);
      showToast("success", "Copied to clipboard.");
    } catch {
      showToast("error", "Failed to copy to clipboard.");
    }
  }, [letterContent, showToast]);

  const handleLikeLetter = useCallback(async () => {
    if (letterId == null) return;
    const newLiked = !isLiked;
    try {
      await sidecarApi.toggleLetterLiked(letterId, newLiked);
      setIsLiked(newLiked);
      showToast("success", newLiked ? "Letter liked." : "Like removed.");
    } catch {
      showToast("error", "Failed to update like status.");
    }
  }, [letterId, isLiked, showToast]);

  const handleRefineLetter = useCallback(async () => {
    setIsRefiningLetter(true);
    try {
      const parts = [letterPrompt];
      if (refinementInstruction.trim()) parts.push(`\n\nRefinement: ${refinementInstruction.trim()}`);
      if (letterRefineText.trim()) parts.push(`\n\nAdditional refinement: ${letterRefineText.trim()}`);
      const refined = await sidecarApi.generateLetter({ prompt: parts.join(""), letter_type: "general" });
      setLetterContent(refined.content);
      setLetterRefineText("");
      showToast("success", "Letter refined.");
    } catch {
      showToast("error", "Failed to refine letter.");
    } finally {
      setIsRefiningLetter(false);
    }
  }, [letterPrompt, letterRefineText, refinementInstruction, showToast]);

  const handleEditFinding = useCallback((index: number, field: "finding" | "explanation", value: string) => {
    const updated = [...editedFindings];
    updated[index] = { ...updated[index], [field]: value };
    setEditedFindings(updated);
    markDirty();
  }, [editedFindings]);

  // ---------------------------------------------------------------------------
  // Shared sidebar props
  // ---------------------------------------------------------------------------
  const sidebarProps = {
    refinementInstruction,
    setRefinementInstruction,
    selectedTemplateId,
    setSelectedTemplateId,
    templates,
    sharedTemplates,
    selectedLiteracy,
    setSelectedLiteracy,
    toneSlider,
    setToneSlider,
    detailSlider,
    setDetailSlider,
    highAnxietyMode,
    setHighAnxietyMode,
    anxietyLevel,
    setAnxietyLevel,
    useAnalogies,
    setUseAnalogies,
    deepAnalysis,
    setDeepAnalysis,
    sectionSettings,
    setSectionSettings,
    explanationVoice,
    setExplanationVoice,
    nameDrop,
    setNameDrop,
    practiceProviders,
    physicianOverride,
    setPhysicianOverride,
    currentResponse,
    nextStepsOptions,
    checkedNextSteps,
    setCheckedNextSteps,
    isRegenerating,
    isSpanish,
    onRegenerate: handleRegenerate,
    onTranslateToggle: handleTranslateToggle,
    extractionResult,
    showExtractedText,
    setShowExtractedText,
    showReportType,
    setShowReportType,
    scrubbedText,
    setScrubbedText,
    isScrubbing,
    setIsScrubbing,
  } as const;

  const teachingProps = {
    teachingPoints,
    setTeachingPoints,
    sharedTeachingPoints,
    newTeachingPoint,
    setNewTeachingPoint,
    effectiveTestType,
    effectiveTestTypeDisplay,
    showToast,
    showUndoToast,
  } as const;

  // ---------------------------------------------------------------------------
  // Letter mode render
  // ---------------------------------------------------------------------------
  if (letterMode) {
    return (
      <div className="results-screen">
        <div className="results-main-panel">
          <header className="results-header">
            <h2 className="results-title">Generated Letter</h2>
          </header>

          <div className="refine-toolbar">
            <button
              className="refine-btn"
              onClick={handleRefineLetter}
              disabled={isRefiningLetter}
            >
              {isRefiningLetter ? "Regenerating\u2026" : "Regenerate"}
            </button>
          </div>

          <div className="results-comment-panel">
            <div className="comment-panel-header">
              <h3>Result Comment</h3>
              <button
                className={`like-btn${isLiked ? " like-btn--active" : ""}`}
                onClick={handleLikeLetter}
              >
                {isLiked ? "\u2665 Liked" : "\u2661 Like"}
              </button>
            </div>
            {isRefiningLetter ? (
              <div className="comment-generating">Generating...</div>
            ) : (
              <div className="comment-preview">{letterContent}</div>
            )}
            <span className="comment-char-count">{letterContent.length} chars</span>
            <button className="comment-copy-btn" onClick={handleCopyLetter}>
              Copy to Clipboard
            </button>
          </div>

          <TeachingPointsPanel {...teachingProps} letterMode />

          <div className="results-nav-buttons">
            <button
              className="results-back-btn results-back-btn--tertiary"
              onClick={() => navigate("/")}
            >
              Back to Import
            </button>
            <button
              className="results-back-btn results-back-btn--secondary"
              onClick={() => {
                navigate("/", { state: { preservedClinicalContext: clinicalContext, preservedQuickReasons: quickReasons } });
              }}
            >
              New Report, Same Patient
            </button>
            <button className="results-back-btn" onClick={() => {
              clearImportCache();
              try { sessionStorage.removeItem("explify_results_state"); } catch { /* ignore */ }
              navigate("/");
            }}>
              Start Fresh (New Patient)
            </button>
          </div>
        </div>

        <RefinementSidebar
          {...sidebarProps}
          letterMode
          isRefiningLetter={isRefiningLetter}
          onRefineLetter={handleRefineLetter}
        />
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // No results render
  // ---------------------------------------------------------------------------
  if (!currentResponse) {
    return (
      <div className="results-main-panel">
        <h2 className="results-title">No Results</h2>
        <p className="results-empty">
          No analysis results found. Please import and process a report first.
        </p>
        <button className="results-back-btn" onClick={() => navigate("/")}>
          Back to Import
        </button>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Report mode render
  // ---------------------------------------------------------------------------
  const { explanation, parsed_report } = currentResponse;
  const activePhysician = physicianOverride ?? currentResponse?.physician_name;
  const rawFindings = isDirty
    ? editedFindings.map((f, i) => ({
        ...(explanation.key_findings[i] ?? { severity: "informational" }),
        finding: f.finding,
        explanation: f.explanation,
      }))
    : explanation.key_findings;
  const displayFindings = rawFindings.map((f) => ({
    ...f,
    explanation: replacePhysician(f.explanation, activePhysician),
  }));
  const measurementMap = new Map<string, ParsedMeasurement>();
  if (parsed_report.measurements) {
    for (const m of parsed_report.measurements) {
      measurementMap.set(m.abbreviation, m);
    }
  }

  return (
    <div className={`results-screen${!canRefine ? " results-screen--single-column" : ""}`}>
      <div className="results-main-panel">
        <header className="results-header">
          <h2 className="results-title">Explanation</h2>
          {fromHistory && <span className="results-from-history">Viewed from history</span>}
        </header>

        {isBatchMode && batchResponses && (
          <div className="results-batch-tabs">
            {batchResponses.map((_, idx) => (
              <button
                key={idx}
                className={`results-batch-tab${idx === activeResultTab ? " results-batch-tab--active" : ""}`}
                onClick={() => setActiveResultTab(idx)}
              >
                {batchLabels?.[idx] || `Report ${idx + 1}`}
              </button>
            ))}
            <button
              className={`results-batch-tab results-batch-tab--combined${activeResultTab === batchResponses.length ? " results-batch-tab--active" : ""}`}
              onClick={() => {
                setActiveResultTab(batchResponses.length);
                if (!combinedSummary && !isGeneratingCombined) {
                  generateCombinedSummary();
                }
              }}
            >
              All Together
            </button>
          </div>
        )}

        {isBatchMode && batchResponses && activeResultTab === batchResponses.length ? (
          /* Combined "All Together" tab view */
          <div className="combined-summary-panel">
            {isGeneratingCombined && (
              <div className="combined-summary-loading">
                <div className="spinner" />
                <span>Generating combined summary...</span>
              </div>
            )}
            {combinedError && (
              <div className="import-error">
                <p>{combinedError}</p>
                <button className="refine-btn" onClick={generateCombinedSummary}>
                  Retry
                </button>
              </div>
            )}
            {combinedSummary && !isGeneratingCombined && (
              <>
                <div className="combined-summary-header">
                  <h3>Combined Summary</h3>
                </div>
                {isEditingCombined ? (
                  <textarea
                    className="summary-textarea"
                    autoComplete="off"
                    value={editedCombinedSummary}
                    onChange={(e) => setEditedCombinedSummary(e.target.value)}
                    rows={12}
                  />
                ) : (
                  <div className="comment-preview">
                    {editedCombinedSummary}
                  </div>
                )}
                <span className="comment-char-count">
                  {editedCombinedSummary.length} chars
                </span>
                <div className="combined-summary-actions">
                  <button
                    className="comment-copy-btn"
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText(editedCombinedSummary);
                        showToast("success", "Combined summary copied.");
                      } catch {
                        showToast("error", "Failed to copy.");
                      }
                    }}
                  >
                    Copy to Clipboard
                  </button>
                  <button
                    className={`edit-toggle-btn${isEditingCombined ? " edit-toggle-btn--active" : ""}`}
                    onClick={() => setIsEditingCombined(!isEditingCombined)}
                  >
                    {isEditingCombined ? "Done Editing" : "Edit"}
                  </button>
                  <button
                    className="refine-btn"
                    onClick={generateCombinedSummary}
                    disabled={isGeneratingCombined}
                  >
                    Regenerate
                  </button>
                </div>
              </>
            )}
          </div>
        ) : (
          /* Individual report tab view */
          <>
            {canRefine && (
              <div className="refine-toolbar">
                <button className="refine-btn" onClick={handleRegenerate} disabled={isRegenerating}>
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

            <CommentPanel
              commentMode={commentMode}
              setCommentMode={setCommentMode}
              isEditing={isEditing}
              editedSummary={editedSummary}
              setEditedSummary={setEditedSummary}
              onMarkDirty={markDirty}
              commentPreviewText={commentPreviewText}
              isGeneratingComment={isGeneratingComment}
              isGeneratingLong={isGeneratingLong}
              isGeneratingSms={isGeneratingSms}
              onCopy={handleCopyComment}
              onExportPdf={handleExportPdf}
              isExporting={isExporting}
              isLiked={isLiked}
              onToggleLike={handleToggleLike}
              smsEnabled={smsEnabled}
              testTypeDisplay={effectiveTestTypeDisplay}
              onChangeType={canRefine ? handleOpenChangeType : undefined}
              qualityRating={qualityRating}
              onRate={handleRate}
            />

            {sectionSettings.include_key_findings && (
              <KeyFindingsPanel
                findings={displayFindings}
                isEditing={isEditing}
                editedFindings={editedFindings}
                onEditFinding={handleEditFinding}
                glossary={glossary}
              />
            )}

            {sectionSettings.include_measurements && (
              <MeasurementsTable
                measurements={explanation.measurements}
                measurementMap={measurementMap}
                glossary={glossary}
              />
            )}

            <footer className="results-footer">
              <span className="results-meta">
                Model: {currentResponse.model_used} | Tokens:{" "}
                {currentResponse.input_tokens} in / {currentResponse.output_tokens} out
              </span>
              {(() => {
                const pm = currentResponse.personalization_metadata;
                if (!pm) return null;
                const parts: string[] = [];
                if (pm.style_sample_count) parts.push(`${pm.style_sample_count} reports`);
                if (pm.edit_corrections_count) parts.push(`${pm.edit_corrections_count} edits`);
                if (pm.feedback_adjustments_count) parts.push(`${pm.feedback_adjustments_count} feedback`);
                if (pm.vocab_preferences_count) parts.push(`${pm.vocab_preferences_count} vocab`);
                if (pm.term_preferences_count) parts.push(`${pm.term_preferences_count} terms`);
                if (pm.liked_examples_count) parts.push(`${pm.liked_examples_count} liked`);
                if (parts.length === 0) return null;
                return (
                  <span className="results-personalization">
                    {"\u2728"} Personalized &mdash; learned from {parts.join(", ")}
                  </span>
                );
              })()}
              {currentResponse.validation_warnings.length > 0 && (
                <details className="validation-warnings">
                  <summary>Validation Warnings ({currentResponse.validation_warnings.length})</summary>
                  <ul>
                    {currentResponse.validation_warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </details>
              )}
            </footer>

            <TeachingPointsPanel {...teachingProps} />
          </>
        )}

        <div className="results-nav-buttons">
          <button
            className="results-back-btn results-back-btn--tertiary"
            onClick={() => {
              if (isDirty && !window.confirm("You have unsaved edits. Leave anyway?")) return;
              navigate("/");
            }}
          >
            Back to Import
          </button>
          <button
            className="results-back-btn results-back-btn--secondary"
            onClick={() => {
              if (isDirty && !window.confirm("You have unsaved edits. Leave anyway?")) return;
              navigate("/", { state: { preservedClinicalContext: clinicalContext, preservedQuickReasons: quickReasons } });
            }}
          >
            New Report, Same Patient
          </button>
          <button
            className="results-back-btn"
            onClick={() => {
              if (isDirty && !window.confirm("You have unsaved edits. Leave anyway?")) return;
              clearImportCache();
              try { sessionStorage.removeItem("explify_results_state"); } catch { /* ignore */ }
              navigate("/");
            }}
          >
            Start Fresh (New Patient)
          </button>
        </div>
      </div>

      {canRefine && <RefinementSidebar {...sidebarProps} />}

      {/* Type Change Modal */}
      {showTypeModal && (
        <div className="type-modal-backdrop" onClick={() => setShowTypeModal(false)}>
          <div className="type-modal" onClick={(e) => e.stopPropagation()}>
            <h3 className="type-modal-title">Change Report Type</h3>
            <p className="type-modal-subtitle">
              Currently identified as <strong>{effectiveTestTypeDisplay}</strong>.
              Select a different type to regenerate the explanation.
            </p>

            {availableTypes.length > 0 && (
              <div className="type-modal-categories">
                {groupTypesByCategory(availableTypes).map(([label, types]) => (
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
                autoComplete="off"
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
                onClick={() => setShowTypeModal(false)}
              >
                Cancel
              </button>
              <button
                className="type-modal-confirm"
                disabled={!modalSelectedType && !modalCustomType.trim()}
                onClick={() => {
                  const chosen = modalCustomType.trim() || modalSelectedType;
                  if (chosen) handleConfirmTypeChange(chosen);
                }}
              >
                Confirm &amp; Regenerate
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
