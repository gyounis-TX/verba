/**
 * Auth service — Cognito-backed (replaces Supabase auth).
 *
 * Exports the same API surface as the old Supabase module so existing
 * consumers (AuthScreen, Sidebar, AppShell, sidecarApi, etc.) keep working.
 */

import {
  CognitoUserPool,
  CognitoUser,
  AuthenticationDetails,
  CognitoUserSession,
  CognitoUserAttribute,
} from "amazon-cognito-identity-js";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const COGNITO_USER_POOL_ID = (import.meta.env.VITE_COGNITO_USER_POOL_ID ?? "").trim();
const COGNITO_CLIENT_ID = (import.meta.env.VITE_COGNITO_CLIENT_ID ?? "").trim();
const COGNITO_DOMAIN = (import.meta.env.VITE_COGNITO_DOMAIN ?? "").trim();

let userPool: CognitoUserPool | null = null;

function getUserPool(): CognitoUserPool | null {
  if (!COGNITO_USER_POOL_ID || !COGNITO_CLIENT_ID) return null;
  if (!userPool) {
    userPool = new CognitoUserPool({
      UserPoolId: COGNITO_USER_POOL_ID,
      ClientId: COGNITO_CLIENT_ID,
    });
  }
  return userPool;
}

// ---------------------------------------------------------------------------
// Session type (compatible with old Supabase Session shape)
// ---------------------------------------------------------------------------

export interface Session {
  access_token: string;
  user: { id: string; email: string };
}

function sessionFromCognito(cognitoSession: CognitoUserSession, email: string): Session {
  const idToken = cognitoSession.getIdToken();
  return {
    access_token: idToken.getJwtToken(),
    user: {
      id: idToken.payload.sub as string,
      email,
    },
  };
}

// ---------------------------------------------------------------------------
// Auth state change listeners
// ---------------------------------------------------------------------------

type AuthCallback = (session: Session | null) => void;
const _listeners = new Set<AuthCallback>();

function _notifyListeners(session: Session | null) {
  for (const cb of _listeners) {
    try { cb(session); } catch { /* ignore */ }
  }
}

export function onAuthStateChange(callback: AuthCallback): () => void {
  _listeners.add(callback);
  return () => { _listeners.delete(callback); };
}

// ---------------------------------------------------------------------------
// Public API — same signatures as old supabase.ts
// ---------------------------------------------------------------------------

export type SignUpResult =
  | { error: string }
  | { error: null; confirmed: true }
  | { error: null; confirmed: false };

export async function signUp(
  email: string,
  password: string,
): Promise<SignUpResult> {
  const pool = getUserPool();
  if (!pool) return { error: "Auth not configured." };

  const attributes = [
    new CognitoUserAttribute({ Name: "email", Value: email.trim() }),
  ];

  return new Promise((resolve) => {
    pool.signUp(email.trim(), password, attributes, [], (err, result) => {
      if (err) {
        const msg = err.message || "Sign-up failed.";
        // Cognito returns "UsernameExistsException" for duplicate email
        if (err.name === "UsernameExistsException") {
          resolve({ error: "An account with this email already exists." });
        } else {
          resolve({ error: msg });
        }
        return;
      }
      if (result?.userConfirmed) {
        // Auto-confirmed (admin setting)
        resolve({ error: null, confirmed: true });
      } else {
        // Verification code sent
        resolve({ error: null, confirmed: false });
      }
    });
  });
}

export async function signIn(
  email: string,
  password: string,
): Promise<{ error: string | null; newPasswordRequired?: boolean }> {
  const pool = getUserPool();
  if (!pool) return { error: "Auth not configured." };

  const user = new CognitoUser({ Username: email.trim(), Pool: pool });
  const authDetails = new AuthenticationDetails({
    Username: email.trim(),
    Password: password,
  });

  return new Promise((resolve) => {
    user.authenticateUser(authDetails, {
      onSuccess(session) {
        const s = sessionFromCognito(session, email.trim());
        _notifyListeners(s);
        resolve({ error: null });
      },
      onFailure(err) {
        resolve({ error: err.message || "Sign-in failed." });
      },
      newPasswordRequired() {
        // Store the CognitoUser so completeNewPassword can use it
        _pendingNewPasswordUser = user;
        resolve({ error: null, newPasswordRequired: true });
      },
    });
  });
}

let _pendingNewPasswordUser: CognitoUser | null = null;

export async function completeNewPassword(
  newPassword: string,
): Promise<{ error: string | null }> {
  const user = _pendingNewPasswordUser;
  if (!user) return { error: "No pending password challenge." };

  return new Promise((resolve) => {
    user.completeNewPasswordChallenge(newPassword, {}, {
      onSuccess(session) {
        _pendingNewPasswordUser = null;
        const email = user.getUsername();
        const s = sessionFromCognito(session, email);
        _notifyListeners(s);
        resolve({ error: null });
      },
      onFailure(err) {
        resolve({ error: err.message || "Failed to set new password." });
      },
    });
  });
}

