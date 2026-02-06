import { useEffect, useState, useCallback } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import type {
  ExplainResponse,
  ExtractionResult,
  MeasurementExplanation,
  FindingExplanation,
  ParsedMeasurement,
  LiteracyLevel,
  ExplanationVoice,
  FooterType,
  TeachingPoint,
  SharedTeachingPoint,
} from "../../types/sidecar";
import { sidecarApi } from "../../services/sidecarApi";
import { logUsage } from "../../services/usageTracker";
import { queueUpsertAfterMutation } from "../../services/syncEngine";
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

const TONE_LABELS = ["", "Concerning", "Straightforward", "Neutral", "Reassuring", "Very Reassuring"];
const DETAIL_LABELS = ["", "Minimal", "Concise", "Moderate", "Detailed", "Very Detailed"];

const LITERACY_OPTIONS: { value: LiteracyLevel; label: string }[] = [
  { value: "grade_4", label: "Grade 4" },
  { value: "grade_6", label: "Grade 6" },
  { value: "grade_8", label: "Grade 8" },
  { value: "grade_12", label: "Grade 12" },
  { value: "clinical", label: "Clinical" },
];

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

const SESSION_KEY = "explify_results_state";

function saveSessionState(data: Record<string, unknown>) {
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(data));
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
    historyId?: number;
    historyLiked?: boolean;
    clinicalContext?: string;
    letterMode?: boolean;
    letterId?: number;
    letterContent?: string;
    letterPrompt?: string;
  } | null;

  // Restore from sessionStorage if location.state is empty (e.g. after Settings round-trip).
  // If locationState carries a fresh explainResponse, this is a NEW report — ignore stale session.
  const session = locationState?.explainResponse ? null : loadSessionState();
  const initialResponse = (locationState?.explainResponse
    ?? session?.explainResponse as ExplainResponse | undefined) ?? null;
  const fromHistory = locationState?.fromHistory ?? (session?.fromHistory as boolean | undefined) ?? false;
  const extractionResult = (locationState?.extractionResult
    ?? session?.extractionResult as ExtractionResult | undefined) ?? null;
  const templateId = locationState?.templateId ?? (session?.templateId as number | undefined);
  const clinicalContext = locationState?.clinicalContext ?? (session?.clinicalContext as string | undefined);

  // Letter mode state
  const letterMode = locationState?.letterMode ?? false;
  const [letterContent, setLetterContent] = useState(locationState?.letterContent ?? "");
  const [letterPrompt] = useState(locationState?.letterPrompt ?? "");
  const [letterId] = useState(locationState?.letterId ?? null);
  const [isRefiningLetter, setIsRefiningLetter] = useState(false);
  const [letterRefineText, setLetterRefineText] = useState("");

  const { showToast } = useToast();
  const [currentResponse, setCurrentResponse] =
    useState<ExplainResponse | null>(initialResponse);
  const [glossary, setGlossary] = useState<Record<string, string>>({});
  const [isExporting, setIsExporting] = useState(false);
  const [isLiked, setIsLiked] = useState(
    locationState?.historyLiked ?? (session?.historyLiked as boolean | undefined) ?? false,
  );
  const [historyId, setHistoryId] = useState<number | null>(
    locationState?.historyId ?? (session?.historyId as number | undefined) ?? null,
  );
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

  // Comment panel state — default to short since that's what we generate first
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

  // Deep analysis state
  const [deepAnalysis, setDeepAnalysis] = useState(false);

  // Physician voice & attribution state
  const [explanationVoice, setExplanationVoice] = useState<ExplanationVoice>("third_person");
  const [nameDrop, setNameDrop] = useState(true);
  const [practiceProviders, setPracticeProviders] = useState<string[]>([]);
  const [physicianOverride, setPhysicianOverride] = useState<string | null>(null);

  // Next steps state
  const [nextStepsOptions, setNextStepsOptions] = useState<string[]>([]);
  const [checkedNextSteps, setCheckedNextSteps] = useState<Set<string>>(
    new Set(["No comment"]),
  );

  // Refinement state
  const [selectedLiteracy, setSelectedLiteracy] =
    useState<LiteracyLevel>("grade_8");
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [refinementInstruction, setRefinementInstruction] = useState("");

  // Edit state
  const [isEditing, setIsEditing] = useState(false);
  const [editedSummary, setEditedSummary] = useState("");
  const [editedFindings, setEditedFindings] = useState<
    { finding: string; explanation: string }[]
  >([]);
  const [isDirty, setIsDirty] = useState(false);

  // Settings loaded flag — gate footer rendering until we have real values
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

  // Test type override — lets the user correct a misdetected type
  const [testTypeOverride, setTestTypeOverride] = useState<string | null>(null);
  const effectiveTestType = testTypeOverride?.trim() || currentResponse?.parsed_report.test_type || "";
  const effectiveTestTypeDisplay = testTypeOverride?.trim()
    ? testTypeOverride.trim().replace(/\b\w/g, (c) => c.toUpperCase())
    : currentResponse?.parsed_report.test_type_display || "this type";

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

  useEffect(() => {
    if (letterMode) {
      // In letter mode, load global teaching points (no test type filter)
      Promise.all([
        sidecarApi.listTeachingPoints(),
        sidecarApi.listSharedTeachingPoints().catch(() => [] as SharedTeachingPoint[]),
      ]).then(([pts, shared]) => {
        setTeachingPoints(pts);
        setSharedTeachingPoints(shared);
      }).catch(() => {});
      return;
    }
    if (!currentResponse) return;
    const testType = currentResponse.parsed_report.test_type;
    Promise.all([
      sidecarApi.listTeachingPoints(testType),
      sidecarApi.listSharedTeachingPoints(testType).catch(() => [] as SharedTeachingPoint[]),
    ]).then(([pts, shared]) => {
      setTeachingPoints(pts);
      setSharedTeachingPoints(shared);
    }).catch(() => {});
  }, [currentResponse, letterMode]);

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
        const src = s.physician_name_source ?? "auto_extract";
        if (src === "custom" && s.custom_physician_name) {
          setPhysicianOverride(s.custom_physician_name);
        } else if (src === "generic") {
          setPhysicianOverride("");
        }
        setSettingsLoaded(true);
      })
      .catch(() => {
        setSettingsLoaded(true);
      });
  }, []);

  // Persist state to sessionStorage so it survives Settings round-trips
  useEffect(() => {
    if (!currentResponse) return;
    saveSessionState({
      explainResponse: currentResponse,
      fromHistory,
      extractionResult,
      templateId,
      historyId,
      historyLiked: isLiked,
      clinicalContext,
    });
  }, [currentResponse, fromHistory, extractionResult, templateId, historyId, isLiked, clinicalContext]);

  const canRefine = !fromHistory && extractionResult != null;

  const handleRegenerate = useCallback(async () => {
    if (!extractionResult) return;
    setIsRegenerating(true);
    const isShort = commentMode === "short";
    const isSms = commentMode === "sms";
    try {
      const response = await sidecarApi.explainReport({
        extraction_result: extractionResult,
        test_type: effectiveTestType,
        literacy_level: selectedLiteracy,
        template_id: templateId,
        clinical_context: clinicalContext,
        tone_preference: toneSlider,
        detail_preference: detailSlider,
        next_steps: [...checkedNextSteps].filter(s => s !== "No comment"),
        short_comment: isShort,
        sms_summary: isSms,
        explanation_voice: explanationVoice,
        name_drop: nameDrop,
        physician_name_override: physicianOverride !== null ? (physicianOverride || "") : undefined,
        include_key_findings: (isShort || isSms) ? true : sectionSettings.include_key_findings,
        include_measurements: (isShort || isSms) ? true : sectionSettings.include_measurements,
        refinement_instruction: refinementInstruction.trim() || undefined,
        deep_analysis: deepAnalysis || undefined,
      });
      if (isSms) {
        setSmsText(response.explanation.overall_summary);
      } else if (isShort) {
        setShortCommentText(response.explanation.overall_summary);
      } else {
        setLongExplanationResponse(response);
      }
      setCurrentResponse(response);
      logUsage({
        model_used: response.model_used,
        input_tokens: response.input_tokens,
        output_tokens: response.output_tokens,
        request_type: "explain",
        deep_analysis: deepAnalysis,
      });
      showToast("success", "Explanation regenerated.");
    } catch {
      showToast("error", "Failed to regenerate explanation.");
    } finally {
      setIsRegenerating(false);
    }
  }, [extractionResult, effectiveTestType, selectedLiteracy, templateId, clinicalContext, toneSlider, detailSlider, checkedNextSteps, commentMode, explanationVoice, nameDrop, physicianOverride, sectionSettings, refinementInstruction, deepAnalysis, showToast]);

  const handleTranslateToggle = useCallback(async () => {
    const translatingToSpanish = !isSpanish;

    // Letter mode: translate via generateLetter
    if (letterMode) {
      setIsRefiningLetter(true);
      try {
        const translatePrompt = translatingToSpanish
          ? `${letterPrompt}\n\nTranslate the entire letter into Spanish. Keep all medical values and units in their original form. Use simple, patient-friendly Spanish.`
          : letterPrompt;
        const refined = await sidecarApi.generateLetter({
          prompt: translatePrompt,
          letter_type: "general",
        });
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
      const response = await sidecarApi.explainReport({
        extraction_result: extractionResult,
        test_type: effectiveTestType,
        literacy_level: selectedLiteracy,
        template_id: templateId,
        clinical_context: clinicalContext,
        tone_preference: toneSlider,
        detail_preference: detailSlider,
        next_steps: [...checkedNextSteps].filter(s => s !== "No comment"),
        short_comment: isShort,
        sms_summary: isSms,
        explanation_voice: explanationVoice,
        name_drop: nameDrop,
        physician_name_override: physicianOverride !== null ? (physicianOverride || "") : undefined,
        include_key_findings: (isShort || isSms) ? true : sectionSettings.include_key_findings,
        include_measurements: (isShort || isSms) ? true : sectionSettings.include_measurements,
        refinement_instruction: translatingToSpanish
          ? "Translate the entire explanation into Spanish. Keep all medical values and units in their original form. Use simple, patient-friendly Spanish."
          : undefined,
        deep_analysis: deepAnalysis || undefined,
      });
      if (isSms) {
        setSmsText(response.explanation.overall_summary);
      } else if (isShort) {
        setShortCommentText(response.explanation.overall_summary);
      } else {
        setLongExplanationResponse(response);
      }
      setCurrentResponse(response);
      logUsage({
        model_used: response.model_used,
        input_tokens: response.input_tokens,
        output_tokens: response.output_tokens,
        request_type: "explain",
        deep_analysis: deepAnalysis,
      });
      setIsSpanish(translatingToSpanish);
      showToast("success", translatingToSpanish ? "Translated to Spanish." : "Translated to English.");
    } catch {
      showToast("error", "Failed to translate explanation.");
    } finally {
      setIsRegenerating(false);
    }
  }, [extractionResult, effectiveTestType, selectedLiteracy, templateId, clinicalContext, toneSlider, detailSlider, checkedNextSteps, commentMode, isSpanish, explanationVoice, nameDrop, physicianOverride, sectionSettings, deepAnalysis, showToast, letterMode, letterPrompt]);

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
        // Auto-save to history first
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
      showToast(
        "success",
        newLiked
          ? "Will process more like this in the future."
          : "Like removed.",
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      showToast("error", `Failed to update like status: ${msg}`);
    }
  }, [currentResponse, historyId, isLiked, toneSlider, detailSlider, showToast]);

  const markDirty = () => {
    if (!isDirty) setIsDirty(true);
  };

  // Generate short comment on demand
  const generateShortComment = useCallback(async () => {
    if (!extractionResult || !currentResponse) return;
    setIsGeneratingComment(true);
    try {
      const response = await sidecarApi.explainReport({
        extraction_result: extractionResult,
        test_type: effectiveTestType,
        literacy_level: selectedLiteracy,
        template_id: templateId,
        clinical_context: clinicalContext,
        tone_preference: toneSlider,
        detail_preference: detailSlider,
        next_steps: [...checkedNextSteps].filter(s => s !== "No comment"),
        short_comment: true,
        explanation_voice: explanationVoice,
        name_drop: nameDrop,
        physician_name_override: physicianOverride !== null ? (physicianOverride || "") : undefined,
        include_key_findings: true,
        include_measurements: true,
        deep_analysis: deepAnalysis || undefined,
      });
      setShortCommentText(response.explanation.overall_summary);
      logUsage({
        model_used: response.model_used,
        input_tokens: response.input_tokens,
        output_tokens: response.output_tokens,
        request_type: "explain",
        deep_analysis: deepAnalysis,
      });
    } catch {
      showToast("error", "Failed to generate short comment.");
    } finally {
      setIsGeneratingComment(false);
    }
  }, [extractionResult, currentResponse, selectedLiteracy, templateId, toneSlider, detailSlider, checkedNextSteps, explanationVoice, nameDrop, physicianOverride, sectionSettings, showToast]);

  // Generate long explanation on demand when user switches to "long" tab
  const generateLongExplanation = useCallback(async () => {
    if (!extractionResult || !currentResponse) return;
    setIsGeneratingLong(true);
    try {
      const response = await sidecarApi.explainReport({
        extraction_result: extractionResult,
        test_type: effectiveTestType,
        literacy_level: selectedLiteracy,
        template_id: templateId,
        clinical_context: clinicalContext,
        tone_preference: toneSlider,
        detail_preference: detailSlider,
        next_steps: [...checkedNextSteps].filter(s => s !== "No comment"),
        short_comment: false,
        explanation_voice: explanationVoice,
        name_drop: nameDrop,
        physician_name_override: physicianOverride !== null ? (physicianOverride || "") : undefined,
        include_key_findings: sectionSettings.include_key_findings,
        include_measurements: sectionSettings.include_measurements,
        refinement_instruction: refinementInstruction.trim() || undefined,
        deep_analysis: deepAnalysis || undefined,
      });
      setLongExplanationResponse(response);
      logUsage({
        model_used: response.model_used,
        input_tokens: response.input_tokens,
        output_tokens: response.output_tokens,
        request_type: "explain",
        deep_analysis: deepAnalysis,
      });
    } catch {
      showToast("error", "Failed to generate detailed explanation.");
    } finally {
      setIsGeneratingLong(false);
    }
  }, [extractionResult, currentResponse, selectedLiteracy, templateId, clinicalContext, toneSlider, detailSlider, checkedNextSteps, explanationVoice, nameDrop, physicianOverride, sectionSettings, refinementInstruction, showToast]);

  // Generate SMS summary on demand
  const generateSmsText = useCallback(async () => {
    if (!extractionResult || !currentResponse) return;
    setIsGeneratingSms(true);
    try {
      const response = await sidecarApi.explainReport({
        extraction_result: extractionResult,
        test_type: effectiveTestType,
        literacy_level: selectedLiteracy,
        template_id: templateId,
        clinical_context: clinicalContext,
        tone_preference: toneSlider,
        detail_preference: detailSlider,
        next_steps: [...checkedNextSteps].filter(s => s !== "No comment"),
        sms_summary: true,
        explanation_voice: explanationVoice,
        name_drop: nameDrop,
        physician_name_override: physicianOverride !== null ? (physicianOverride || "") : undefined,
        include_key_findings: true,
        include_measurements: true,
        deep_analysis: deepAnalysis || undefined,
      });
      setSmsText(response.explanation.overall_summary);
      logUsage({
        model_used: response.model_used,
        input_tokens: response.input_tokens,
        output_tokens: response.output_tokens,
        request_type: "explain",
        deep_analysis: deepAnalysis,
      });
    } catch {
      setSmsText("");
      showToast("error", "Failed to generate SMS summary.");
    } finally {
      setIsGeneratingSms(false);
    }
  }, [extractionResult, currentResponse, selectedLiteracy, templateId, clinicalContext, toneSlider, detailSlider, checkedNextSteps, explanationVoice, nameDrop, physicianOverride, showToast]);

  // Generate on-demand when user switches tabs and content isn't cached
  useEffect(() => {
    if (commentMode === "short" && shortCommentText === null && extractionResult && currentResponse && !isGeneratingComment) {
      generateShortComment();
    }
  }, [commentMode, shortCommentText, extractionResult, currentResponse, isGeneratingComment, generateShortComment]);

  useEffect(() => {
    if (commentMode === "long" && longExplanationResponse === null && extractionResult && currentResponse && !isGeneratingLong) {
      generateLongExplanation();
    }
  }, [commentMode, longExplanationResponse, extractionResult, currentResponse, isGeneratingLong, generateLongExplanation]);

  useEffect(() => {
    if (commentMode === "sms" && smsText === null && extractionResult && currentResponse && !isGeneratingSms) {
      generateSmsText();
    }
  }, [commentMode, smsText, extractionResult, currentResponse, isGeneratingSms, generateSmsText]);

  // Compute preview text for comment panel
  const commentPreviewText = (() => {
    const physician = physicianOverride ?? currentResponse?.physician_name;
    if (commentMode === "sms") {
      return replacePhysician(smsText ?? "", physician);
    }
    if (commentMode === "short") {
      const base = replacePhysician(shortCommentText ?? "", physician);
      if (computedFooter) {
        return base + "\n\n" + computedFooter;
      }
      return base;
    }
    // Long mode: use edited text if dirty, otherwise use the dedicated long explanation
    const longSource = longExplanationResponse ?? currentResponse;
    if (!longSource) return "";
    const expl = longSource.explanation;
    // Use editedSummary if the user has made edits
    const summary = replacePhysician(
      isDirty ? editedSummary : expl.overall_summary,
      physician,
    );
    // Use editedFindings if the user has made edits
    const findings = (isDirty ? editedFindings : expl.key_findings).map((f) => ({
      finding: f.finding,
      explanation: replacePhysician(f.explanation, physician),
    }));
    return buildCopyText(
      summary,
      findings,
      expl.measurements,
      computedFooter,
      sectionSettings.include_key_findings,
      sectionSettings.include_measurements,
      [...checkedNextSteps],
    );
  })();

  const handleCopyComment = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(commentPreviewText);
      showToast("success", "Copied to clipboard.");

      // Track that this explanation was copied
      if (historyId) {
        // Fire-and-forget: mark as copied
        sidecarApi.markHistoryCopied(historyId).catch(() => {
          // Silently ignore errors
        });

        // If the user edited the text, save their edited version
        if (isDirty && commentMode === "long") {
          sidecarApi.saveEditedText(historyId, editedSummary).catch(() => {
            // Silently ignore errors
          });
        }
      }
    } catch {
      showToast("error", "Failed to copy to clipboard.");
    }
  }, [commentPreviewText, showToast, historyId, isDirty, commentMode, editedSummary]);

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
      if (refinementInstruction.trim()) {
        parts.push(`\n\nRefinement: ${refinementInstruction.trim()}`);
      }
      if (letterRefineText.trim()) {
        parts.push(`\n\nAdditional refinement: ${letterRefineText.trim()}`);
      }
      const refined = await sidecarApi.generateLetter({
        prompt: parts.join(""),
        letter_type: "general",
      });
      setLetterContent(refined.content);
      setLetterRefineText("");
      showToast("success", "Letter refined.");
    } catch {
      showToast("error", "Failed to refine letter.");
    } finally {
      setIsRefiningLetter(false);
    }
  }, [letterPrompt, letterRefineText, refinementInstruction, showToast]);

  if (letterMode) {
    return (
      <div className="results-screen">
        <div className="results-main-panel">
          <header className="results-header">
            <h2 className="results-title">Generated Letter</h2>
          </header>

          {/* Letter Comment Panel */}
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

          {/* Teaching Points */}
          <details className="teaching-points-panel teaching-points-collapsible">
            <summary className="teaching-points-header">
              <h3>Teaching Points</h3>
              {(teachingPoints.length + sharedTeachingPoints.length) > 0 && (
                <span className="teaching-points-count">{teachingPoints.length + sharedTeachingPoints.length}</span>
              )}
            </summary>
            <div className="teaching-points-body">
              <p className="teaching-points-desc">
                Add personalized instructions that customize how AI generates letters.
                These points can be stylistic or clinical. Explify will remember and apply these to all future outputs.
              </p>
              <div className="teaching-point-input-row">
                <textarea
                  className="teaching-point-input"
                  placeholder="e.g. Always use a warm, conversational tone"
                  value={newTeachingPoint}
                  onChange={(e) => setNewTeachingPoint(e.target.value)}
                  rows={3}
                />
                <div className="teaching-point-save-row">
                  <button
                    className="teaching-point-save-btn"
                    disabled={!newTeachingPoint.trim()}
                    onClick={async () => {
                      if (!newTeachingPoint.trim()) return;
                      try {
                        const tp = await sidecarApi.createTeachingPoint({
                          text: newTeachingPoint.trim(),
                        });
                        setTeachingPoints((prev) => [tp, ...prev]);
                        setNewTeachingPoint("");
                        queueUpsertAfterMutation("teaching_points", tp.id).catch(() => {});
                      } catch {
                        showToast("error", "Failed to save teaching point.");
                      }
                    }}
                  >
                    Save for all types
                  </button>
                </div>
              </div>
              {sharedTeachingPoints.length > 0 && (
                <div className="shared-teaching-points">
                  <span className="shared-teaching-points-label">Shared with you</span>
                  {sharedTeachingPoints.map((sp) => (
                    <div key={sp.sync_id} className="shared-teaching-point-card">
                      <p className="shared-teaching-point-text">{sp.text}</p>
                      <div className="shared-teaching-point-meta">
                        <span className="shared-teaching-point-sharer">
                          Shared by {sp.sharer_email}
                        </span>
                        {sp.test_type ? (
                          <span className="shared-teaching-point-type">{sp.test_type}</span>
                        ) : (
                          <span className="shared-teaching-point-type shared-teaching-point-type--global">All types</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </details>

          <button
            className="results-back-btn"
            onClick={() => navigate("/")}
          >
            Analyze Another Report
          </button>
        </div>

        {/* Right Column — Refine + Settings */}
        <div className="results-right-column">
          {/* Refine Panel */}
          <div className="results-refine-panel">
            <h3>Refine Context</h3>
            <textarea
              className="refine-textarea"
              placeholder="e.g., Make it shorter, add more detail, emphasize dietary changes..."
              value={refinementInstruction}
              onChange={(e) => setRefinementInstruction(e.target.value)}
              rows={3}
            />
          </div>

          {/* Result Settings Panel */}
          <div className="results-settings-panel">
            <h3>Result Settings</h3>

            <div className="settings-panel-label">
              <span>Literacy</span>
              <div className="literacy-tabs">
                {LITERACY_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    className={`literacy-tab-btn ${selectedLiteracy === opt.value ? "literacy-tab-btn--active" : ""}`}
                    onClick={() => setSelectedLiteracy(opt.value)}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="quick-sliders">
              <div className="quick-slider-group">
                <label className="quick-slider-label">
                  Tone
                  <span className="quick-slider-value">{TONE_LABELS[toneSlider]}</span>
                </label>
                <div className="quick-slider-row">
                  <span className="quick-slider-end">Concerning</span>
                  <input
                    type="range"
                    className="preference-slider"
                    min={1}
                    max={5}
                    step={1}
                    value={toneSlider}
                    onChange={(e) => setToneSlider(Number(e.target.value))}
                  />
                  <span className="quick-slider-end">Very Reassuring</span>
                </div>
              </div>
              <div className="quick-slider-group">
                <label className="quick-slider-label">
                  Detail
                  <span className="quick-slider-value">{DETAIL_LABELS[detailSlider]}</span>
                </label>
                <div className="quick-slider-row">
                  <span className="quick-slider-end">Minimal</span>
                  <input
                    type="range"
                    className="preference-slider"
                    min={1}
                    max={5}
                    step={1}
                    value={detailSlider}
                    onChange={(e) => setDetailSlider(Number(e.target.value))}
                  />
                  <span className="quick-slider-end">Very Detailed</span>
                </div>
              </div>
            </div>

            {/* Voice */}
            <div className="quick-voice-section">
              <span className="quick-actions-label">Voice:</span>
              <div className="quick-voice-toggle">
                <button
                  className={`physician-picker-btn ${explanationVoice === "first_person" ? "physician-picker-btn--active" : ""}`}
                  onClick={() => setExplanationVoice("first_person")}
                >
                  1st Person
                </button>
                <button
                  className={`physician-picker-btn ${explanationVoice === "third_person" ? "physician-picker-btn--active" : ""}`}
                  onClick={() => setExplanationVoice("third_person")}
                >
                  3rd Person
                </button>
              </div>
            </div>

            {/* Physician */}
            {explanationVoice === "third_person" && (
              <div className="quick-voice-section">
                <span className="quick-actions-label">Physician:</span>
                <div className="quick-voice-toggle">
                  {practiceProviders.map((name) => (
                    <button
                      key={name}
                      className={`physician-picker-btn ${physicianOverride === name ? "physician-picker-btn--active" : ""}`}
                      onClick={() => setPhysicianOverride(name)}
                    >
                      {name}
                    </button>
                  ))}
                  <button
                    className={`physician-picker-btn ${physicianOverride === "" || physicianOverride === null ? "physician-picker-btn--active" : ""}`}
                    onClick={() => setPhysicianOverride("")}
                  >
                    Generic
                  </button>
                </div>
                <label className="quick-toggle" style={{ marginTop: "var(--space-xs)" }}>
                  <input
                    type="checkbox"
                    checked={nameDrop}
                    onChange={(e) => setNameDrop(e.target.checked)}
                  />
                  <span>Name drop</span>
                </label>
              </div>
            )}

            {/* Next Steps */}
            <div className="settings-panel-next-steps">
              <span className="quick-actions-label">Next Steps:</span>
              <div className="next-steps-checks">
                <label className="next-step-check">
                  <input
                    type="checkbox"
                    checked={checkedNextSteps.has("No comment")}
                    onChange={() => {
                      setCheckedNextSteps(new Set(["No comment"]));
                    }}
                  />
                  <span>No comment</span>
                </label>
                {nextStepsOptions.map((option) => (
                  <label key={option} className="next-step-check">
                    <input
                      type="checkbox"
                      checked={checkedNextSteps.has(option)}
                      onChange={() => {
                        setCheckedNextSteps((prev) => {
                          const next = new Set(prev);
                          if (next.has(option)) {
                            next.delete(option);
                            if (next.size === 0) next.add("No comment");
                          } else {
                            next.add(option);
                            next.delete("No comment");
                          }
                          return next;
                        });
                      }}
                    />
                    <span>{option}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="quick-actions-buttons">
              <button
                className="quick-action-btn"
                onClick={handleRefineLetter}
                disabled={isRefiningLetter}
              >
                {isRefiningLetter ? "Regenerating\u2026" : "Apply"}
              </button>
              <button
                className="quick-action-btn"
                onClick={handleTranslateToggle}
                disabled={isRefiningLetter}
              >
                {isSpanish ? "Translate to English" : "Translate to Spanish"}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!currentResponse) {
    return (
      <div className="results-main-panel">
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
        {fromHistory && (
          <span className="results-from-history">Viewed from history</span>
        )}
      </header>

      {/* Refine Toolbar */}
      {canRefine && (
        <div className="refine-toolbar">
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

      {/* Comment Panel */}
      <div className="results-comment-panel">
        <div className="comment-panel-header">
          <h3>Result Comment</h3>
          <button
            className={`like-btn${isLiked ? " like-btn--active" : ""}`}
            onClick={handleToggleLike}
          >
            {isLiked ? "\u2665 Liked" : "\u2661 Like"}
          </button>
        </div>
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
            value={editedSummary}
            onChange={(e) => {
              setEditedSummary(e.target.value);
              markDirty();
            }}
            rows={6}
          />
        )}
        {(isGeneratingComment && commentMode === "short") || (isGeneratingLong && commentMode === "long") || (isGeneratingSms && commentMode === "sms") ? (
          <div className="comment-generating">
            {commentMode === "sms" ? "Generating SMS summary..." : commentMode === "short" ? "Generating short comment..." : "Generating detailed explanation..."}
          </div>
        ) : (
          <div className="comment-preview">{commentPreviewText}</div>
        )}
        <span className="comment-char-count">{commentPreviewText.length} chars</span>
        <button className="comment-copy-btn" onClick={handleCopyComment}>
          Copy to Clipboard
        </button>
        <div className="comment-export-row">
          <button
            className="comment-export-btn"
            onClick={handleExportPdf}
            disabled={isExporting}
          >
            {isExporting ? "Exporting\u2026" : "Export PDF"}
          </button>
          <button className="comment-export-btn" onClick={() => window.print()}>
            Print
          </button>
        </div>
      </div>

      {/* Key Findings */}
      {sectionSettings.include_key_findings && displayFindings.length > 0 && (
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
      {sectionSettings.include_measurements && explanation.measurements.length > 0 && (
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

      {/* Teaching Points */}
      <details className="teaching-points-panel teaching-points-collapsible">
        <summary className="teaching-points-header">
          <h3>Teaching Points</h3>
          {(teachingPoints.length + sharedTeachingPoints.length) > 0 && (
            <span className="teaching-points-count">{teachingPoints.length + sharedTeachingPoints.length}</span>
          )}
        </summary>
        <div className="teaching-points-body">
          <div className="teaching-points-type-row">
            <label className="teaching-points-type-label">Report type:</label>
            <input
              type="text"
              className="teaching-points-type-input"
              value={testTypeOverride ?? currentResponse?.parsed_report.test_type_display ?? ""}
              onChange={(e) => setTestTypeOverride(e.target.value)}
              placeholder="e.g. Calcium Score CT"
            />
          </div>
          <p className="teaching-points-desc">
            Add personalized instructions that customize how AI interprets and explains results.
            These points can be stylistic or clinical. Explify will remember and apply these to all future explanations.
          </p>
          <div className="teaching-point-input-row">
            <textarea
              className="teaching-point-input"
              placeholder="e.g. Always mention diastolic dysfunction grading"
              value={newTeachingPoint}
              onChange={(e) => setNewTeachingPoint(e.target.value)}
              rows={3}
            />
            <div className="teaching-point-save-row">
              <button
                className="teaching-point-save-btn"
                disabled={!newTeachingPoint.trim()}
                onClick={async () => {
                  if (!newTeachingPoint.trim()) return;
                  try {
                    const tp = await sidecarApi.createTeachingPoint({
                      text: newTeachingPoint.trim(),
                      test_type: effectiveTestType,
                    });
                    setTeachingPoints((prev) => [tp, ...prev]);
                    setNewTeachingPoint("");
                    queueUpsertAfterMutation("teaching_points", tp.id).catch(() => {});
                  } catch {
                    showToast("error", "Failed to save teaching point.");
                  }
                }}
              >
                Save for {effectiveTestTypeDisplay}
              </button>
              <button
                className="teaching-point-save-btn teaching-point-save-btn--all"
                disabled={!newTeachingPoint.trim()}
                onClick={async () => {
                  if (!newTeachingPoint.trim()) return;
                  try {
                    const tp = await sidecarApi.createTeachingPoint({
                      text: newTeachingPoint.trim(),
                    });
                    setTeachingPoints((prev) => [tp, ...prev]);
                    setNewTeachingPoint("");
                    queueUpsertAfterMutation("teaching_points", tp.id).catch(() => {});
                  } catch {
                    showToast("error", "Failed to save teaching point.");
                  }
                }}
              >
                Save for all types
              </button>
            </div>
          </div>
          {sharedTeachingPoints.length > 0 && (
            <div className="shared-teaching-points">
              <span className="shared-teaching-points-label">Shared with you</span>
              {sharedTeachingPoints.map((sp) => (
                <div key={sp.sync_id} className="shared-teaching-point-card">
                  <p className="shared-teaching-point-text">{sp.text}</p>
                  <div className="shared-teaching-point-meta">
                    <span className="shared-teaching-point-sharer">
                      Shared by {sp.sharer_email}
                    </span>
                    {sp.test_type ? (
                      <span className="shared-teaching-point-type">{sp.test_type}</span>
                    ) : (
                      <span className="shared-teaching-point-type shared-teaching-point-type--global">All types</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </details>

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

      {canRefine && (
      <div className="results-right-column">
      {/* Refine Panel */}
        <div className="results-refine-panel">
          <h3>Refine Context</h3>
          <textarea
            className="refine-textarea"
            placeholder="e.g., Emphasize the elevated LDL given patient's cardiac history"
            value={refinementInstruction}
            onChange={(e) => setRefinementInstruction(e.target.value)}
            rows={3}
          />
        </div>

      {/* Result Settings Panel */}
        <div className="results-settings-panel">
          <h3>Result Settings</h3>

          <div className="settings-panel-label">
            <span>Literacy</span>
            <div className="literacy-tabs">
              {LITERACY_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  className={`literacy-tab-btn ${selectedLiteracy === opt.value ? "literacy-tab-btn--active" : ""}`}
                  onClick={() => setSelectedLiteracy(opt.value)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <div className="quick-sliders">
            <div className="quick-slider-group">
              <label className="quick-slider-label">
                Tone
                <span className="quick-slider-value">{TONE_LABELS[toneSlider]}</span>
              </label>
              <div className="quick-slider-row">
                <span className="quick-slider-end">Concerning</span>
                <input
                  type="range"
                  className="preference-slider"
                  min={1}
                  max={5}
                  step={1}
                  value={toneSlider}
                  onChange={(e) => setToneSlider(Number(e.target.value))}
                />
                <span className="quick-slider-end">Very Reassuring</span>
              </div>
            </div>
            <div className="quick-slider-group">
              <label className="quick-slider-label">
                Detail
                <span className="quick-slider-value">{DETAIL_LABELS[detailSlider]}</span>
              </label>
              <div className="quick-slider-row">
                <span className="quick-slider-end">Minimal</span>
                <input
                  type="range"
                  className="preference-slider"
                  min={1}
                  max={5}
                  step={1}
                  value={detailSlider}
                  onChange={(e) => setDetailSlider(Number(e.target.value))}
                />
                <span className="quick-slider-end">Very Detailed</span>
              </div>
            </div>
          </div>

          <div className="deep-analysis-setting">
            <label className="quick-toggle">
              <input
                type="checkbox"
                checked={deepAnalysis}
                onChange={(e) => setDeepAnalysis(e.target.checked)}
              />
              <span>Deep Analysis</span>
            </label>
            <span className="deep-analysis-subtext">For complex cases only</span>
          </div>

          <div className="quick-toggles">
            <span className="quick-actions-label">Long comment settings:</span>
            <div className="quick-toggles-row">
              <label className="quick-toggle">
                <input
                  type="checkbox"
                  checked={sectionSettings.include_key_findings}
                  onChange={(e) =>
                    setSectionSettings((prev) => ({
                      ...prev,
                      include_key_findings: e.target.checked,
                    }))
                  }
                />
                <span>Include Key Findings</span>
              </label>
              <label className="quick-toggle">
                <input
                  type="checkbox"
                  checked={sectionSettings.include_measurements}
                  onChange={(e) =>
                    setSectionSettings((prev) => ({
                      ...prev,
                      include_measurements: e.target.checked,
                    }))
                  }
                />
                <span>Include Measurements</span>
              </label>
            </div>
          </div>

          {/* Voice */}
          <div className="quick-voice-section">
            <span className="quick-actions-label">Voice:</span>
            <div className="quick-voice-toggle">
              <button
                className={`physician-picker-btn ${explanationVoice === "first_person" ? "physician-picker-btn--active" : ""}`}
                onClick={() => setExplanationVoice("first_person")}
              >
                1st Person
              </button>
              <button
                className={`physician-picker-btn ${explanationVoice === "third_person" ? "physician-picker-btn--active" : ""}`}
                onClick={() => setExplanationVoice("third_person")}
              >
                3rd Person
              </button>
            </div>
          </div>

          {/* Physician */}
          {explanationVoice === "third_person" && (
            <div className="quick-voice-section">
              <span className="quick-actions-label">Physician:</span>
              <div className="quick-voice-toggle">
                {currentResponse?.physician_name && (
                  <button
                    className={`physician-picker-btn ${physicianOverride === null ? "physician-picker-btn--active" : ""}`}
                    onClick={() => setPhysicianOverride(null)}
                  >
                    {currentResponse.physician_name} (Extracted)
                  </button>
                )}
                {practiceProviders.map((name) => (
                  <button
                    key={name}
                    className={`physician-picker-btn ${physicianOverride === name ? "physician-picker-btn--active" : ""}`}
                    onClick={() => setPhysicianOverride(name)}
                  >
                    {name}
                  </button>
                ))}
                <button
                  className={`physician-picker-btn ${physicianOverride === "" || (!currentResponse?.physician_name && physicianOverride === null) ? "physician-picker-btn--active" : ""}`}
                  onClick={() => setPhysicianOverride("")}
                >
                  Generic
                </button>
              </div>
              <label className="quick-toggle" style={{ marginTop: "var(--space-xs)" }}>
                <input
                  type="checkbox"
                  checked={nameDrop}
                  onChange={(e) => setNameDrop(e.target.checked)}
                />
                <span>Name drop</span>
              </label>
            </div>
          )}

          {/* Next Steps */}
          <div className="settings-panel-next-steps">
            <span className="quick-actions-label">Next Steps:</span>
            <div className="next-steps-checks">
              <label className="next-step-check">
                <input
                  type="checkbox"
                  checked={checkedNextSteps.has("No comment")}
                  onChange={() => {
                    setCheckedNextSteps(new Set(["No comment"]));
                  }}
                />
                <span>No comment</span>
              </label>
              {nextStepsOptions.map((option) => (
                <label key={option} className="next-step-check">
                  <input
                    type="checkbox"
                    checked={checkedNextSteps.has(option)}
                    onChange={() => {
                      setCheckedNextSteps((prev) => {
                        const next = new Set(prev);
                        if (next.has(option)) {
                          next.delete(option);
                          if (next.size === 0) next.add("No comment");
                        } else {
                          next.add(option);
                          next.delete("No comment");
                        }
                        return next;
                      });
                    }}
                  />
                  <span>{option}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="quick-actions-buttons">
            <button
              className="quick-action-btn"
              onClick={handleRegenerate}
              disabled={isRegenerating}
            >
              {isRegenerating ? "Regenerating\u2026" : "Apply"}
            </button>
            <button
              className="quick-action-btn"
              onClick={handleTranslateToggle}
              disabled={isRegenerating}
            >
              {isSpanish ? "Translate to English" : "Translate to Spanish"}
            </button>
          </div>

          <div className="extracted-text-section">
            <div className="extracted-text-buttons">
              {extractionResult?.full_text && (
                <button
                  className="extracted-text-toggle"
                  onClick={async () => {
                    const willShow = !showExtractedText;
                    setShowExtractedText(willShow);
                    if (willShow && scrubbedText === null && !isScrubbing) {
                      setIsScrubbing(true);
                      try {
                        const res = await sidecarApi.scrubPreview(extractionResult.full_text);
                        setScrubbedText(res.scrubbed_text);
                      } catch {
                        setScrubbedText(extractionResult.full_text);
                      } finally {
                        setIsScrubbing(false);
                      }
                    }
                  }}
                >
                  {showExtractedText ? "Hide Extracted Text" : "View Extracted Text"}
                </button>
              )}
              <button
                className="extracted-text-toggle"
                onClick={() => setShowReportType((prev) => !prev)}
              >
                {showReportType ? "Hide Report Type" : "View Report Type"}
              </button>
            </div>
            {showReportType && (
              <div className="report-type-reveal">
                {currentResponse.parsed_report.test_type_display}
              </div>
            )}
            {showExtractedText && extractionResult?.full_text && (
              <div className="extracted-text-container">
                {isScrubbing ? (
                  <pre className="extracted-text">Redacting PHI...</pre>
                ) : (
                  <pre className="extracted-text">{scrubbedText ?? extractionResult.full_text}</pre>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
      )}
    </div>
  );
}
