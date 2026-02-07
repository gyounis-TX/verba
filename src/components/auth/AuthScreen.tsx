import { useState, useCallback, useRef } from "react";
import { signIn, signUp, verifyOtp, resendSignupOtp, type SignUpResult } from "../../services/supabase";
import { useToast } from "../shared/Toast";
import "./AuthScreen.css";

interface AuthScreenProps {
  onAuthSuccess: () => void;
}

export function AuthScreen({ onAuthSuccess }: AuthScreenProps) {
  const { showToast } = useToast();
  const [mode, setMode] = useState<"signin" | "signup" | "verify">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState(["", "", "", "", "", "", "", ""]);
  const [loading, setLoading] = useState(false);
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  const handleCodeChange = useCallback(
    (index: number, value: string) => {
      if (!/^\d*$/.test(value)) return;
      const next = [...code];
      next[index] = value.slice(-1);
      setCode(next);
      if (value && index < 7) {
        inputRefs.current[index + 1]?.focus();
      }
    },
    [code],
  );

  const handleCodeKeyDown = useCallback(
    (index: number, e: React.KeyboardEvent) => {
      if (e.key === "Backspace" && !code[index] && index > 0) {
        inputRefs.current[index - 1]?.focus();
      }
    },
    [code],
  );

  const handleCodePaste = useCallback((e: React.ClipboardEvent) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 8);
    if (!pasted) return;
    const next = ["", "", "", "", "", "", "", ""];
    for (let i = 0; i < pasted.length; i++) {
      next[i] = pasted[i];
    }
    setCode(next);
    const focusIdx = Math.min(pasted.length, 7);
    inputRefs.current[focusIdx]?.focus();
  }, []);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!email.trim() || !password.trim()) return;

      setLoading(true);
      try {
        if (mode === "signin") {
          const result = await signIn(email, password);
          if (result.error) {
            showToast("error", result.error);
          } else {
            showToast("success", "Signed in successfully.");
            onAuthSuccess();
          }
        } else {
          const result: SignUpResult = await signUp(email, password);
          if (result.error) {
            showToast("error", result.error);
          } else if (result.confirmed) {
            // Auto-confirmed (no email verification required)
            showToast("success", "Account created.");
            onAuthSuccess();
          } else {
            setCode(["", "", "", "", "", "", "", ""]);
            setMode("verify");
            showToast("success", "Code sent to your email.");
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

  const handleVerify = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const token = code.join("");
      if (token.length !== 8) return;

      setLoading(true);
      try {
        const result = await verifyOtp(email, token);
        if (result.error) {
          showToast("error", result.error);
        } else {
          showToast("success", "Email verified. Signed in.");
          onAuthSuccess();
        }
      } catch {
        showToast("error", "Verification failed.");
      } finally {
        setLoading(false);
      }
    },
    [code, email, showToast, onAuthSuccess],
  );

  const handleResend = useCallback(async () => {
    setLoading(true);
    try {
      const result = await resendSignupOtp(email);
      if (result.error) {
        showToast("error", result.error);
      } else {
        showToast("success", "New code sent.");
      }
    } catch {
      showToast("error", "Could not resend code.");
    } finally {
      setLoading(false);
    }
  }, [email, showToast]);

  if (mode === "verify") {
    return (
      <div className="auth-screen">
        <div className="auth-card">
          <h2 className="auth-title">Verify Your Email</h2>
          <p className="auth-subtitle">
            Enter the 8-digit code sent to <strong>{email}</strong>
          </p>

          <form className="auth-form" onSubmit={handleVerify}>
            <div className="auth-code-inputs" onPaste={handleCodePaste}>
              {code.map((digit, i) => (
                <input
                  key={i}
                  ref={(el) => { inputRefs.current[i] = el; }}
                  type="text"
                  inputMode="numeric"
                  maxLength={1}
                  className="auth-code-box"
                  value={digit}
                  onChange={(e) => handleCodeChange(i, e.target.value)}
                  onKeyDown={(e) => handleCodeKeyDown(i, e)}
                  autoFocus={i === 0}
                />
              ))}
            </div>

            <button
              type="submit"
              className="auth-submit-btn"
              disabled={loading || code.join("").length !== 8}
            >
              {loading ? "Verifying..." : "Verify"}
            </button>
          </form>

          <p className="auth-switch">
            Didn't get a code?{" "}
            <button
              className="auth-switch-btn"
              onClick={handleResend}
              disabled={loading}
            >
              Resend
            </button>
          </p>

          <p className="auth-switch">
            <button
              className="auth-switch-btn"
              onClick={() => setMode("signup")}
            >
              Back
            </button>
          </p>
        </div>
      </div>
    );
  }

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
