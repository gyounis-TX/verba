import { useState, useEffect, useCallback, useRef } from "react";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { useSidecar } from "../../hooks/useSidecar";
import { sidecarApi } from "../../services/sidecarApi";
import { getSession, onAuthStateChange } from "../../services/supabase";
import { ConsentDialog } from "../shared/ConsentDialog";
import { OnboardingWizard } from "../onboarding/OnboardingWizard";
import { AuthScreen } from "../auth/AuthScreen";
import "./AppShell.css";

export function AppShell() {
  const { isReady, error } = useSidecar();
  const navigate = useNavigate();
  const location = useLocation();
  const [consentChecked, setConsentChecked] = useState(false);
  const [consentGiven, setConsentGiven] = useState(false);
  const [showSetupBanner, setShowSetupBanner] = useState(false);
  const [onboardingChecked, setOnboardingChecked] = useState(false);
  const [onboardingCompleted, setOnboardingCompleted] = useState(false);
  const prevPathRef = useRef(location.pathname);

  // Auth gate state
  const [authChecked, setAuthChecked] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  // Check existing session and listen for auth changes
  useEffect(() => {
    getSession()
      .then(async (session) => {
        if (session) {
          setIsAuthenticated(true);
          setAuthChecked(true);
          return;
        }
        // No session — check if Supabase is actually reachable before
        // requiring login. If it's down, skip auth entirely.
        const supabaseUrl = (import.meta.env.VITE_SUPABASE_URL ?? "").trim();
        if (!supabaseUrl) {
          setIsAuthenticated(true);
          setAuthChecked(true);
          return;
        }
        try {
          const ctrl = new AbortController();
          const timer = setTimeout(() => ctrl.abort(), 5000);
          await fetch(`${supabaseUrl}/auth/v1/health`, { signal: ctrl.signal });
          clearTimeout(timer);
          // Supabase reachable but no session — require login
          setIsAuthenticated(false);
          setAuthChecked(true);
        } catch {
          // Supabase unreachable — allow through gracefully
          setIsAuthenticated(true);
          setAuthChecked(true);
        }
      })
      .catch(() => {
        // getSession itself failed — allow through gracefully
        setIsAuthenticated(true);
        setAuthChecked(true);
      });
    const unsubscribe = onAuthStateChange((session) => {
      setIsAuthenticated(!!session);
    });
    return () => unsubscribe?.();
  }, []);

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

  // Check onboarding status after consent is given and user is authenticated
  useEffect(() => {
    if (!isReady || !consentGiven || !isAuthenticated) return;
    let cancelled = false;
    sidecarApi
      .getOnboarding()
      .then((res) => {
        if (!cancelled) {
          setOnboardingCompleted(res.onboarding_completed);
          setOnboardingChecked(true);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setOnboardingCompleted(true);
          setOnboardingChecked(true);
        }
      });
    return () => { cancelled = true; };
  }, [isReady, consentGiven, isAuthenticated]);

  const handleConsent = () => {
    sidecarApi.grantConsent().catch(() => {});
    setConsentGiven(true);
  };

  const handleOnboardingComplete = () => {
    sidecarApi.completeOnboarding().catch(() => {});
    setOnboardingCompleted(true);
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
        ) : !authChecked ? (
          <div className="sidecar-loading">
            <p>Loading...</p>
          </div>
        ) : !isAuthenticated ? (
          <AuthScreen onAuthSuccess={() => {
            setIsAuthenticated(true);
            navigate("/import");
          }} />
        ) : !onboardingChecked ? (
          <div className="sidecar-loading">
            <p>Loading...</p>
          </div>
        ) : !onboardingCompleted ? (
          <OnboardingWizard onComplete={handleOnboardingComplete} />
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
                <button
                  className="setup-banner-dismiss"
                  onClick={() => setShowSetupBanner(false)}
                  aria-label="Dismiss"
                >
                  &times;
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
