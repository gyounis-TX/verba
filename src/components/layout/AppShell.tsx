import { useState, useEffect, useCallback, useRef } from "react";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { useSidecar } from "../../hooks/useSidecar";
import { useIdleTimeout } from "../../hooks/useIdleTimeout";
import { sidecarApi } from "../../services/sidecarApi";
import { getSession, onAuthStateChange, isAuthConfigured, signOut } from "../../services/supabase";
import { ConsentDialog } from "../shared/ConsentDialog";
import { BAADialog } from "../shared/BAADialog";
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
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Auth gate state
  const [authChecked, setAuthChecked] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  // BAA gate state (web mode only)
  const [baaChecked, setBaaChecked] = useState(false);
  const [baaAccepted, setBaaAccepted] = useState(false);

  // Check existing session and listen for auth changes
  useEffect(() => {
    if (!isAuthConfigured()) {
      // Auth not configured (desktop mode or missing env vars) — skip login
      setIsAuthenticated(true);
      setAuthChecked(true);
      return;
    }
    getSession()
      .then((session) => {
        setIsAuthenticated(!!session);
        setAuthChecked(true);
      })
      .catch(() => {
        // getSession failed — allow through gracefully
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
    // Close mobile sidebar on navigation
    setSidebarOpen(false);
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

  // Check BAA status after authentication (web mode only)
  useEffect(() => {
    if (!isReady || !isAuthenticated) return;
    if (!isAuthConfigured()) {
      // Desktop/Tauri mode — no BAA needed
      setBaaAccepted(true);
      setBaaChecked(true);
      return;
    }
    let cancelled = false;
    sidecarApi
      .getBAAStatus()
      .then((res) => {
        if (!cancelled) {
          setBaaAccepted(res.accepted);
          setBaaChecked(true);
        }
      })
      .catch(() => {
        if (!cancelled) {
          // BAA API failed — allow through gracefully
          setBaaAccepted(true);
          setBaaChecked(true);
        }
      });
    return () => { cancelled = true; };
  }, [isReady, isAuthenticated]);

  // Check onboarding status after consent is given, user is authenticated, and BAA accepted
  useEffect(() => {
    if (!isReady || !consentGiven || !isAuthenticated || !baaAccepted) return;
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
  }, [isReady, consentGiven, isAuthenticated, baaAccepted]);

  const handleConsent = () => {
    sidecarApi.grantConsent().catch(() => {});
    setConsentGiven(true);
  };

  const handleBAAAccept = () => {
    sidecarApi.acceptBAA().catch(() => {});
    setBaaAccepted(true);
  };

  const handleBAADecline = () => {
    signOut().catch(() => {});
    setIsAuthenticated(false);
  };

  const handleOnboardingComplete = () => {
    sidecarApi.completeOnboarding().catch(() => {});
    setOnboardingCompleted(true);
  };

  // HIPAA §164.312(a)(2)(iii) — auto-logoff after 30 min idle (web mode only)
  useIdleTimeout({
    timeoutMs: 30 * 60_000,
    enabled: isAuthConfigured() && isAuthenticated,
    onWarn: () => {
      // Could show a toast/modal here; for now just console
      console.warn("Session will expire in 1 minute due to inactivity.");
    },
    onLogout: () => {
      signOut().catch(() => {});
      setIsAuthenticated(false);
    },
  });

  return (
    <div className="app-shell">
      <button
        className="mobile-menu-btn"
        onClick={() => setSidebarOpen((v) => !v)}
        aria-label={sidebarOpen ? "Close menu" : "Open menu"}
      >
        {sidebarOpen ? "\u2715" : "\u2630"}
      </button>
      {sidebarOpen && (
        <div className="sidebar-overlay sidebar-overlay--visible" onClick={() => setSidebarOpen(false)} />
      )}
      <Sidebar className={sidebarOpen ? "sidebar--open" : ""} />
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
        ) : !baaChecked ? (
          <div className="sidecar-loading">
            <p>Loading...</p>
          </div>
        ) : !baaAccepted ? (
          <BAADialog onAccept={handleBAAAccept} onDecline={handleBAADecline} />
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
