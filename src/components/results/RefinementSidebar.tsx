import type {
  ExplainResponse,
  ExtractionResult,
  LiteracyLevel,
  ExplanationVoice,
  FooterType,
  Template,
  SharedTemplate,
} from "../../types/sidecar";
import { sidecarApi } from "../../services/sidecarApi";

const TONE_LABELS = ["", "Concerning", "Straightforward", "Neutral", "Reassuring", "Very Reassuring"];
const DETAIL_LABELS = ["", "Minimal", "Concise", "Moderate", "Detailed", "Very Detailed"];
const ANXIETY_OPTIONS: { value: number; label: string; hint: string }[] = [
  { value: 0, label: "None", hint: "Standard tone" },
  { value: 1, label: "Mild", hint: "Softer language" },
  { value: 2, label: "Moderate", hint: "Lead with positives" },
  { value: 3, label: "Severe", hint: "Maximum reassurance" },
];

const LITERACY_OPTIONS: { value: LiteracyLevel; label: string }[] = [
  { value: "grade_4", label: "Grade 4" },
  { value: "grade_6", label: "Grade 6" },
  { value: "grade_8", label: "Grade 8" },
  { value: "grade_12", label: "Grade 12" },
  { value: "clinical", label: "Clinical" },
];

interface SectionSettings {
  include_key_findings: boolean;
  include_measurements: boolean;
  practice_name: string | null;
  footer_type: FooterType;
  custom_footer_text: string | null;
}

interface RefinementSidebarProps {
  refinementInstruction: string;
  setRefinementInstruction: (value: string) => void;
  selectedTemplateId: number | undefined;
  setSelectedTemplateId: (value: number | undefined) => void;
  templates: Template[];
  sharedTemplates: SharedTemplate[];
  selectedLiteracy: LiteracyLevel;
  setSelectedLiteracy: (value: LiteracyLevel) => void;
  toneSlider: number;
  setToneSlider: (value: number) => void;
  detailSlider: number;
  setDetailSlider: (value: number) => void;
  highAnxietyMode: boolean;
  setHighAnxietyMode: (value: boolean) => void;
  anxietyLevel: number;
  setAnxietyLevel: (value: number) => void;
  useAnalogies: boolean;
  setUseAnalogies: (value: boolean) => void;
  deepAnalysis: boolean;
  setDeepAnalysis: (value: boolean) => void;
  sectionSettings: SectionSettings;
  setSectionSettings: React.Dispatch<React.SetStateAction<SectionSettings>>;
  explanationVoice: ExplanationVoice;
  setExplanationVoice: (value: ExplanationVoice) => void;
  nameDrop: boolean;
  setNameDrop: (value: boolean) => void;
  practiceProviders: string[];
  physicianOverride: string | null;
  setPhysicianOverride: (value: string | null) => void;
  currentResponse: ExplainResponse | null;
  nextStepsOptions: string[];
  checkedNextSteps: Set<string>;
  setCheckedNextSteps: React.Dispatch<React.SetStateAction<Set<string>>>;
  isRegenerating: boolean;
  isSpanish: boolean;
  onRegenerate: () => void;
  onTranslateToggle: () => void;
  extractionResult: ExtractionResult | null;
  showExtractedText: boolean;
  setShowExtractedText: (value: boolean) => void;
  showReportType: boolean;
  setShowReportType: (value: boolean) => void;
  scrubbedText: string | null;
  setScrubbedText: (value: string | null) => void;
  isScrubbing: boolean;
  setIsScrubbing: (value: boolean) => void;
  /** When true, renders the simplified letter-mode sidebar */
  letterMode?: boolean;
  isRefiningLetter?: boolean;
  onRefineLetter?: () => void;
}

