"use client";

// "Open workspace" on the landing page: with a session, go straight to the dashboard; otherwise
// show the sign-in / sign-up card. The card is a Liquid Glass sheet (functional layer over the
// film, regular variant, opaque fallback for Reduce Transparency and Increase Contrast).
//
// Sign in is the real owner sign-in (POST /api/v1/auth/login, docs/API.md 2a, D-044).
// Google, GitHub and Apple are shown but not connected: the backend has no OAuth yet, so they say
// so instead of pretending. Sign up explains creating the single owner password.

import * as React from "react";
import { AppleLogo, GithubLogo, GoogleLogo } from "@phosphor-icons/react";
import { ArrowRight, Check, Copy, Eye, EyeOff, X } from "lucide-react";

const DASHBOARD = "/dashboard";

/** Only same-site paths are allowed as a return address (no open redirect). */
function safeNext(next?: string | null) {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/login") ? next : DASHBOARD;
}

const AccessContext = React.createContext<() => void>(() => undefined);

export function useOpenWorkspace() {
  return React.useContext(AccessContext);
}

/** A button styled with the prototype's classes that opens the workspace. */
export function OpenWorkspace({ className, children }: { className: string; children: React.ReactNode }) {
  const open = useOpenWorkspace();
  return (
    <button type="button" className={className} onClick={open}>
      {children}
    </button>
  );
}

export function WorkspaceAccessProvider({
  children,
  initialOpen = false,
  next,
}: {
  children: React.ReactNode;
  /** Open the card on load (the /login page). */
  initialOpen?: boolean;
  /** Where to go after signing in, e.g. the page that asked for a session. */
  next?: string;
}) {
  const [open, setOpen] = React.useState(initialOpen);
  const target = safeNext(next);
  const busy = React.useRef(false);

  const request = React.useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    try {
      const r = await fetch("/api/v1/auth/me", { credentials: "same-origin", cache: "no-store" });
      if (r.ok) {
        window.location.href = target;
        return;
      }
    } catch {
      /* backend unreachable: the card explains it on submit */
    } finally {
      busy.current = false;
    }
    setOpen(true);
  }, [target]);

  return (
    <AccessContext.Provider value={request}>
      {children}
      {open && <AccessCard target={target} onClose={() => setOpen(false)} />}
    </AccessContext.Provider>
  );
}

function CopyLine({ text }: { text: string }) {
  const [done, setDone] = React.useState(false);
  return (
    <div className="glass-code">
      <code className="mono">{text}</code>
      <button
        type="button"
        aria-label={done ? "Copied" : "Copy command"}
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(text);
            setDone(true);
            window.setTimeout(() => setDone(false), 1600);
          } catch {
            /* clipboard blocked: the text is selectable */
          }
        }}
      >
        {done ? <Check size={15} /> : <Copy size={15} />}
      </button>
    </div>
  );
}

const PROVIDERS = [
  { id: "google", label: "Google", Icon: GoogleLogo },
  { id: "github", label: "GitHub", Icon: GithubLogo },
  { id: "apple", label: "Apple", Icon: AppleLogo },
] as const;

