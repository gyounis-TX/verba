import { useState, useEffect, useRef } from "react";
import { sidecarApi } from "../../services/sidecarApi";
import { useToast } from "../shared/Toast";
import type { ExtractionResult, ExplainResponse } from "../../types/sidecar";
import "../shared/TypeModal.css";

interface QuickNormalModalProps {
  extractionResult: ExtractionResult;
  testType: string;
  testTypeDisplay: string;
  clinicalContext?: string;
  quickReasons?: string[];
  onClose: () => void;
  onViewFullAnalysis: () => void;
}

export default function QuickNormalModal({
  extractionResult,
  testType,
  testTypeDisplay,
  clinicalContext,
  quickReasons,
  onClose,
  onViewFullAnalysis,
}: QuickNormalModalProps) {
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [message, setMessage] = useState("");
  const [response, setResponse] = useState<ExplainResponse | null>(null);
  const [copied, setCopied] = useState(false);
  const [saved, setSaved] = useState(false);
  const { showToast } = useToast();
  const abortRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await sidecarApi.explainReport({
          extraction_result: extractionResult,
          test_type: testType,
          quick_normal: true,
          short_comment: true,
          clinical_context: clinicalContext || undefined,
          quick_reasons: quickReasons,
        });
        if (cancelled || abortRef.current) return;
        setResponse(resp);
        setMessage(resp.explanation.overall_summary);
        setStatus("success");
      } catch (err) {
        if (cancelled || abortRef.current) return;
        setStatus("error");
      }
    })();
    return () => { cancelled = true; };
  }, [extractionResult, testType, clinicalContext, quickReasons]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message);
      setCopied(true);
      showToast("success", "Copied to clipboard");
      setTimeout(() => setCopied(false), 2000);

      // Save to history (fire-and-forget)
      if (response && !saved) {
        setSaved(true);
        sidecarApi.saveHistory({
          test_type: testType,
          test_type_display: testTypeDisplay,
          filename: null,
          summary: message,
          full_response: response,
        }).catch(() => {
          // Non-critical — history save failure is OK
        });
      }
    } catch {
      showToast("error", "Failed to copy to clipboard");
    }
  };

  const handleFullAnalysis = () => {
    abortRef.current = true;
    onViewFullAnalysis();
  };

  return (
    <div className="type-modal-backdrop" onClick={onClose}>
      <div
        className="type-modal"
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: 480 }}
      >
        <h3 className="type-modal-title">Quick Normal</h3>
        <p className="type-modal-subtitle">
          All measurements within normal range for this {testTypeDisplay}.
        </p>

        {status === "loading" && (
          <div className="quick-normal-loading">
            <span className="quick-normal-spinner" />
            <span>Generating reassurance message...</span>
          </div>
        )}

        {status === "error" && (
          <div className="quick-normal-error">
            <p>Failed to generate message.</p>
            <button className="quick-normal-btn quick-normal-btn--secondary" onClick={handleFullAnalysis}>
              Try Full Analysis
            </button>
          </div>
        )}

        {status === "success" && (
          <>
            <div className="quick-normal-result">
              <p className="quick-normal-text">{message}</p>
            </div>
            <div className="type-modal-actions">
              <button className="quick-normal-btn quick-normal-btn--secondary" onClick={handleFullAnalysis}>
                Full Analysis
              </button>
              <button className="quick-normal-btn quick-normal-btn--primary" onClick={handleCopy}>
                {copied ? "Copied!" : "Copy to Clipboard"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
