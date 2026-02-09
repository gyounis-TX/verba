import { useState, useEffect, useCallback, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { sidecarApi } from "../../services/sidecarApi";
import { logUsage } from "../../services/usageTracker";
import { useToast } from "../shared/Toast";
import type { ExtractionResult, ExplainResponse } from "../../types/sidecar";
import "./ProcessingScreen.css";

type ProcessingStep = "detecting" | "parsing" | "explaining" | "validating" | "done" | "error";

interface StepInfo {
  id: ProcessingStep;
  label: string;
  description: string;
}

const STEPS: StepInfo[] = [
  {
    id: "detecting",
    label: "Detecting Report Type",
    description: "Identifying the type of medical test...",
  },
  {
    id: "parsing",
    label: "Parsing Report",
    description: "Extracting measurements and findings...",
  },
  {
    id: "explaining",
    label: "Generating Explanation",
    description: "Creating a plain-language explanation...",
  },
  {
    id: "validating",
    label: "Validating Results",
    description: "Checking response quality...",
  },
];

interface CategorizedError {
  category: string;
  title: string;
  message: string;
  suggestion: string;
  suggestions?: string[];
}

function categorizeError(errorMessage: string): CategorizedError {
  const lower = errorMessage.toLowerCase();

  if (lower.includes("api key") || lower.includes("no api key") || lower.includes("authentication")) {
    const provider = lower.includes("openai") ? "OpenAI" : lower.includes("claude") || lower.includes("anthropic") ? "Claude" : "AI";
    return {
      category: "auth",
      title: "API Key Issue",
      message: errorMessage,
      suggestion: `Your ${provider} API key isn't working. It may have expired or the format is incorrect.`,
      suggestions: [
        "Check that your API key is entered correctly in Settings",
        `Verify the key hasn't expired on your ${provider} dashboard`,
        "Try switching to a different AI provider in Settings",
      ],
    };
  }

  if (lower.includes("rate limit") || lower.includes("quota") || lower.includes("429")) {
    return {
      category: "quota",
      title: "Rate Limit Reached",
      message: errorMessage,
      suggestion: "You've hit the API rate limit.",
      suggestions: [
        "Wait 60 seconds and try again",
        "Switch to a different model in Settings",
        "If this keeps happening, check your API plan usage limits",
      ],
    };
  }

  if (lower.includes("timeout") || lower.includes("timed out")) {
    return {
      category: "timeout",
      title: "Request Timed Out",
      message: errorMessage,
      suggestion: "The request timed out. This can happen with very long reports.",
      suggestions: [
        "Try again — it may work on a second attempt",
        "Use Short Comment mode for faster results",
        "Try switching to a faster model in Settings",
      ],
    };
  }

  if (lower.includes("network") || lower.includes("fetch") || lower.includes("connection")) {
    return {
      category: "network",
      title: "Network Error",
      message: errorMessage,
      suggestion: "Can't reach the AI service.",
      suggestions: [
        "Check your internet connection",
        "If you're behind a VPN or firewall, it may be blocking API calls",
        "Try again in a few moments",
      ],
    };
  }

  if (lower.includes("parse") || lower.includes("validation") || lower.includes("invalid")) {
    return {
      category: "parse",
      title: "Processing Error",
      message: errorMessage,
      suggestion: "We couldn't extract structured data from this report.",
      suggestions: [
        "The file may be a scanned image with low quality",
        "Try uploading a clearer PDF or pasting the text directly",
        "If this is an uncommon report type, try selecting the type manually",
      ],
    };
  }

  const truncatedMsg = errorMessage.length > 100 ? errorMessage.slice(0, 100) + "..." : errorMessage;
  return {
    category: "unknown",
    title: "Processing Failed",
    message: errorMessage,
    suggestion: `Something unexpected went wrong: ${truncatedMsg}`,
    suggestions: [
      "Try again — the issue may be temporary",
      "Try a different file or paste the text directly",
      "If the problem persists, restart the app",
    ],
  };
}

export function ProcessingScreen() {
  const location = useLocation();
  const navigate = useNavigate();
  const locationState = location.state as {
    extractionResult?: ExtractionResult;
    templateId?: number;
    sharedTemplateSyncId?: string;
    clinicalContext?: string;
    testType?: string;
    quickReasons?: string[];
    batchExtractionResults?: Array<{ key: string; result: ExtractionResult }>;
    testTypes?: Record<string, string>;
  } | null;
  const extractionResult = locationState?.extractionResult;
  const templateId = locationState?.templateId;
  const sharedTemplateSyncId = locationState?.sharedTemplateSyncId;
  const clinicalContext = locationState?.clinicalContext;
  const testType = locationState?.testType;
  const quickReasons = locationState?.quickReasons;
  const batchExtractionResults = locationState?.batchExtractionResults;
  const testTypes = locationState?.testTypes;
  const isBatchMode = batchExtractionResults != null && batchExtractionResults.length > 1;

  const { showToast } = useToast();
  const [currentStep, setCurrentStep] =
    useState<ProcessingStep>("detecting");
  const [stepMessages, setStepMessages] = useState<Record<string, string>>({});
  const [error, setError] = useState<CategorizedError | null>(null);
  const [deepAnalysis, setDeepAnalysis] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const startTimeRef = useRef(Date.now());

  // Batch state
  interface BatchFileStatus {
    key: string;
    filename: string;
    result: ExtractionResult;
    status: "waiting" | "processing" | "done" | "error";
    step: ProcessingStep;
    stepMessages: Record<string, string>;
    response?: ExplainResponse;
    errorInfo?: CategorizedError;
  }
  const [batchFiles, setBatchFiles] = useState<BatchFileStatus[]>(() => {
    if (!isBatchMode || !batchExtractionResults) return [];
    return batchExtractionResults.map((br) => ({
      key: br.key,
      filename: br.result.filename || br.key.split("::")[0],
      result: br.result,
      status: "waiting" as const,
      step: "detecting" as const,
      stepMessages: {},
    }));
  });

  // Elapsed timer
  useEffect(() => {
    startTimeRef.current = Date.now();
    const interval = setInterval(() => {
      setElapsed((Date.now() - startTimeRef.current) / 1000);
    }, 100);
    return () => clearInterval(interval);
  }, []);

  const runPipeline = useCallback(async () => {
    if (!extractionResult) {
      setError(categorizeError("No extraction result found. Please import a report first."));
      setCurrentStep("error");
      return;
    }

    try {
      const stream = sidecarApi.explainReportStream({
        extraction_result: extractionResult,
        test_type: testType,
        template_id: templateId,
        shared_template_sync_id: sharedTemplateSyncId,
        clinical_context: clinicalContext,
        short_comment: true,
        deep_analysis: deepAnalysis || undefined,
        quick_reasons: quickReasons,
      });

      for await (const event of stream) {
        if (event.stage === "error") {
          setError(categorizeError(event.message ?? "Processing failed."));
          setCurrentStep("error");
          return;
        }

        if (event.stage === "done") {
          const response = event.data as ExplainResponse;
          logUsage({
            model_used: response.model_used,
            input_tokens: response.input_tokens,
            output_tokens: response.output_tokens,
            request_type: "explain",
            deep_analysis: deepAnalysis,
          });

          sidecarApi
            .saveHistory({
              test_type: response.parsed_report.test_type,
              test_type_display: response.parsed_report.test_type_display,
              filename: extractionResult.filename ?? null,
              summary: response.explanation.overall_summary.slice(0, 200),
              full_response: response,
            })
            .catch(() => {
              showToast("error", "Analysis complete but failed to save to history.");
            });

          setCurrentStep("done");
          navigate("/results", {
            state: {
              explainResponse: response,
              extractionResult,
              templateId,
              clinicalContext,
              quickReasons,
            },
          });
          return;
        }

        // Progress event
        const stage = event.stage as ProcessingStep;
        setCurrentStep(stage);
        if (event.message) {
          setStepMessages((prev) => ({ ...prev, [stage]: event.message! }));
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Processing failed.";
      setError(categorizeError(msg));
      setCurrentStep("error");
    }
  }, [extractionResult, templateId, sharedTemplateSyncId, clinicalContext, quickReasons, testType, deepAnalysis, navigate, showToast]);

  useEffect(() => {
    if (isBatchMode) return;
    runPipeline();
  }, [runPipeline, isBatchMode]);

  // Batch pipeline
  const batchStartedRef = useRef(false);
  useEffect(() => {
    if (!isBatchMode || batchStartedRef.current || !batchExtractionResults) return;
    batchStartedRef.current = true;

    async function processBatch() {
      const responses: ExplainResponse[] = [];
      const labels: string[] = [];
      const usedOpenings: string[] = [];
      const batchSummaries: Array<{ label: string; test_type_display: string; measurements_summary: string }> = [];

      for (let i = 0; i < batchExtractionResults!.length; i++) {
        const br = batchExtractionResults![i];
        const filename = br.result.filename || br.key.split("::")[0];

        setBatchFiles((prev) =>
          prev.map((f, idx) =>
            idx === i ? { ...f, status: "processing", step: "detecting" as ProcessingStep } : f,
          ),
        );

        try {
          const stream = sidecarApi.explainReportStream({
            extraction_result: br.result,
            test_type: testTypes?.[br.key] ?? testType,
            template_id: templateId,
            shared_template_sync_id: sharedTemplateSyncId,
            clinical_context: clinicalContext,
            short_comment: true,
            quick_reasons: quickReasons,
            avoid_openings: usedOpenings.length > 0 ? usedOpenings : undefined,
            batch_prior_summaries: batchSummaries.length > 0 ? batchSummaries : undefined,
          });

          let fileResponse: ExplainResponse | null = null;

          for await (const event of stream) {
            if (event.stage === "error") {
              setBatchFiles((prev) =>
                prev.map((f, idx) =>
                  idx === i
                    ? { ...f, status: "error", errorInfo: categorizeError(event.message ?? "Processing failed.") }
                    : f,
                ),
              );
              break;
            }

            if (event.stage === "done") {
              fileResponse = event.data as ExplainResponse;
              setBatchFiles((prev) =>
                prev.map((f, idx) =>
                  idx === i ? { ...f, status: "done", response: fileResponse! } : f,
                ),
              );
              break;
            }

            const stage = event.stage as ProcessingStep;
            setBatchFiles((prev) =>
              prev.map((f, idx) =>
                idx === i
                  ? {
                      ...f,
                      step: stage,
                      stepMessages: event.message
                        ? { ...f.stepMessages, [stage]: event.message }
                        : f.stepMessages,
                    }
                  : f,
              ),
            );
          }

          if (fileResponse) {
            // Extract the opening sentence to avoid repetition in next reports
            const summary = fileResponse.explanation.overall_summary;
            const firstSentence = summary.split(/[.!?]\s/)[0]?.trim();
            if (firstSentence) usedOpenings.push(firstSentence);

            // Build cross-type summary for subsequent entries
            const measurements = fileResponse.explanation.measurements || [];
            const mSummary = measurements
              .slice(0, 5)
              .map((m: { abbreviation: string; value: number; unit: string; status: string }) =>
                `${m.abbreviation}: ${m.value} ${m.unit} [${m.status}]`)
              .join("; ");
            if (mSummary) {
              batchSummaries.push({
                label: filename,
                test_type_display: fileResponse.parsed_report.test_type_display || "Unknown",
                measurements_summary: mSummary,
              });
            }

            responses.push(fileResponse);
            labels.push(fileResponse.parsed_report.test_type_display || filename);
            logUsage({
              model_used: fileResponse.model_used,
              input_tokens: fileResponse.input_tokens,
              output_tokens: fileResponse.output_tokens,
              request_type: "explain",
              deep_analysis: deepAnalysis,
            });
            sidecarApi
              .saveHistory({
                test_type: fileResponse.parsed_report.test_type,
                test_type_display: fileResponse.parsed_report.test_type_display,
                filename: br.result.filename ?? null,
                summary: fileResponse.explanation.overall_summary.slice(0, 200),
                full_response: fileResponse,
              })
              .catch(() => {});
          }
        } catch (err) {
          const msg = err instanceof Error ? err.message : "Processing failed.";
          setBatchFiles((prev) =>
            prev.map((f, idx) =>
              idx === i ? { ...f, status: "error", errorInfo: categorizeError(msg) } : f,
            ),
          );
        }
      }

      if (responses.length === 1) {
        navigate("/results", {
          state: {
            explainResponse: responses[0],
            extractionResult: batchExtractionResults![0].result,
            templateId,
            clinicalContext,
            quickReasons,
          },
        });
      } else if (responses.length > 1) {
        navigate("/results", {
          state: {
            explainResponse: responses[0],
            extractionResult: batchExtractionResults![0].result,
            batchResponses: responses,
            batchLabels: labels,
            templateId,
            clinicalContext,
            quickReasons,
          },
        });
      }
    }

    processBatch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isBatchMode]);

  const currentStepIndex = STEPS.findIndex((s) => s.id === currentStep);

  // ---------------------------------------------------------------------------
  // Batch mode rendering
  // ---------------------------------------------------------------------------
  if (isBatchMode) {
    const doneCount = batchFiles.filter((f) => f.status === "done").length;
    const allSettled = batchFiles.every((f) => f.status === "done" || f.status === "error");
    const allFailed = batchFiles.every((f) => f.status === "error");

    return (
      <div className="processing-screen">
        <header className="processing-header">
          <h2 className="processing-title">
            Analyzing Reports ({doneCount} of {batchFiles.length})
          </h2>
        </header>

        <div className="batch-file-list">
          {batchFiles.map((file) => (
            <div key={file.key} className={`batch-file-card batch-file-card--${file.status}`}>
              <div className="batch-file-header">
                <span className="batch-file-name">{file.filename}</span>
                <span className={`batch-file-badge batch-file-badge--${file.status}`}>
                  {file.status === "waiting" && "Waiting"}
                  {file.status === "processing" && "Processing"}
                  {file.status === "done" && "Done"}
                  {file.status === "error" && "Failed"}
                </span>
              </div>

              {file.status === "processing" && (
                <div className="batch-file-steps">
                  {STEPS.map((step, stepIdx) => {
                    const curIdx = STEPS.findIndex((s) => s.id === file.step);
                    const isDone = curIdx > stepIdx;
                    const isActive = step.id === file.step;
                    return (
                      <span
                        key={step.id}
                        className={`batch-step ${isDone ? "batch-step--done" : isActive ? "batch-step--active" : "batch-step--pending"}`}
                      >
                        {isDone ? "\u2713" : isActive ? "\u27F3" : "\u25CB"} {step.label}
                      </span>
                    );
                  })}
                </div>
              )}

              {file.status === "processing" && (
                <p className="batch-file-message">
                  {file.stepMessages[file.step] || STEPS.find((s) => s.id === file.step)?.description}
                </p>
              )}

              {file.status === "error" && file.errorInfo && (
                <p className="batch-file-error">{file.errorInfo.suggestion}</p>
              )}
            </div>
          ))}
        </div>

        <div className="batch-progress">
          <div className="batch-progress-bar">
            <div
              className="batch-progress-fill"
              style={{ width: `${(doneCount / batchFiles.length) * 100}%` }}
            />
          </div>
          <span className="batch-progress-text">
            {doneCount}/{batchFiles.length} complete
          </span>
        </div>

        {!allSettled && (
          <div className="processing-elapsed">Elapsed: {elapsed.toFixed(1)}s</div>
        )}

        {allSettled && allFailed && (
          <div className="processing-error">
            <p className="error-title">All files failed to process</p>
            <div className="error-actions">
              <button className="retry-btn" onClick={() => navigate("/")}>
                Back to Import
              </button>
            </div>
          </div>
        )}
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Single file mode rendering
  // ---------------------------------------------------------------------------
  return (
    <div className="processing-screen">
      <header className="processing-header">
        <h2 className="processing-title">Analyzing Report</h2>
        <label className="deep-analysis-toggle">
          <input
            type="checkbox"
            checked={deepAnalysis}
            onChange={(e) => setDeepAnalysis(e.target.checked)}
          />
          <span className="deep-analysis-label">Deep Analysis</span>
          <span className="deep-analysis-subtext">For complex cases only</span>
        </label>
      </header>

      <div className="processing-steps">
        {STEPS.map((step, index) => {
          const isActive = step.id === currentStep;
          const isComplete =
            currentStepIndex > index || currentStep === "done";
          const isPending =
            currentStepIndex < index && currentStep !== "error";
          const isErrorStep =
            currentStep === "error" && currentStepIndex === index;

          return (
            <div
              key={step.id}
              className={`processing-step ${
                isActive
                  ? "processing-step--active"
                  : isComplete
                    ? "processing-step--complete"
                    : isErrorStep
                      ? "processing-step--error"
                      : isPending
                        ? "processing-step--pending"
                        : "processing-step--pending"
              }`}
            >
              <div className="step-indicator">
                {isComplete ? (
                  <span className="step-check">&#10003;</span>
                ) : isActive ? (
                  <div className="step-spinner" />
                ) : isErrorStep ? (
                  <span className="step-error-icon">&#10007;</span>
                ) : (
                  <span className="step-number">{index + 1}</span>
                )}
              </div>
              <div className="step-content">
                <span className="step-label">{step.label}</span>
                <span className="step-description">
                  {stepMessages[step.id] || step.description}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {currentStep !== "done" && currentStep !== "error" && (
        <div className="processing-elapsed">
          Elapsed: {elapsed.toFixed(1)}s
        </div>
      )}

      {currentStep === "error" && error && (
        <div className="processing-error">
          <p className="error-title">{error.title}</p>
          <p className="error-suggestion">{error.suggestion}</p>
          {error.suggestions && error.suggestions.length > 0 && (
            <ul className="error-suggestions-list">
              {error.suggestions.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          )}
          <div className="error-actions">
            {["network", "timeout", "quota"].includes(error.category) && (
              <button
                className="retry-btn"
                onClick={() => {
                  setError(null);
                  setStepMessages({});
                  setCurrentStep("detecting");
                  startTimeRef.current = Date.now();
                  runPipeline();
                }}
              >
                Retry
              </button>
            )}
            {["auth", "timeout"].includes(error.category) && (
              <button
                className="retry-btn"
                onClick={() => navigate("/settings")}
              >
                Go to Settings
              </button>
            )}
            <button
              className="retry-btn"
              onClick={() => navigate("/")}
            >
              Back to Import
            </button>
          </div>
        </div>
      )}

      {currentStep === "done" && (
        <div className="processing-complete">
          <p>Redirecting to results...</p>
        </div>
      )}
    </div>
  );
}