function AccessCard({ target, onClose }: { target: string; onClose: () => void }) {
  const [mode, setMode] = React.useState<"signin" | "signup">("signin");
  const [password, setPassword] = React.useState("");
  const [show, setShow] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [provider, setProvider] = React.useState<string | null>(null);
  const dialogRef = React.useRef<HTMLDivElement>(null);
  const close = React.useRef(onClose);
  close.current = onClose;

  // Focus trap, Escape to close, focus returned to the opener.
  React.useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusable = () => Array.from(dialog.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], input:not([disabled])'));
    (dialog.querySelector<HTMLElement>("input") ?? focusable()[0])?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        close.current();
        return;
      }
      if (e.key !== "Tab") return;
      const items = focusable();
      const first = items[0];
      const last = items[items.length - 1];
      if (!first || !last) return;
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, []);

  const switchMode = (m: "signin" | "signup") => {
    setMode(m);
    setError(null);
    setProvider(null);
  };

  const signIn = async (e: React.FormEvent) => {
    e.preventDefault();
    setProvider(null);
    if (!password) {
      setError("Enter the owner password.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const r = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ password }),
      });
      if (r.ok) {
        window.location.href = target;
        return;
      }
      if (r.status === 401) setError("That password doesn't match the owner password. Try again.");
      else if (r.status === 429) setError("Too many attempts. Wait a minute, then try again.");
      else if (r.status === 403) switchMode("signup");
      else setError(`Sign-in failed (HTTP ${r.status}). Check that the backend is running.`);
    } catch {
      setError("Can't reach the backend. Start it from backend/ with: py -m uvicorn app.main:app --port 8000");
    }
    setBusy(false);
  };

  const signin = mode === "signin";

  return (
    <div
      className="glass-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div ref={dialogRef} className="glass-card" role="dialog" aria-modal="true" aria-labelledby="glass-title">
        <button type="button" className="glass-close" onClick={onClose} aria-label="Close">
          <X size={18} />
        </button>

        <svg className="glass-mark" viewBox="0 0 36 36" fill="none" aria-hidden="true">
          <path
            d="M10.25 11.5c1.7-3.1 4.15-4.65 7.45-4.65 4.42 0 7.05 3.08 7.05 6.8 0 4.05-2.18 6.17-6.95 6.17h-2.3c-3.06 0-5.42 1.77-5.42 4.8 0 2.7 2.02 4.53 4.92 4.53 4.22 0 7.2-2.86 8.91-8.6"
            stroke="currentColor"
            strokeWidth="1.55"
            strokeLinecap="round"
          />
          <path d="M8.25 16.15h6.15M21.25 11.65h6.5" stroke="currentColor" strokeWidth="1.45" strokeLinecap="round" />
          <circle cx="8.1" cy="16.15" r="2.05" fill="#8DB99E" />
          <circle cx="28.12" cy="11.65" r="2.05" fill="#D7B579" />
          <circle cx="15.02" cy="28.8" r="2.05" fill="#8DB99E" />
          <circle cx="18.1" cy="18.15" r="1.6" fill="currentColor" />
        </svg>
        <h2 id="glass-title">{signin ? "Welcome back" : "Create your workspace"}</h2>
        <p className="glass-sub">{signin ? "Sign in to approve plans and follow your runs." : "Set up the owner account for this EvoLab workspace."}</p>

        <div className="glass-segment" role="tablist" aria-label="Sign in or sign up">
          <span className="glass-segment-thumb" data-mode={mode} aria-hidden="true" />
          <button type="button" role="tab" aria-selected={signin} onClick={() => switchMode("signin")}>
            Sign in
          </button>
          <button type="button" role="tab" aria-selected={!signin} onClick={() => switchMode("signup")}>
            Sign up
          </button>
        </div>

        <div className="glass-providers">
          {PROVIDERS.map(({ id, label, Icon }) => (
            <button key={id} type="button" className="glass-provider" onClick={() => setProvider(label)} aria-describedby={provider === label ? "glass-provider-note" : undefined}>
              <Icon size={18} weight="bold" aria-hidden="true" />
              <span>
                Continue with {label}
              </span>
            </button>
          ))}
        </div>
        {provider && (
          <p id="glass-provider-note" className="glass-note" role="status">
            {provider} sign-in isn&apos;t connected to this workspace yet. Use the owner password{signin ? " below" : ""} for now.
          </p>
        )}

        <div className="glass-divider">
          <span>{signin ? "or use the owner password" : "or set the owner password"}</span>
        </div>

        {signin ? (
          <form onSubmit={signIn} noValidate>
            <label className="glass-field">
              <span className="sr-only">Owner password</span>
              <input
                type={show ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Owner password"
                aria-invalid={!!error}
                aria-describedby={error ? "glass-error" : undefined}
              />
              <button type="button" className="glass-eye" onClick={() => setShow((v) => !v)} aria-label={show ? "Hide password" : "Show password"}>
                {show ? <EyeOff size={17} /> : <Eye size={17} />}
              </button>
            </label>
            {error && (
              <p id="glass-error" className="glass-error" role="alert">
                {error}
              </p>
            )}
            <button type="submit" className="glass-primary" disabled={busy}>
              {busy ? "Signing in" : "Sign in"} <ArrowRight size={16} />
            </button>
            <p className="glass-foot">
              New here?{" "}
              <button type="button" onClick={() => switchMode("signup")}>
                Create the owner account
              </button>
            </p>
          </form>
        ) : (
          <div>
            <ol className="glass-steps">
              <li>
                <b>Choose a password</b> on the machine that runs the backend. The script asks for it and prints a hash, never the password.
                <CopyLine text="cd backend; py scripts/hash_password.py" />
              </li>
              <li>
                <b>Save the hash.</b> Paste the printed <span className="mono">OWNER_PASSWORD_HASH=…</span> line into <span className="mono">.env</span> at the repo root.
              </li>
              <li>
                <b>Restart the backend</b> so it reads the new hash.
                <CopyLine text="py -m uvicorn app.main:app --port 8000" />
              </li>
            </ol>
            <button type="button" className="glass-primary" onClick={() => switchMode("signin")}>
              I&apos;ve set it, sign in <ArrowRight size={16} />
            </button>
            <p className="glass-foot">Forgot the password? Repeat these steps to set a new one.</p>
          </div>
        )}
      </div>
    </div>
  );
}
