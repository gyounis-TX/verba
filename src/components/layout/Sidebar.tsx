import { useState, useEffect, useCallback, useMemo } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { getSession, signOut, onAuthStateChange } from "../../services/supabase";
import { isSupabaseConfigured, fullSync } from "../../services/syncEngine";
import { isAdmin } from "../../services/adminAuth";
import { IS_TAURI } from "../../services/platform";
import "./Sidebar.css";

const baseNavItems = [
  { path: "/", label: "Import" },
  { path: "/results", label: "Explanation" },
  { path: "/history", label: "History" },
  { path: "/teaching-points", label: "Teaching Points" },
  { path: "/templates", label: "Templates" },
  { path: "/settings", label: "Settings" },
];

const TAGLINES = [
  "Explain better",
  "When smartphrases aren't enough",
  "Nonhumans helping humans help humans",
  "Turning results into understanding",
  "Clear explanations. Less typing.",
  "Make every result understandable",
  "Transforming complexity to clarity",
  "Because your time matters",
];

function getDailyTagline(): string {
  const now = new Date();
  const startOfYear = new Date(now.getFullYear(), 0, 0);
  const diff = now.getTime() - startOfYear.getTime();
  const dayOfYear = Math.floor(diff / (1000 * 60 * 60 * 24));
  return TAGLINES[dayOfYear % TAGLINES.length];
}

function getNavItems(userEmail: string | null) {
  if (isAdmin(userEmail)) {
    return [...baseNavItems, { path: "/admin", label: "Admin" }];
  }
  return baseNavItems;
}

interface UpdateInfo {
  version: string;
  available: boolean;
}

export function Sidebar() {
  const navigate = useNavigate();
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null);
  const [isInstalling, setIsInstalling] = useState(false);
  const [showUpdatePrompt, setShowUpdatePrompt] = useState(false);
  const [isSignedIn, setIsSignedIn] = useState(false);
  const [userEmail, setUserEmail] = useState<string | null>(null);

  useEffect(() => {
    if (!isSupabaseConfigured()) return;
    getSession().then((session) => {
      setIsSignedIn(!!session);
      setUserEmail(session?.user?.email ?? null);
      if (session) fullSync().catch(() => {});
    });
    const unsub = onAuthStateChange((session) => {
      setIsSignedIn(!!session);
      setUserEmail(session?.user?.email ?? null);
      if (session) fullSync().catch(() => {});
    });
    return unsub;
  }, []);

  const handleSignOut = useCallback(async () => {
    await signOut();
    setIsSignedIn(false);
    setUserEmail(null);
  }, []);

  useEffect(() => {
    if (!IS_TAURI) return;

    let cancelled = false;

    const checkUpdate = async () => {
      try {
        const { check } = await import("@tauri-apps/plugin-updater");
        const update = await check();
        if (update && !cancelled) {
          setUpdateInfo({ version: update.version, available: true });
        }
      } catch {
        // Updater not available or failed silently
      }
    };

    checkUpdate(); // Check immediately on mount

    // Re-check every 24 hours
    const interval = setInterval(checkUpdate, 24 * 60 * 60 * 1000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const handleUpdateClick = useCallback(() => {
    if (!isInstalling) setShowUpdatePrompt((prev) => !prev);
  }, [isInstalling]);

  const handleInstallUpdate = useCallback(async () => {
    setShowUpdatePrompt(false);
    setIsInstalling(true);
    try {
      const { check } = await import("@tauri-apps/plugin-updater");
      const update = await check();
      if (update) {
        if (navigator.userAgent.includes("Windows")) {
          try {
            const { invoke } = await import("@tauri-apps/api/core");
            await invoke("kill_sidecar");
          } catch {
            // Non-fatal: NSIS hook will kill sidecar if needed
          }
        }
        await update.downloadAndInstall();
        const { relaunch } = await import("@tauri-apps/plugin-process");
        await relaunch();
      }
    } catch {
      setIsInstalling(false);
    }
  }, []);

  const navItems = useMemo(() => getNavItems(userEmail), [userEmail]);

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        {IS_TAURI && updateInfo?.available ? (
          <>
            <button className="sidebar-title-btn" onClick={handleUpdateClick} disabled={isInstalling}>
              <h1 className="sidebar-title">
                Explify
                {!isInstalling && <span className="update-dot" />}
              </h1>
              <span className="sidebar-descriptor">
                {isInstalling ? "Updating..." : `v${updateInfo.version} available`}
              </span>
            </button>
            {showUpdatePrompt && (
              <div className="update-prompt">
                <span className="update-prompt-text">Update and restart now?</span>
                <div className="update-prompt-actions">
                  <button className="update-prompt-yes" onClick={handleInstallUpdate}>Yes</button>
                  <button className="update-prompt-no" onClick={() => setShowUpdatePrompt(false)}>No</button>
                </div>
              </div>
            )}
          </>
        ) : (
          <>
            <h1 className="sidebar-title">Explify</h1>
            <span className="sidebar-descriptor">{getDailyTagline()}</span>
          </>
        )}
      </div>
      <nav className="sidebar-nav">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === "/"}
            className={({ isActive }) =>
              `sidebar-link ${isActive ? "sidebar-link--active" : ""}`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
      {isSupabaseConfigured() && (
        <div className="sidebar-auth">
          {isSignedIn ? (
            <>
              <span className="auth-user-email">{userEmail}</span>
              <button className="auth-signout-btn" onClick={handleSignOut}>
                Sign Out
              </button>
            </>
          ) : (
            <button
              className="auth-signin-btn"
              onClick={() => navigate("/auth")}
            >
              Sign In
            </button>
          )}
        </div>
      )}
    </aside>
  );
}
