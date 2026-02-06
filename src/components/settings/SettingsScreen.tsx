import { useState, useEffect, useCallback, useRef } from "react";
import { getVersion } from "@tauri-apps/api/app";
import { check, type Update } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";
import { sidecarApi } from "../../services/sidecarApi";
import { queueSettingsUpsert } from "../../services/syncEngine";
import { useToast } from "../shared/Toast";
import { SharingPanel } from "../teaching-points/SharingPanel";
import type { LiteracyLevel, ExplanationVoice, PhysicianNameSource, FooterType } from "../../types/sidecar";
import "./SettingsScreen.css";

const SPECIALTY_OPTIONS = [
  "Cardiology",
  "Pulmonology",
  "Neurology",
  "Gastroenterology",
  "Endocrinology",
  "Nephrology",
  "Hematology",
  "Oncology",
  "Radiology",
  "General/Primary Care",
];

const LITERACY_OPTIONS: {
  value: LiteracyLevel;
  label: string;
  description: string;
}[] = [
  {
    value: "grade_4",
    label: "Grade 4",
    description: "Very simple words, short sentences",
  },
  {
    value: "grade_6",
    label: "Grade 6",
    description: "Simple, clear language",
  },
  {
    value: "grade_8",
    label: "Grade 8",
    description: "Clear with some technical terms",
  },
  {
    value: "grade_12",
    label: "Grade 12",
    description: "Adult language, medical terms in context",
  },
  {
    value: "clinical",
    label: "Clinical",
    description: "Standard medical terminology",
  },
];

