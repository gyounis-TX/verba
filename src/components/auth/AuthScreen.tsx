import { useState, useCallback, useRef } from "react";
import { Link } from "react-router-dom";
import {
  signIn,
  signUp,
  verifyOtp,
  resendSignupOtp,
  resetPassword,
  confirmNewPassword,
  completeNewPassword,
  signInWithGoogle,
  isAuthConfigured,
  type SignUpResult,
} from "../../services/supabase";
import { useToast } from "../shared/Toast";
import "./AuthScreen.css";

interface AuthScreenProps {
  onAuthSuccess: () => void;
}

type AuthMode = "signin" | "signup" | "verify" | "forgot" | "reset-code" | "new-password";

export function AuthScreen({ onAuthSuccess }: AuthScreenProps) {
  const { showToast } = useToast();
  const [mode, setMode] = useState<AuthMode>("signin");
  const [resetCode, setResetCode] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [code, setCode] = useState(["", "", "", "", "", ""]);
  const [loading, setLoading] = useState(false);
  const [resetSent, setResetSent] = useState(false);
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  // No access_token redirect needed with Cognito (code-based reset)

  const handleCodeChange = useCallback(
    (index: number, value: string) => {
      if (!/^\d*$/.test(value)) return;
      const next = [...code];
      next[index] = value.slice(-1);
      setCode(next);
      if (value && index < 5) {
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
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (!pasted) return;
    const next = ["", "", "", "", "", ""];
    for (let i = 0; i < pasted.length; i++) {
      next[i] = pasted[i];
    }
    setCode(next);
    const focusIdx = Math.min(pasted.length, 5);
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
          } else if (result.userNotConfirmed) {
            // Account exists but not verified — resend code and show verify screen
            try {
              await resendSignupOtp(email);
              showToast("info", "A new verification code has been sent to your email.");
            } catch {
              showToast("info", "Please check your email for a verification code.");
            }
            setCode(["", "", "", "", "", ""]);
            setMode("verify");
          } else if (result.newPasswordRequired) {
            setPassword("");
            setConfirmPassword("");
            setMode("new-password");
            showToast("success", "Please set a new password.");
          } else {
            showToast("success", "Signed in successfully.");
            onAuthSuccess();
          }
        } else {
          const result: SignUpResult = await signUp(email, password);
          if (result.error) {
            showToast("error", result.error);
          } else if ("confirmed" in result && result.confirmed) {
            showToast("success", "Account created.");
            onAuthSuccess();
          } else {
            setCode(["", "", "", "", "", ""]);
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
      if (token.length !== 6) return;

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

  const handleForgotPassword = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!email.trim()) return;

      setLoading(true);
      try {
        const result = await resetPassword(email);
        if (result.error) {
          showToast("error", result.error);
        } else {
          setResetSent(true);
          showToast("success", "Check your email for a verification code.");
        }
      } catch {
        showToast("error", "Could not send reset email.");
      } finally {
        setLoading(false);
      }
    },
    [email, showToast],
  );

  const handleResetPassword = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!resetCode.trim()) {
        showToast("error", "Please enter the verification code.");
        return;
      }
      if (!password.trim() || password.length < 8) {
        showToast("error", "Password must be at least 8 characters.");
        return;
      }
      if (password !== confirmPassword) {
        showToast("error", "Passwords do not match.");
        return;
      }

      setLoading(true);
      try {
        const result = await confirmNewPassword(email, resetCode, password);
        if (result.error) {
          showToast("error", result.error);
        } else {
          showToast("success", "Password updated. You can now sign in.");
          setPassword("");
          setConfirmPassword("");
          setResetCode("");
          setMode("signin");
        }
      } catch {
        showToast("error", "Could not update password.");
      } finally {
        setLoading(false);
      }
    },
    [email, resetCode, password, confirmPassword, showToast],
  );

  const handleGoogleSignIn = useCallback(async () => {
    setLoading(true);
    try {
      const result = await signInWithGoogle();
      if (result.error) {
        showToast("error", result.error);
        setLoading(false);
      }
      // On success, Supabase redirects to Google — no further action needed
    } catch {
      showToast("error", "Google sign-in failed.");
      setLoading(false);
    }
  }, [showToast]);

  // New password required (admin-created user with temp password)
  if (mode === "new-password") {
    const handleNewPassword = async (e: React.FormEvent) => {
      e.preventDefault();
      if (!password.trim() || password.length < 8) {
        showToast("error", "Password must be at least 8 characters.");
        return;
      }
      if (password !== confirmPassword) {
        showToast("error", "Passwords do not match.");
        return;
      }
      setLoading(true);
      try {
        const result = await completeNewPassword(password);
        if (result.error) {
          showToast("error", result.error);
        } else {
          showToast("success", "Password set. Signed in.");
          onAuthSuccess();
        }
      } catch {
        showToast("error", "Could not set password.");
      } finally {
        setLoading(false);
      }
    };

    return (
      <div className="auth-screen">
        <div className="auth-card">
          <h2 className="auth-title">Set New Password</h2>
          <p className="auth-subtitle">Your account requires a new password.</p>

          <form className="auth-form" onSubmit={handleNewPassword}>
            <label className="auth-label">
              New Password
              <input
                type="password"
                className="auth-input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="New password"
                required
                minLength={8}
                autoFocus
              />
            </label>

            <label className="auth-label">
              Confirm Password
              <input
                type="password"
                className="auth-input"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Confirm new password"
                required
                minLength={8}
              />
            </label>

            <button
              type="submit"
              className="auth-submit-btn"
              disabled={loading || !password || !confirmPassword}
            >
              {loading ? "Setting password..." : "Set Password"}
            </button>
          </form>
        </div>
      </div>
    );
  }

  // Reset password screen (Cognito: code + new password)
  if (mode === "reset-code") {
    return (
      <div className="auth-screen">
        <div className="auth-card">
          <h2 className="auth-title">Set New Password</h2>
          <p className="auth-subtitle">Enter the code from your email and your new password.</p>

          <form className="auth-form" onSubmit={handleResetPassword}>
            <label className="auth-label">
              Verification Code
              <input
                type="text"
                className="auth-input"
                value={resetCode}
                onChange={(e) => setResetCode(e.target.value.replace(/\D/g, ""))}
                placeholder="6-digit code"
                required
                autoFocus
              />
            </label>

            <label className="auth-label">
              New Password
              <input
                type="password"
                className="auth-input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="New password"
                required
                minLength={8}
              />
            </label>

            <label className="auth-label">
              Confirm Password
              <input
                type="password"
                className="auth-input"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Confirm new password"
                required
                minLength={8}
              />
            </label>

            <button
              type="submit"
              className="auth-submit-btn"
              disabled={loading || !resetCode || !password || !confirmPassword}
            >
              {loading ? "Updating..." : "Update Password"}
            </button>
          </form>

          <p className="auth-switch">
            <button
              className="auth-switch-btn"
              onClick={() => setMode("signin")}
            >
              Back to sign in
            </button>
          </p>
        </div>
      </div>
    );
  }

  // Forgot password screen
  if (mode === "forgot") {
    return (
      <div className="auth-screen">
        <div className="auth-card">
          <h2 className="auth-title">Reset Password</h2>
          <p className="auth-subtitle">
            Enter your email and we'll send you a verification code.
          </p>

          <form className="auth-form" onSubmit={handleForgotPassword}>
            <label className="auth-label">
              Email
              <input
                type="email"
                className="auth-input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
                autoFocus
              />
            </label>

            <button
              type="submit"
              className="auth-submit-btn"
              disabled={loading || !email.trim()}
            >
              {loading ? "Sending..." : "Send Reset Code"}
            </button>
          </form>

          {resetSent && (
            <p className="auth-switch">
              <button
                className="auth-switch-btn"
                onClick={() => setMode("reset-code")}
              >
                I have the code
              </button>
            </p>
          )}

          <p className="auth-switch">
            <button
              className="auth-switch-btn"
              onClick={() => {
                setResetSent(false);
                setMode("signin");
              }}
            >
              Back to sign in
            </button>
          </p>
        </div>
      </div>
    );
  }

  // OTP verification screen
  if (mode === "verify") {
    return (
      <div className="auth-screen">
        <div className="auth-card">
          <h2 className="auth-title">Verify Your Email</h2>
          <p className="auth-subtitle">
            Enter the 6-digit code sent to <strong>{email}</strong>
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
              disabled={loading || code.join("").length !== 6}
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

  // Sign in / Sign up screen
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

        {isAuthConfigured() && (
          <>
            <button
              type="button"
              className="auth-google-btn"
              onClick={handleGoogleSignIn}
              disabled={loading}
            >
              <svg className="auth-google-icon" viewBox="0 0 24 24" width="18" height="18">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18A10.96 10.96 0 0 0 1 12c0 1.77.42 3.45 1.18 4.93l3.66-2.84z" />
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
              </svg>
              Continue with Google
            </button>
            <div className="auth-divider">
              <span className="auth-divider-text">or</span>
            </div>
          </>
        )}

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

          {mode === "signin" && (
            <div className="auth-forgot">
              <button
                type="button"
                className="auth-switch-btn"
                onClick={() => setMode("forgot")}
              >
                Forgot password?
              </button>
            </div>
          )}

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

        {mode === "signup" && (
          <p className="auth-legal">
            By creating an account, you agree to our{" "}
            <Link to="/terms" className="auth-legal-link">Terms of Service</Link>
            {" "}and{" "}
            <Link to="/privacy" className="auth-legal-link">Privacy Policy</Link>.
          </p>
        )}

        <p className="auth-note">
          API keys are never synced and remain local to this device.
        </p>
      </div>
    </div>
  );
}
