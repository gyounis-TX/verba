import { useState, useCallback } from "react";
import { signIn, signUp } from "../../services/supabase";
import { useToast } from "../shared/Toast";
import "./AuthScreen.css";

interface AuthScreenProps {
  onAuthSuccess: () => void;
}

export function AuthScreen({ onAuthSuccess }: AuthScreenProps) {
  const { showToast } = useToast();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!email.trim() || !password.trim()) return;

      setLoading(true);
      try {
        const result =
          mode === "signin"
            ? await signIn(email, password)
            : await signUp(email, password);

        if (result.error) {
          showToast("error", result.error);
        } else {
          if (mode === "signup") {
            showToast(
              "success",
              "Account created. Check your email for confirmation.",
            );
          } else {
            showToast("success", "Signed in successfully.");
            onAuthSuccess();
          }
        }
      } catch {
        showToast("error", "Authentication failed.");
      } finally {
        setLoading(false);
      }
    },
    [email, password, mode, showToast, onAuthSuccess],
  );

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <h2 className="auth-title">
          {mode === "signin" ? "Sign In" : "Create Account"}
        </h2>
        <p className="auth-subtitle">
          {mode === "signin"
            ? "Sign in to sync your data across devices."
            : "Create an account to enable cloud sync."}
        </p>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label className="auth-label">
            Email
            <input
              type="email"
              className="auth-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
            />
          </label>

          <label className="auth-label">
            Password
            <input
              type="password"
              className="auth-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              required
              minLength={6}
            />
          </label>

          <button
            type="submit"
            className="auth-submit-btn"
            disabled={loading}
          >
            {loading
              ? "Please wait..."
              : mode === "signin"
                ? "Sign In"
                : "Create Account"}
          </button>
        </form>

        <p className="auth-switch">
          {mode === "signin" ? (
            <>
              No account?{" "}
              <button
                className="auth-switch-btn"
                onClick={() => setMode("signup")}
              >
                Create one
              </button>
            </>
          ) : (
            <>
              Already have an account?{" "}
              <button
                className="auth-switch-btn"
                onClick={() => setMode("signin")}
              >
                Sign in
              </button>
            </>
          )}
        </p>

        <p className="auth-note">
          API keys are never synced and remain local to this device.
        </p>
      </div>
    </div>
  );
}
