import { useState, useEffect, useCallback, useRef } from "react";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { useSidecar } from "../../hooks/useSidecar";
import { sidecarApi } from "../../services/sidecarApi";
import { ConsentDialog } from "../shared/ConsentDialog";
import "./AppShell.css";

export function AppShell() {
  const { isReady, error } = useSidecar();
  const navigate = useNavigate();
  const location = useLocation();
  const [consentChecked, setConsentChecked] = useState(false);
  const [consentGiven, setConsentGiven] = useState(false);
  const [showSetupBanner, setShowSetupBanner] = useState(false);
  const prevPathRef = useRef(location.pathname);

  const checkSpecialty = useCallback(() => {
    if (!isReady || !consentGiven) return;
    sidecarApi
      .getSettings()
      .then((s) => {
        setShowSetupBanner(!s.specialty);
      })
      .catch(() => {});
  }, [isReady, consentGiven]);

  // Initial check when ready
  useEffect(() => {
    checkSpecialty();
  }, [checkSpecialty]);

  // Re-check after navigating away from settings (user may have saved)
  useEffect(() => {
    const prev = prevPathRef.current;
    prevPathRef.current = location.pathname;
    if (prev === "/settings" && location.pathname !== "/settings") {
      checkSpecialty();
    }
  }, [location.pathname, checkSpecialty]);

  useEffect(() => {
    if (!isReady) return;
    sidecarApi
      .getConsent()
      .then((res) => {
        setConsentGiven(res.consent_given);
        setConsentChecked(true);
      })
      .catch(() => {
        // Consent API failed — allow through gracefully
        setConsentGiven(true);
        setConsentChecked(true);
      });
  }, [isReady]);

  const handleConsent = () => {
    sidecarApi.grantConsent().catch(() => {});
    setConsentGiven(true);
  };

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="app-content">
        {error ? (
          <div className="sidecar-error">
            <h2>Connection Error</h2>
            <p>{error}</p>
          </div>
        ) : !isReady || !consentChecked ? (
          <div className="sidecar-loading">
            <p>Starting backend services...</p>
          </div>
        ) : !consentGiven ? (
          <ConsentDialog onConsent={handleConsent} />
        ) : (
          <>
            {showSetupBanner && (
              <div className="setup-banner">
                <span>Please configure your specialty in Settings.</span>
                <button
                  className="setup-banner-btn"
                  onClick={() => navigate("/settings")}
                >
                  Go to Settings
                </button>
              </div>
            )}
            <Outlet />
          </>
        )}
      </main>
    </div>
  );
}
