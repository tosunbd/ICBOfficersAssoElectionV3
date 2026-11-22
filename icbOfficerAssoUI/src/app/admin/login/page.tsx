"use client";

import { useEffect, useState, type FormEvent, type KeyboardEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Suspense } from "react";
import { useAuth } from "@/hooks/useAuth";
import { errorMessage } from "@/lib/format";
import { Logo } from "@/components/ui/Logo";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { Icon } from "@/components/ui/Icon";
import { Alert } from "@/components/ui/Basics";

export default function LoginPage() {
  return <Suspense><LoginScreen /></Suspense>;
}

function LoginScreen() {
  const signedOut = useSearchParams().get("signedout") === "1";
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(false);
  const { login, isAuthenticated, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && isAuthenticated) router.replace("/admin");
  }, [isLoading, isAuthenticated, router]);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(username.trim(), password);
      router.replace("/admin");
    } catch (err) {
      setError(errorMessage(err, "Invalid username or password"));
      setAttempt((n) => n + 1);
    } finally {
      setLoading(false);
    }
  };

  const trackCaps = (event: KeyboardEvent<HTMLInputElement>) => setCapsLock(event.getModifierState?.("CapsLock") ?? false);

  return (
    <div className="login-shell">
      <section className="login-showcase" aria-hidden="true">
        <div className="login-showcase-top">
          <Icon name="shield" size={16} /> ICB Officers&apos; Association
        </div>
        <div className="login-showcase-center">
          <div className="medallion-stage">
            <span className="orbit" /><span className="orbit orbit-2" /><span className="orbit orbit-3" />
            <Logo size={190} halo />
          </div>
          <div>
            <h1>Every ballot, <em>counted</em> in the light.</h1>
            <p className="login-showcase-bn" style={{ marginTop: 14 }}>আইসিবি কর্মকর্তা সমিতি · কার্যনির্বাহী পরিষদ নির্বাচন</p>
          </div>
          <div className="login-features">
            <span className="login-feature"><Icon name="zap" size={16} /> Automatic ballot reading</span>
            <span className="login-feature"><Icon name="broadcast" size={16} /> Live public results</span>
            <span className="login-feature"><Icon name="scroll" size={16} /> Full audit trail</span>
          </div>
        </div>
        <div className="login-showcase-foot">Investment Corporation of Bangladesh · Election Management System</div>
      </section>

      <section className="login-panel">
        <ThemeToggle className="login-theme-toggle" />
        <div className="login-card">
          <div className="login-mobile-brand"><Logo size={96} halo /></div>
          <div className="page-eyebrow">Secure access</div>
          <h2>Welcome back</h2>
          <p className="lead">Sign in to the election control room.</p>

          <form className={`login-form ${attempt ? "shake" : ""}`} key={attempt} onSubmit={handleSubmit}>
            {error ? <Alert type="error">{error}</Alert> : signedOut && <Alert type="success">You have been signed out safely.</Alert>}
            <div className="input-group">
              <label className="input-label" htmlFor="username">Username</label>
              <div className="input-wrap">
                <Icon name="user" size={17} />
                <input id="username" className="input input-lg" autoComplete="username" value={username}
                  onChange={(e) => setUsername(e.target.value)} required autoFocus placeholder="admin" />
              </div>
            </div>
            <div className="input-group">
              <label className="input-label" htmlFor="password">Password</label>
              <div className="input-wrap">
                <Icon name="lock" size={17} />
                <input id="password" type={showPassword ? "text" : "password"} className="input input-lg" autoComplete="current-password"
                  value={password} onChange={(e) => setPassword(e.target.value)} onKeyUp={trackCaps} onKeyDown={trackCaps} required
                  placeholder="••••••••" style={{ paddingRight: 80 }} />
                <button type="button" className="input-affix" onClick={() => setShowPassword((v) => !v)} aria-label={showPassword ? "Hide password" : "Show password"}>
                  <Icon name={showPassword ? "eyeOff" : "eye"} size={15} />{showPassword ? "Hide" : "Show"}
                </button>
              </div>
              {capsLock && <span className="caps-warning"><Icon name="alert" size={13} /> Caps Lock is on</span>}
            </div>
            <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={loading} style={{ marginTop: 6 }}>
              {loading ? <><span className="btn-spinner" /> Signing in…</> : <>Sign in <Icon name="arrowRight" size={17} /></>}
            </button>
          </form>

          <div className="login-secure"><Icon name="shield" size={14} /> Every action is recorded in the audit log</div>
          <Link href="/dashboard" className="login-back"><Icon name="broadcast" size={14} /> View the public live screen</Link>
        </div>
      </section>
    </div>
  );
}