export async function verifyOtp(
  email: string,
  token: string,
): Promise<{ error: string | null }> {
  const pool = getUserPool();
  if (!pool) return { error: "Auth not configured." };

  const user = new CognitoUser({ Username: email.trim(), Pool: pool });

  return new Promise((resolve) => {
    user.confirmRegistration(token, true, (err) => {
      if (err) {
        resolve({ error: err.message || "Verification failed." });
      } else {
        resolve({ error: null });
      }
    });
  });
}

export async function resendSignupOtp(
  email: string,
): Promise<{ error: string | null }> {
  const pool = getUserPool();
  if (!pool) return { error: "Auth not configured." };

  const user = new CognitoUser({ Username: email.trim(), Pool: pool });

  return new Promise((resolve) => {
    user.resendConfirmationCode((err) => {
      if (err) {
        resolve({ error: err.message || "Could not resend code." });
      } else {
        resolve({ error: null });
      }
    });
  });
}

export async function resetPassword(
  email: string,
): Promise<{ error: string | null }> {
  const pool = getUserPool();
  if (!pool) return { error: "Auth not configured." };

  const user = new CognitoUser({ Username: email.trim(), Pool: pool });

  return new Promise((resolve) => {
    user.forgotPassword({
      onSuccess() {
        resolve({ error: null });
      },
      onFailure(err) {
        resolve({ error: err.message || "Could not send reset code." });
      },
    });
  });
}

/**
 * Confirm a new password with the verification code from the reset email.
 * In the old Supabase flow, `updatePassword` worked differently (via a
 * recovery link that set a session). With Cognito, we need both the code
 * and the new password. The AuthScreen handles this two-step flow.
 */
export async function confirmNewPassword(
  email: string,
  code: string,
  newPassword: string,
): Promise<{ error: string | null }> {
  const pool = getUserPool();
  if (!pool) return { error: "Auth not configured." };

  const user = new CognitoUser({ Username: email.trim(), Pool: pool });

  return new Promise((resolve) => {
    user.confirmPassword(code, newPassword, {
      onSuccess() {
        resolve({ error: null });
      },
      onFailure(err) {
        resolve({ error: err.message || "Could not update password." });
      },
    });
  });
}

/** @deprecated — use confirmNewPassword for Cognito. Kept for backwards compat. */
export async function updatePassword(
  _newPassword: string,
): Promise<{ error: string | null }> {
  // In Cognito, changing password for a signed-in user requires the current session
  const pool = getUserPool();
  if (!pool) return { error: "Auth not configured." };
  const user = pool.getCurrentUser();
  if (!user) return { error: "No active session." };

  return new Promise((resolve) => {
    user.getSession((err: Error | null, session: CognitoUserSession | null) => {
      if (err || !session) {
        resolve({ error: "Session expired." });
        return;
      }
      // changePassword requires old password — this path is limited.
      // For password reset, use confirmNewPassword instead.
      resolve({ error: "Use the verification code flow to reset your password." });
    });
  });
}

export async function signInWithGoogle(): Promise<{ error: string | null }> {
  if (!COGNITO_DOMAIN || !COGNITO_CLIENT_ID) {
    return { error: "Google sign-in not configured." };
  }
  const redirectUri = encodeURIComponent(
    `${window.location.origin}${window.location.pathname}`,
  );
  const url =
    `${COGNITO_DOMAIN}/oauth2/authorize?` +
    `response_type=code&client_id=${COGNITO_CLIENT_ID}` +
    `&redirect_uri=${redirectUri}` +
    `&identity_provider=Google&scope=openid+email+profile`;
  window.location.href = url;
  return { error: null };
}

/** Returns true when Cognito env vars are configured. */
export function isAuthConfigured(): boolean {
  return !!(COGNITO_USER_POOL_ID && COGNITO_CLIENT_ID);
}



export async function signOut(): Promise<void> {
  const pool = getUserPool();
  if (!pool) return;
  const user = pool.getCurrentUser();
  if (user) {
    user.signOut();
    _notifyListeners(null);
  }
}

export async function getSession(): Promise<Session | null> {
  const pool = getUserPool();
  if (!pool) return null;
  const user = pool.getCurrentUser();
  if (!user) return null;

  return new Promise((resolve) => {
    user.getSession((err: Error | null, session: CognitoUserSession | null) => {
      if (err || !session || !session.isValid()) {
        resolve(null);
        return;
      }
      const email = session.getIdToken().payload.email as string ?? "";
      resolve(sessionFromCognito(session, email));
    });
  });
}