export function SettingsScreen() {
  const { showToast } = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const loaded = useRef(false);

  const [literacyLevel, setLiteracyLevel] =
    useState<LiteracyLevel>("grade_12");
  const [specialty, setSpecialty] = useState("");
  const [practiceName, setPracticeName] = useState("");
  const [includeKeyFindings, setIncludeKeyFindings] = useState(true);
  const [includeMeasurements, setIncludeMeasurements] = useState(true);
  const [tonePreference, setTonePreference] = useState(3);
  const [detailPreference, setDetailPreference] = useState(3);
  const [quickReasons, setQuickReasons] = useState<string[]>([]);
  const [newReason, setNewReason] = useState("");
  const [nextStepsOptions, setNextStepsOptions] = useState<string[]>([
    "We will contact you to discuss next steps",
  ]);
  const [newNextStep, setNewNextStep] = useState("");
  const [explanationVoice, setExplanationVoice] = useState<ExplanationVoice>("third_person");
  const [nameDrop, setNameDrop] = useState(true);
  const [physicianNameSource, setPhysicianNameSource] = useState<PhysicianNameSource>("auto_extract");
  const [customPhysicianName, setCustomPhysicianName] = useState("");
  const [practiceProviders, setPracticeProviders] = useState<string[]>([]);
  const [newProvider, setNewProvider] = useState("");
  const [shortCommentCharLimit, setShortCommentCharLimit] = useState<number | null>(1000);
  const [smsEnabled, setSmsEnabled] = useState(false);
  const [smsCharLimit, setSmsCharLimit] = useState(300);
  const [footerType, setFooterType] = useState<FooterType>("explify_branding");
  const [customFooterText, setCustomFooterText] = useState("");

  // About / Update state
  const [appVersion, setAppVersion] = useState("");
  const [updateCheck, setUpdateCheck] = useState<Update | null>(null);
  const [updateStatus, setUpdateStatus] = useState<"idle" | "checking" | "updating" | "up-to-date">("idle");


  useEffect(() => {
    getVersion().then(setAppVersion).catch(() => {});
  }, []);

  useEffect(() => {
    async function loadSettings() {
      try {
        const s = await sidecarApi.getSettings();
        setLiteracyLevel(s.literacy_level);
        setSpecialty(s.specialty ?? "");
        setPracticeName(s.practice_name ?? "");
        setIncludeKeyFindings(s.include_key_findings);
        setIncludeMeasurements(s.include_measurements);
        setTonePreference(s.tone_preference);
        setDetailPreference(s.detail_preference);
        setQuickReasons(s.quick_reasons ?? []);
        setNextStepsOptions(s.next_steps_options ?? [
          "We will contact you to discuss next steps",
        ]);
        setExplanationVoice(s.explanation_voice ?? "third_person");
        setNameDrop(s.name_drop ?? true);
        setPhysicianNameSource(s.physician_name_source ?? "auto_extract");
        setCustomPhysicianName(s.custom_physician_name ?? "");
        setPracticeProviders(s.practice_providers ?? []);
        setShortCommentCharLimit(s.short_comment_char_limit ?? 1000);
        setSmsEnabled(s.sms_summary_enabled ?? false);
        setSmsCharLimit(s.sms_summary_char_limit ?? 300);
        setFooterType(s.footer_type ?? "explify_branding");
        setCustomFooterText(s.custom_footer_text ?? "");
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Failed to load settings";
        setError(msg);
        showToast("error", msg);
      } finally {
        setLoading(false);
        loaded.current = true;
      }
    }
    loadSettings();
  }, [showToast]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setError(null);
    setSuccess(false);

    try {
      const update: Record<string, unknown> = {
        literacy_level: literacyLevel,
        specialty: specialty || null,
        practice_name: practiceName.trim() || null,
        include_key_findings: includeKeyFindings,
        include_measurements: includeMeasurements,
        tone_preference: tonePreference,
        detail_preference: detailPreference,
        quick_reasons: quickReasons,
        next_steps_options: nextStepsOptions,
        explanation_voice: explanationVoice,
        name_drop: nameDrop,
        physician_name_source: physicianNameSource,
        custom_physician_name: customPhysicianName.trim() || null,
        practice_providers: practiceProviders,
        short_comment_char_limit: shortCommentCharLimit,
        sms_summary_enabled: smsEnabled,
        sms_summary_char_limit: smsCharLimit,
        footer_type: footerType,
        custom_footer_text: customFooterText.trim() || null,
      };

      await sidecarApi.updateSettings(update);

      // Queue each setting for cloud sync (API keys are auto-excluded)
      for (const [key, value] of Object.entries(update)) {
        if (value !== undefined) {
          const serialized = typeof value === "string" ? value : JSON.stringify(value);
          queueSettingsUpsert(key, serialized);
        }
      }

      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to save settings";
      setError(msg);
      showToast("error", msg);
    } finally {
      setSaving(false);
    }
  }, [literacyLevel, specialty, practiceName, includeKeyFindings, includeMeasurements, tonePreference, detailPreference, quickReasons, nextStepsOptions, explanationVoice, nameDrop, physicianNameSource, customPhysicianName, practiceProviders, shortCommentCharLimit, smsEnabled, smsCharLimit, footerType, customFooterText, showToast]);

  // Auto-save: debounce 800ms after any setting changes
  const handleSaveRef = useRef(handleSave);
  handleSaveRef.current = handleSave;

  useEffect(() => {
    if (!loaded.current) return;

    const timer = setTimeout(() => {
      handleSaveRef.current();
    }, 800);

    return () => clearTimeout(timer);
  }, [literacyLevel, specialty, practiceName, includeKeyFindings, includeMeasurements, tonePreference, detailPreference, quickReasons, nextStepsOptions, explanationVoice, nameDrop, physicianNameSource, customPhysicianName, practiceProviders, shortCommentCharLimit, smsEnabled, smsCharLimit, footerType, customFooterText]);

  const handleCheckForUpdates = async () => {
    setUpdateStatus("checking");
    setUpdateCheck(null);
    try {
      const update = await check();
      if (update?.available) {
        setUpdateCheck(update);
        setUpdateStatus("idle");
      } else {
        setUpdateStatus("up-to-date");
      }
    } catch {
      setUpdateStatus("idle");
      showToast("error", "Failed to check for updates.");
    }
  };

  const handleApplyUpdate = async () => {
    if (!updateCheck) return;
    setUpdateStatus("updating");
    try {
      if (navigator.userAgent.includes("Windows")) {
        try {
          const { invoke } = await import("@tauri-apps/api/core");
          await invoke("kill_sidecar");
        } catch {
          // Non-fatal: NSIS hook will kill sidecar if needed
        }
      }
      await updateCheck.downloadAndInstall();
      await relaunch();
    } catch {
      setUpdateStatus("idle");
      showToast("error", "Update failed.");
    }
  };

  if (loading) {
    return (
      <div className="settings-screen">
        <p>Loading settings...</p>
      </div>
    );
  }

  return (
    <div className="settings-screen">
      <header className="settings-header">
        <h2 className="settings-title">Settings</h2>
        <p className="settings-description">
          Configure your explanation preferences.
        </p>
      </header>

      {/* Practice Information */}
      <section className="settings-section">
        <h3 className="settings-section-title">Practice Information</h3>
        <div className="form-group">
          <label className="form-label">Specialty</label>
          <select
            className="form-input"
            value={specialty}
            onChange={(e) => setSpecialty(e.target.value)}
          >
            <option value="">Select a specialty...</option>
            {SPECIALTY_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label className="form-label">Practice Name</label>
          <input
            type="text"
            className="form-input"
            placeholder="e.g. Main Street Cardiology"
            value={practiceName}
            onChange={(e) => setPracticeName(e.target.value)}
          />
        </div>

      </section>

      {/* Literacy Level */}
      <section className="settings-section">
        <h3 className="settings-section-title">Explanation Level</h3>
        <div className="literacy-tabs-settings">
          {LITERACY_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              className={`literacy-tab-settings ${literacyLevel === opt.value ? "literacy-tab-settings--active" : ""}`}
              onClick={() => setLiteracyLevel(opt.value)}
            >
              <span className="literacy-tab-label">{opt.label}</span>
              <span className="literacy-tab-desc">{opt.description}</span>
            </button>
          ))}
        </div>
      </section>

      {/* Output Sections */}
      <section className="settings-section">
        <h3 className="settings-section-title">Output Sections</h3>
        <p className="settings-description" style={{ marginBottom: "var(--space-md)" }}>
          Choose which sections appear in the explanation output. Summary is always included.
        </p>
        <div className="form-group">
          <label className="form-label" style={{ display: "flex", alignItems: "center", gap: "var(--space-sm)" }}>
            <input
              type="checkbox"
              checked={includeKeyFindings}
              onChange={(e) => setIncludeKeyFindings(e.target.checked)}
            />
            Key Findings
          </label>
        </div>
        <div className="form-group">
          <label className="form-label" style={{ display: "flex", alignItems: "center", gap: "var(--space-sm)" }}>
            <input
              type="checkbox"
              checked={includeMeasurements}
              onChange={(e) => setIncludeMeasurements(e.target.checked)}
            />
            Measurements
          </label>
        </div>
      </section>

      {/* Tone & Detail Preferences */}
      <section className="settings-section">
        <h3 className="settings-section-title">Explanation Preferences</h3>
        <p className="settings-description" style={{ marginBottom: "var(--space-md)" }}>
          Adjust how explanations are generated for every analysis.
        </p>
        <div className="form-group">
          <label className="form-label">
            Tone
            <span className="slider-value-label">
              {["", "Concerning", "Straightforward", "Neutral", "Reassuring", "Very Reassuring"][tonePreference]}
            </span>
          </label>
          <div className="slider-container">
            <span className="slider-label-left">Concerning</span>
            <input
              type="range"
              className="preference-slider"
              min={1}
              max={5}
              step={1}
              value={tonePreference}
              onChange={(e) => setTonePreference(Number(e.target.value))}
            />
            <span className="slider-label-right">Very Reassuring</span>
          </div>
          <div className="slider-ticks">
            {[1, 2, 3, 4, 5].map((n) => (
              <span key={n} className={`slider-tick${tonePreference === n ? " slider-tick--active" : ""}`}>{n}</span>
            ))}
          </div>
        </div>
        <div className="form-group">
          <label className="form-label">
            Detail Level
            <span className="slider-value-label">
              {["", "Minimal", "Concise", "Moderate", "Detailed", "Very Detailed"][detailPreference]}
            </span>
          </label>
          <div className="slider-container">
            <span className="slider-label-left">Minimal</span>
            <input
              type="range"
              className="preference-slider"
              min={1}
              max={5}
              step={1}
              value={detailPreference}
              onChange={(e) => setDetailPreference(Number(e.target.value))}
            />
            <span className="slider-label-right">Very Detailed</span>
          </div>
          <div className="slider-ticks">
            {[1, 2, 3, 4, 5].map((n) => (
              <span key={n} className={`slider-tick${detailPreference === n ? " slider-tick--active" : ""}`}>{n}</span>
            ))}
          </div>
        </div>
      </section>

      {/* Physician Voice & Attribution */}
      <section className="settings-section">
        <h3 className="settings-section-title">Physician Voice & Attribution</h3>
        <p className="settings-description" style={{ marginBottom: "var(--space-md)" }}>
          Control how the physician is referenced in explanations.
        </p>

        <div className="form-group">
          <label className="form-label">Explanation Voice</label>
          <div className="literacy-options">
            <label
              className={`literacy-option ${explanationVoice === "first_person" ? "literacy-option--selected" : ""}`}
            >
              <input
                type="radio"
                name="explanation_voice"
                value="first_person"
                checked={explanationVoice === "first_person"}
                onChange={() => setExplanationVoice("first_person")}
                className="literacy-radio"
              />
              <div className="literacy-content">
                <span className="literacy-label">First Person</span>
                <span className="literacy-desc">
                  "I have reviewed your results..."
                </span>
              </div>
            </label>
            <label
              className={`literacy-option ${explanationVoice === "third_person" ? "literacy-option--selected" : ""}`}
            >
              <input
                type="radio"
                name="explanation_voice"
                value="third_person"
                checked={explanationVoice === "third_person"}
                onChange={() => setExplanationVoice("third_person")}
                className="literacy-radio"
              />
              <div className="literacy-content">
                <span className="literacy-label">Third Person</span>
                <span className="literacy-desc">
                  "Your doctor has reviewed your results..."
                </span>
              </div>
            </label>
          </div>
        </div>

        {explanationVoice === "third_person" && (
          <>
            <div className="form-group">
              <label className="form-label">Physician Name Source</label>
              <div className="literacy-options">
                <label
                  className={`literacy-option ${physicianNameSource === "auto_extract" ? "literacy-option--selected" : ""}`}
                >
                  <input
                    type="radio"
                    name="physician_name_source"
                    value="auto_extract"
                    checked={physicianNameSource === "auto_extract"}
                    onChange={() => setPhysicianNameSource("auto_extract")}
                    className="literacy-radio"
                  />
                  <div className="literacy-content">
                    <span className="literacy-label">Auto-extract from Report</span>
                    <span className="literacy-desc">
                      Detects the physician name from the scanned report and replaces "your doctor" with their name
                    </span>
                  </div>
                </label>
                <label
                  className={`literacy-option ${physicianNameSource === "custom" ? "literacy-option--selected" : ""}`}
                >
                  <input
                    type="radio"
                    name="physician_name_source"
                    value="custom"
                    checked={physicianNameSource === "custom"}
                    onChange={() => setPhysicianNameSource("custom")}
                    className="literacy-radio"
                  />
                  <div className="literacy-content">
                    <span className="literacy-label">Practice Provider</span>
                    <span className="literacy-desc">
                      Use a provider from your list below instead of "your doctor"
                    </span>
                  </div>
                </label>
                <label
                  className={`literacy-option ${physicianNameSource === "generic" ? "literacy-option--selected" : ""}`}
                >
                  <input
                    type="radio"
                    name="physician_name_source"
                    value="generic"
                    checked={physicianNameSource === "generic"}
                    onChange={() => setPhysicianNameSource("generic")}
                    className="literacy-radio"
                  />
                  <div className="literacy-content">
                    <span className="literacy-label">Generic</span>
                    <span className="literacy-desc">
                      Keep generic phrasing like "your doctor" — no name replacement
                    </span>
                  </div>
                </label>
              </div>
            </div>

            {physicianNameSource === "custom" && (
              <div className="form-group">
                <label className="form-label">Default Provider</label>
                {practiceProviders.length > 0 ? (
                  <div className="provider-buttons">
                    {practiceProviders.map((name) => (
                      <button
                        key={name}
                        type="button"
                        className={`provider-btn ${customPhysicianName === name ? "provider-btn--active" : ""}`}
                        onClick={() => setCustomPhysicianName(name)}
                      >
                        {name}
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className="settings-description">
                    Add providers below to select a default.
                  </p>
                )}
              </div>
            )}

            <div className="form-group">
              <label className="form-label" style={{ display: "flex", alignItems: "center", gap: "var(--space-sm)" }}>
                <input
                  type="checkbox"
                  checked={nameDrop}
                  onChange={(e) => setNameDrop(e.target.checked)}
                />
                Name drop: Include explicit attribution phrase (e.g., "Dr. X has reviewed your results")
              </label>
            </div>
          </>
        )}

        {/* Practice Providers List */}
        <div className="form-group" style={{ marginTop: "var(--space-lg)" }}>
          <label className="form-label">Practice Providers</label>
          <p className="settings-description" style={{ marginBottom: "var(--space-sm)" }}>
            Add physicians in your practice. These appear as buttons on the results screen to quickly attribute the report.
          </p>
          <div className="list-input-row">
            <input
              type="text"
              className="form-input"
              placeholder="e.g. Dr. Smith"
              value={newProvider}
              onChange={(e) => setNewProvider(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && newProvider.trim() && practiceProviders.length < 20) {
                  e.preventDefault();
                  if (!practiceProviders.includes(newProvider.trim())) {
                    setPracticeProviders([...practiceProviders, newProvider.trim()]);
                  }
                  setNewProvider("");
                }
              }}
            />
            <button
              className="list-add-btn"
              disabled={!newProvider.trim() || practiceProviders.length >= 20 || practiceProviders.includes(newProvider.trim())}
              onClick={() => {
                if (newProvider.trim() && practiceProviders.length < 20 && !practiceProviders.includes(newProvider.trim())) {
                  setPracticeProviders([...practiceProviders, newProvider.trim()]);
                  setNewProvider("");
                }
              }}
            >
              Add
            </button>
          </div>
          {practiceProviders.length > 0 && (
            <div className="list-items">
              {practiceProviders.map((name, i) => (
                <span key={i} className="list-item-chip">
                  {name}
                  <button
                    className="list-item-remove"
                    onClick={() => setPracticeProviders(practiceProviders.filter((_, idx) => idx !== i))}
                    aria-label={`Remove ${name}`}
                  >
                    &times;
                  </button>
                </span>
              ))}
            </div>
          )}
          <span className="list-count">{practiceProviders.length}/20</span>
        </div>
      </section>

      {/* Short Comment Settings */}
      <section className="settings-section">
        <h3 className="settings-section-title">Short Comment Settings</h3>
        <p className="settings-description" style={{ marginBottom: "var(--space-md)" }}>
          Set the character limit for short result comments. This does not affect long comments.
        </p>
        <div className="form-group">
          <label className="form-label">
            Character Limit
            <span className="slider-value-label">
              {shortCommentCharLimit === null ? "No Limit" : `${shortCommentCharLimit} chars`}
            </span>
          </label>
          <div className="slider-container">
            <span className="slider-label-left">500</span>
            <input
              type="range"
              className="preference-slider"
              min={500}
              max={4000}
              step={100}
              value={shortCommentCharLimit ?? 4000}
              disabled={shortCommentCharLimit === null}
              onChange={(e) => setShortCommentCharLimit(Number(e.target.value))}
            />
            <span className="slider-label-right">4000</span>
          </div>
          <label className="form-label" style={{ display: "flex", alignItems: "center", gap: "var(--space-sm)", marginTop: "var(--space-sm)" }}>
            <input
              type="checkbox"
              checked={shortCommentCharLimit === null}
              onChange={(e) => setShortCommentCharLimit(e.target.checked ? null : 1000)}
            />
            No limit
          </label>
        </div>
      </section>

      {/* SMS Summary Settings */}
      <section className="settings-section">
        <h3 className="settings-section-title">SMS Summary</h3>
        <p className="settings-description" style={{ marginBottom: "var(--space-md)" }}>
          Enable an ultra-short SMS-length summary tab on the results screen.
        </p>
        <div className="form-group">
          <label className="form-label" style={{ display: "flex", alignItems: "center", gap: "var(--space-sm)" }}>
            <input
              type="checkbox"
              checked={smsEnabled}
              onChange={(e) => setSmsEnabled(e.target.checked)}
            />
            Enable SMS-length summary
          </label>
        </div>
        {smsEnabled && (
          <div className="form-group">
            <label className="form-label">
              Character Limit
              <span className="slider-value-label">
                {smsCharLimit} chars
              </span>
            </label>
            <div className="slider-container">
              <span className="slider-label-left">100</span>
              <input
                type="range"
                className="preference-slider"
                min={100}
                max={500}
                step={10}
                value={smsCharLimit}
                onChange={(e) => setSmsCharLimit(Number(e.target.value))}
              />
              <span className="slider-label-right">500</span>
            </div>
          </div>
        )}
      </section>

      {/* Quick Reasons for Testing */}
      <section className="settings-section">
        <h3 className="settings-section-title">Quick Reasons for Testing</h3>
        <p className="settings-description" style={{ marginBottom: "var(--space-md)" }}>
          Add up to 20 common clinical reasons. These appear as quick-select buttons on the Import screen.
          This allows personalization of results based on reason for testing.
        </p>
        <div className="list-input-row">
          <input
            type="text"
            className="form-input"
            placeholder="e.g. Chest pain"
            value={newReason}
            onChange={(e) => setNewReason(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && newReason.trim() && quickReasons.length < 20) {
                e.preventDefault();
                if (!quickReasons.includes(newReason.trim())) {
                  setQuickReasons([...quickReasons, newReason.trim()]);
                }
                setNewReason("");
              }
            }}
          />
          <button
            className="list-add-btn"
            disabled={!newReason.trim() || quickReasons.length >= 20 || quickReasons.includes(newReason.trim())}
            onClick={() => {
              if (newReason.trim() && quickReasons.length < 20 && !quickReasons.includes(newReason.trim())) {
                setQuickReasons([...quickReasons, newReason.trim()]);
                setNewReason("");
              }
            }}
          >
            Add
          </button>
        </div>
        {quickReasons.length > 0 && (
          <div className="list-items">
            {quickReasons.map((reason, i) => (
              <span key={i} className="list-item-chip">
                {reason}
                <button
                  className="list-item-remove"
                  onClick={() => setQuickReasons(quickReasons.filter((_, idx) => idx !== i))}
                  aria-label={`Remove ${reason}`}
                >
                  &times;
                </button>
              </span>
            ))}
          </div>
        )}
        <span className="list-count">{quickReasons.length}/20</span>
      </section>

      {/* Next Steps Options */}
      <section className="settings-section">
        <h3 className="settings-section-title">Next Steps Options</h3>
        <p className="settings-description" style={{ marginBottom: "var(--space-md)" }}>
          Configure the checkboxes shown in the "Next Steps" box on the results screen.
          "No comment" is always included. Edit or remove existing options, or add new ones.
        </p>

        <div className="next-steps-list">
          {/* Codified "No comment" - always present, not editable */}
          <div className="next-step-row next-step-row--codified">
            <span className="next-step-text">No comment</span>
            <span className="next-step-badge">Always included</span>
          </div>

          {/* Editable options */}
          {nextStepsOptions.map((option, i) => (
            <div key={i} className="next-step-row">
              <input
                type="text"
                className="form-input next-step-edit-input"
                value={option}
                onChange={(e) => {
                  const updated = [...nextStepsOptions];
                  updated[i] = e.target.value;
                  setNextStepsOptions(updated);
                }}
              />
              <button
                className="list-item-remove"
                onClick={() => setNextStepsOptions(nextStepsOptions.filter((_, idx) => idx !== i))}
                aria-label={`Remove ${option}`}
              >
                &times;
              </button>
            </div>
          ))}
        </div>

        <div className="list-input-row" style={{ marginTop: "var(--space-sm)" }}>
          <input
            type="text"
            className="form-input"
            placeholder="e.g. Please schedule a follow-up appointment"
            value={newNextStep}
            onChange={(e) => setNewNextStep(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && newNextStep.trim()) {
                e.preventDefault();
                if (!nextStepsOptions.includes(newNextStep.trim())) {
                  setNextStepsOptions([...nextStepsOptions, newNextStep.trim()]);
                }
                setNewNextStep("");
              }
            }}
          />
          <button
            className="list-add-btn"
            disabled={!newNextStep.trim() || nextStepsOptions.includes(newNextStep.trim())}
            onClick={() => {
              if (newNextStep.trim() && !nextStepsOptions.includes(newNextStep.trim())) {
                setNextStepsOptions([...nextStepsOptions, newNextStep.trim()]);
                setNewNextStep("");
              }
            }}
          >
            Add
          </button>
        </div>
      </section>

      {/* Comment Footer */}
      <section className="settings-section">
        <h3 className="settings-section-title">Comment Footer</h3>
        <p className="settings-description" style={{ marginBottom: "var(--space-md)" }}>
          Choose what appears at the bottom of copied result comments.
        </p>
        <div className="form-group">
          <div className="literacy-options">
            <label
              className={`literacy-option ${footerType === "explify_branding" ? "literacy-option--selected" : ""}`}
            >
              <input
                type="radio"
                name="footer_type"
                value="explify_branding"
                checked={footerType === "explify_branding"}
                onChange={() => setFooterType("explify_branding")}
                className="literacy-radio"
              />
              <div className="literacy-content">
                <span className="literacy-label">Powered by Explify</span>
                <span className="literacy-desc">
                  "Summary powered by Explify, refined by [practice name]."
                </span>
              </div>
            </label>
            <label
              className={`literacy-option ${footerType === "ai_disclaimer" ? "literacy-option--selected" : ""}`}
            >
              <input
                type="radio"
                name="footer_type"
                value="ai_disclaimer"
                checked={footerType === "ai_disclaimer"}
                onChange={() => setFooterType("ai_disclaimer")}
                className="literacy-radio"
              />
              <div className="literacy-content">
                <span className="literacy-label">AI Disclaimer</span>
                <span className="literacy-desc">
                  "This summary was generated with AI assistance and reviewed by your healthcare provider. It is intended for informational purposes only and does not replace professional medical advice."
                </span>
              </div>
            </label>
            <label
              className={`literacy-option ${footerType === "custom" ? "literacy-option--selected" : ""}`}
            >
              <input
                type="radio"
                name="footer_type"
                value="custom"
                checked={footerType === "custom"}
                onChange={() => setFooterType("custom")}
                className="literacy-radio"
              />
              <div className="literacy-content">
                <span className="literacy-label">Custom</span>
                <span className="literacy-desc">
                  Enter your own footer text below.
                </span>
              </div>
            </label>
            <label
              className={`literacy-option ${footerType === "none" ? "literacy-option--selected" : ""}`}
            >
              <input
                type="radio"
                name="footer_type"
                value="none"
                checked={footerType === "none"}
                onChange={() => setFooterType("none")}
                className="literacy-radio"
              />
              <div className="literacy-content">
                <span className="literacy-label">None</span>
                <span className="literacy-desc">
                  No footer will be appended to comments.
                </span>
              </div>
            </label>
          </div>
        </div>
        {footerType === "custom" && (
          <div className="form-group">
            <label className="form-label">Custom Footer Text</label>
            <textarea
              className="form-input"
              rows={3}
              placeholder="Enter your custom footer text..."
              value={customFooterText}
              onChange={(e) => setCustomFooterText(e.target.value)}
              style={{ resize: "vertical" }}
            />
          </div>
        )}
      </section>

      {/* Auto-save Status */}
      <div className="settings-actions">
        {saving && <span className="save-status">Saving...</span>}
        {success && <span className="save-success">Settings saved.</span>}
        {error && <span className="save-error">{error}</span>}
      </div>

      {/* Sharing */}
      <SharingPanel />

      {/* About */}
      <section className="settings-section about-section">
        <h3 className="settings-section-title">About</h3>
        <p className="settings-description">
          Explify v{appVersion || "..."}
        </p>
        <div className="about-update-row">
          {updateCheck ? (
            <button
              className="save-btn"
              onClick={handleApplyUpdate}
              disabled={updateStatus === "updating"}
            >
              {updateStatus === "updating"
                ? "Updating..."
                : `Update to v${updateCheck.version}`}
            </button>
          ) : (
            <button
              className="save-btn about-check-btn"
              onClick={handleCheckForUpdates}
              disabled={updateStatus === "checking"}
            >
              {updateStatus === "checking" ? "Checking..." : "Check for Updates"}
            </button>
          )}
          {updateStatus === "up-to-date" && (
            <span className="save-success">You're on the latest version.</span>
          )}
        </div>
      </section>
    </div>
  );
}