export function RefinementSidebar({
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
  highAnxietyMode: _highAnxietyMode,
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
  onRegenerate,
  onTranslateToggle,
  extractionResult,
  showExtractedText,
  setShowExtractedText,
  showReportType,
  setShowReportType,
  scrubbedText,
  setScrubbedText,
  isScrubbing,
  setIsScrubbing,
  letterMode,
  isRefiningLetter,
  onRefineLetter,
}: RefinementSidebarProps) {
  const handleApply = letterMode ? onRefineLetter : onRegenerate;
  const isApplying = letterMode ? isRefiningLetter : isRegenerating;

  return (
    <div className="results-right-column">
      {/* Refine Panel */}
      <div className="results-refine-panel">
        <h3>Refine Context</h3>
        <textarea
          className="refine-textarea"
          placeholder={letterMode
            ? "e.g., Make it shorter, add more detail, emphasize dietary changes..."
            : "e.g., Emphasize the elevated LDL given patient's cardiac history"}
          value={refinementInstruction}
          onChange={(e) => setRefinementInstruction(e.target.value)}
          rows={3}
        />
      </div>

      {/* Result Settings Panel */}
      <div className="results-settings-panel">
        <h3>Result Settings</h3>

        {/* Template Selector */}
        <div className="settings-panel-label">
          <span>Template</span>
          <select
            className="template-select"
            value={selectedTemplateId ?? ""}
            onChange={(e) => {
              const val = e.target.value;
              setSelectedTemplateId(val ? Number(val) : undefined);
            }}
          >
            <option value="">No template</option>
            {templates.length > 0 && (
              <optgroup label="Your Templates">
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </optgroup>
            )}
            {sharedTemplates.length > 0 && (
              <optgroup label="Shared Templates">
                {sharedTemplates.map((t) => (
                  <option key={`shared-${t.id}`} value={t.id}>{t.name}</option>
                ))}
              </optgroup>
            )}
          </select>
        </div>

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
              <span className="quick-slider-value">
                {anxietyLevel >= 3 ? "High Anxiety Mode" : TONE_LABELS[toneSlider]}
              </span>
            </label>
            <div className="quick-slider-row">
              <span className="quick-slider-end">Concerning</span>
              <input
                type="range"
                className="preference-slider"
                min={1}
                max={5}
                step={1}
                value={anxietyLevel >= 3 ? 5 : anxietyLevel === 2 ? Math.max(toneSlider, 4) : toneSlider}
                onChange={(e) => setToneSlider(Number(e.target.value))}
                disabled={anxietyLevel >= 3}
              />
              <span className="quick-slider-end">Very Reassuring</span>
            </div>
            <div className="anxiety-level-section">
              <span className="high-anxiety-label">Patient Anxiety</span>
              <div className="anxiety-level-tabs">
                {ANXIETY_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    className={`anxiety-level-btn ${anxietyLevel === opt.value ? "anxiety-level-btn--active" : ""}`}
                    onClick={() => {
                      setAnxietyLevel(opt.value);
                      setHighAnxietyMode(opt.value >= 3);
                      if (opt.value >= 3) setToneSlider(5);
                    }}
                    title={opt.hint}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
              <span className="high-anxiety-hint">
                {ANXIETY_OPTIONS.find((o) => o.value === anxietyLevel)?.hint}
              </span>
            </div>
            <label className="high-anxiety-toggle">
              <input
                type="checkbox"
                checked={useAnalogies}
                onChange={(e) => setUseAnalogies(e.target.checked)}
              />
              <span className="high-anxiety-label">Use Analogies</span>
              <span className="high-anxiety-hint">
                Size comparisons and everyday examples
              </span>
            </label>
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

        {/* Report-mode only settings */}
        {!letterMode && (
          <>
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
          </>
        )}

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
              {!letterMode && currentResponse?.physician_name && (
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
                className={`physician-picker-btn ${physicianOverride === "" || (!letterMode && !currentResponse?.physician_name && physicianOverride === null) ? "physician-picker-btn--active" : ""}`}
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
            onClick={handleApply}
            disabled={!!isApplying}
          >
            {isApplying ? "Regenerating\u2026" : "Apply"}
          </button>
          <button
            className="quick-action-btn"
            onClick={onTranslateToggle}
            disabled={!!isApplying}
          >
            {isSpanish ? "Translate to English" : "Translate to Spanish"}
          </button>
        </div>

        {/* Extracted text / report type (report mode only) */}
        {!letterMode && (
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
                onClick={() => setShowReportType(!showReportType)}
              >
                {showReportType ? "Hide Report Type" : "View Report Type"}
              </button>
            </div>
            {showReportType && currentResponse && (
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
        )}
      </div>
    </div>
  );
}
