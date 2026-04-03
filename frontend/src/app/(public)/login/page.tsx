"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState, useEffect, Suspense, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { login, signup, requestOTP, verifyOTP, resetPassword } from "@/services/authService";
import { useAuthStore } from "@/state/authStore";
import { useNotificationStore } from "@/state/notificationStore";
import TermsModal from "@/components/TermsModal";


/* ── SVG Icons ── */
const GoogleIcon = () => (
  <svg viewBox="0 0 24 24" width="18" height="18">
    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4" />
    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
  </svg>
);

const AppleIcon = () => (
  <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
    <path d="M17.05 20.28c-.98.95-2.05.88-3.08.4-1.09-.5-2.08-.48-3.24 0-1.44.62-2.2.44-3.06-.4C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8 1.18-.24 2.31-.93 3.57-.84 1.51.12 2.65.72 3.4 1.8-3.12 1.87-2.38 5.98.48 7.13-.57 1.5-1.31 2.99-2.54 4.09l.01-.01zM12.03 7.25c-.15-2.23 1.66-4.07 3.74-4.25.29 2.58-2.34 4.5-3.74 4.25z" />
  </svg>
);

const EyeIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
);

const EyeOffIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
    <line x1="1" y1="1" x2="23" y2="23" />
  </svg>
);

const SLIDES = ["/1.png", "/2.png", "/3.png", "/4.png"];

type AuthMode = "login" | "signup" | "otp" | "forgot_email" | "forgot_otp" | "reset_password";

function AuthPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { addToast } = useNotificationStore();
  const loginSuccess = useAuthStore((state) => state.loginSuccess);

  const [mode, setMode] = useState<AuthMode>("login");
  const [activeSlide, setActiveSlide] = useState(0);

  // Form States
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [agreedTerms, setAgreedTerms] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [isTermsOpen, setIsTermsOpen] = useState(false);

  // OTP State
  const [otp, setOtp] = useState(["", "", "", "", "", ""]);
  const [otpPurpose, setOtpPurpose] = useState<"signup" | "login" | "password_reset">("signup");

  // Sync mode from URL on mount
  useEffect(() => {
    const m = searchParams.get("mode") as AuthMode;
    if (m) setMode(m);
  }, [searchParams]);

  // Slideshow Logic
  useEffect(() => {
    const interval = setInterval(() => {
      setActiveSlide((prev) => (prev + 1) % SLIDES.length);
    }, 6000);
    return () => clearInterval(interval);
  }, []);

  /* ── Password Validation Logic ── */
  const passwordValidation = useMemo(() => {
    return {
      length: password.length >= 8,
      uppercase: /[A-Z]/.test(password),
      symbol: /[!@#$%^&*(),.?":{}|<>]/.test(password),
      match: mode === "signup" || mode === "reset_password" ? (password === confirmPassword && confirmPassword.length > 0) : true
    };
  }, [password, confirmPassword, mode]);

  const passwordStrength = useMemo(() => {
    if (password.length === 0) return { score: 0, label: "", color: "#f0f0f0" };
    let score = 0;
    if (passwordValidation.length) score += 25;
    if (passwordValidation.uppercase) score += 25;
    if (passwordValidation.symbol) score += 25;
    if (password.length >= 12) score += 25;
    
    if (score <= 25) return { score, label: "Weak", color: "#ef4444" };
    if (score <= 50) return { score, label: "Fair", color: "#f97316" };
    if (score <= 75) return { score, label: "Good", color: "#eab308" };
    return { score, label: "Strong", color: "#22c55e" };
  }, [password, passwordValidation]);

  /* ── API Actions ── */

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const data = await login({ email, password });
      loginSuccess(data.user, { expiresAt: data.accessTokenExpiresAt });
      addToast({ title: "Welcome back!", type: "success" });
      router.push("/");
    } catch (err: any) {
      addToast({ title: "Login Failed", message: err.response?.data?.detail || "Invalid credentials", type: "error" });
    } finally {
      setSubmitting(false);
    }
  };

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!agreedTerms) return addToast({ title: "Terms required", message: "Please agree to the terms and conditions.", type: "warning" });
    if (!passwordValidation.length || !passwordValidation.uppercase || !passwordValidation.symbol) {
      return addToast({ title: "Weak password", message: "Please follow the password rules.", type: "warning" });
    }
    if (password !== confirmPassword) return addToast({ title: "Mismatch", message: "Passwords do not match.", type: "error" });

    setSubmitting(true);
    try {
      await signup({ email, password, first_name: firstName, last_name: lastName });
      setOtpPurpose("signup");
      setMode("otp");
      addToast({ title: "Verification required", message: "We've sent an OTP to your email.", type: "info" });
    } catch (err: any) {
      addToast({ title: "Signup Failed", message: err.response?.data?.detail || "Check your details", type: "error" });
    } finally {
      setSubmitting(false);
    }
  };

  const handleVerifyOTP = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    const otpValue = otp.join("");
    try {
      const data = await verifyOTP({ email, otp: otpValue, purpose: otpPurpose });
      if (otpPurpose === "password_reset") {
        setMode("reset_password");
      } else {
        if (data.user) {
           loginSuccess(data.user, { expiresAt: data.accessTokenExpiresAt });
           addToast({ title: "Account Verified", message: "Welcome to AI Architect.", type: "success" });
           router.push("/");
        } else {
           addToast({ title: "Verified", message: "Please sign in.", type: "success" });
           setMode("login");
        }
      }
    } catch (err: any) {
      addToast({ title: "Verification Failed", message: err.response?.data?.detail || "Invalid OTP", type: "error" });
    } finally {
      setSubmitting(false);
    }
  };

  const handleRequestPasswordReset = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
       await requestOTP({ email, purpose: "password_reset" });
       setOtpPurpose("password_reset");
       setMode("forgot_otp");
       addToast({ title: "OTP Sent", message: "Check your email for reset instructions.", type: "info" });
    } catch (err: any) {
       addToast({ title: "Request Failed", message: err.response?.data?.detail || "Email not found", type: "error" });
    } finally {
       setSubmitting(false);
    }
  };

  const handleFinalReset = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirmPassword) return addToast({ title: "Mismatch", message: "Passwords do not match.", type: "error" });
    setSubmitting(true);
    const otpValue = otp.join("");
    try {
       await resetPassword({ email, otp: otpValue, new_password: password });
       addToast({ title: "Password Reset Success", message: "You can now login with your new password.", type: "success" });
       setMode("login");
    } catch (err: any) {
       addToast({ title: "Reset Failed", message: err.response?.data?.detail || "Try again", type: "error" });
    } finally {
       setSubmitting(false);
    }
  };

  const renderPasswordStrength = () => {
    if (password.length === 0) return null;
    return (
      <div className="password-strength-container">
        <div className="strength-bar-bg">
          <div className="strength-bar-fill" style={{ width: `${passwordStrength.score}%`, background: passwordStrength.color }} />
        </div>
        <div className="password-rules-line">
          <span className={`rule-item ${passwordValidation.length ? 'valid' : 'invalid'}`}>Min 8 Chars</span> • 
          <span className={`rule-item ${passwordValidation.uppercase ? 'valid' : 'invalid'}`}> 1 Uppercase</span> • 
          <span className={`rule-item ${passwordValidation.symbol ? 'valid' : 'invalid'}`}> 1 Symbol</span>
          {confirmPassword.length > 0 && (
            <> • <span className={`rule-item ${passwordValidation.match ? 'valid' : 'invalid'}`}> Match</span></>
          )}
        </div>
      </div>
    );
  };

  const renderForm = () => {
    switch (mode) {
      case "login":
        return (
          <motion.div
            key="login"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
          >
            <h1 className="auth-form-title">Welcome back</h1>
            <p className="auth-form-subtitle">
              Don&apos;t have an account? <button onClick={() => setMode("signup")}>Sign up</button>
            </p>
            <form className="auth-form" onSubmit={handleLogin}>
              <div className="auth-form-group">
                <input className="auth-form-input" placeholder="Email" type="email" value={email} onChange={e => setEmail(e.target.value)} required />
              </div>
              <div className="auth-form-group">
                <input className="auth-form-input" placeholder="Password" type={showPassword ? "text" : "password"} value={password} onChange={e => setPassword(e.target.value)} required />
                <button type="button" className="auth-password-toggle" onClick={() => setShowPassword(!showPassword)}>
                  {showPassword ? <EyeOffIcon /> : <EyeIcon />}
                </button>
              </div>
              <div style={{ textAlign: 'right', marginBottom: '15px' }}>
                <button type="button" className="auth-link" onClick={() => setMode("forgot_email")} style={{ background: 'none', border: 'none', color: '#f97316', fontSize: '12px', cursor: 'pointer' }}>
                  Forgot password?
                </button>
              </div>
              <button type="submit" className="auth-btn-primary" disabled={submitting}>{submitting ? "Signing in..." : "Sign in"}</button>
            </form>
          </motion.div>
        );

      case "signup":
        return (
          <motion.div
            key="signup"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
          >
            <h1 className="auth-form-title">Create account</h1>
            <p className="auth-form-subtitle">
              Already have an account? <button onClick={() => setMode("login")}>Sign in</button>
            </p>
            <form className="auth-form" onSubmit={handleSignup}>
              <div className="auth-form-row">
                <div className="auth-form-group"><input className="auth-form-input" placeholder="First Name" value={firstName} onChange={e => setFirstName(e.target.value)} required /></div>
                <div className="auth-form-group"><input className="auth-form-input" placeholder="Last Name" value={lastName} onChange={e => setLastName(e.target.value)} required /></div>
              </div>
              <div className="auth-form-group">
                <input className="auth-form-input" placeholder="Email" type="email" value={email} onChange={e => setEmail(e.target.value)} required />
              </div>
              <div className="auth-form-group">
                <input className="auth-form-input" placeholder="Password" type={showPassword ? "text" : "password"} value={password} onChange={e => setPassword(e.target.value)} required />
                <button type="button" className="auth-password-toggle" onClick={() => setShowPassword(!showPassword)}>
                  {showPassword ? <EyeOffIcon /> : <EyeIcon />}
                </button>
              </div>
              <div className="auth-form-group">
                <input className="auth-form-input" placeholder="Confirm Password" type={showConfirmPassword ? "text" : "password"} value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} required />
                <button type="button" className="auth-password-toggle" onClick={() => setShowConfirmPassword(!showConfirmPassword)}>
                  {showConfirmPassword ? <EyeOffIcon /> : <EyeIcon />}
                </button>
              </div>
              {renderPasswordStrength()}
              <div className="auth-checkbox-group" style={{ marginTop: '20px' }}>
                <input type="checkbox" checked={agreedTerms} onChange={e => setAgreedTerms(e.target.checked)} />
                <label>I agree to the <button type="button" onClick={() => setIsTermsOpen(true)} style={{ background: 'none', border: 'none', padding: 0, color: '#f97316', fontWeight: 600, cursor: 'pointer', textDecoration: 'underline' }}>Terms & Conditions</button></label>
              </div>
              <button type="submit" className="auth-btn-primary" disabled={submitting}>{submitting ? "Creating..." : "Create account"}</button>
            </form>
          </motion.div>
        );

      case "otp":
      case "forgot_otp":
        return (
          <motion.div
            key="otp"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            style={{ textAlign: 'center' }}
          >
            <h1 className="auth-form-title">Verify Email</h1>
            <p className="auth-form-subtitle" style={{ marginBottom: '40px' }}>
              We&apos;ve sent a code to <br/><strong>{email}</strong>
            </p>
            <form className="auth-form" onSubmit={handleVerifyOTP}>
              <div style={{ display: 'flex', gap: '10px', justifyContent: 'center', marginBottom: '30px' }}>
                {otp.map((digit, idx) => (
                  <input
                    key={idx}
                    id={`otp-${idx}`}
                    type="text"
                    maxLength={1}
                    value={digit}
                    onChange={(e) => {
                       const next = [...otp];
                       next[idx] = e.target.value;
                       setOtp(next);
                       if (e.target.value && idx < 5) document.getElementById(`otp-${idx+1}`)?.focus();
                    }}
                    style={{ width: '45px', height: '55px', textAlign: 'center', fontSize: '20px', fontWeight: '700', borderRadius: '10px', border: '1px solid var(--auth-border)', background: '#fdfdfd' }}
                  />
                ))}
              </div>
              <button type="submit" className="auth-btn-primary" disabled={submitting}>{submitting ? "Verifying..." : "Verify OTP"}</button>
              <button type="button" className="auth-link" onClick={() => setMode("login")} style={{ marginTop: '20px', background: 'none', border: 'none', color: '#666', fontSize: '12px' }}>&larr; Back to login</button>
            </form>
          </motion.div>
        );

      case "forgot_email":
        return (
          <motion.div
            key="forgot_email"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
          >
            <h1 className="auth-form-title">Reset Password</h1>
            <p className="auth-form-subtitle">Enter your email to receive a reset code.</p>
            <form className="auth-form" onSubmit={handleRequestPasswordReset}>
              <div className="auth-form-group">
                <input className="auth-form-input" placeholder="Email" type="email" value={email} onChange={e => setEmail(e.target.value)} required />
              </div>
              <button type="submit" className="auth-btn-primary" disabled={submitting}>{submitting ? "Sending..." : "Send Reset Code"}</button>
              <button type="button" className="auth-link" onClick={() => setMode("login")} style={{ marginTop: '20px', width: '100%', textAlign: 'center', background: 'none', border: 'none', color: '#666', fontSize: '12px' }}>&larr; Back to login</button>
            </form>
          </motion.div>
        );

      case "reset_password":
        return (
          <motion.div
              key="reset_password"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
          >
            <h1 className="auth-form-title">Set new password</h1>
            <p className="auth-form-subtitle">Choose a secure password for your account.</p>
            <form className="auth-form" onSubmit={handleFinalReset}>
              <div className="auth-form-group">
                <input className="auth-form-input" placeholder="New Password" type={showPassword ? "text" : "password"} value={password} onChange={e => setPassword(e.target.value)} required />
                <button type="button" className="auth-password-toggle" onClick={() => setShowPassword(!showPassword)}>
                  {showPassword ? <EyeOffIcon /> : <EyeIcon />}
                </button>
              </div>
              <div className="auth-form-group">
                <input className="auth-form-input" placeholder="Confirm New Password" type={showConfirmPassword ? "text" : "password"} value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} required />
                <button type="button" className="auth-password-toggle" onClick={() => setShowConfirmPassword(!showConfirmPassword)}>
                  {showConfirmPassword ? <EyeOffIcon /> : <EyeIcon />}
                </button>
              </div>
              {renderPasswordStrength()}
              <button type="submit" className="auth-btn-primary" disabled={submitting} style={{ marginTop: '20px' }}>{submitting ? "Updating..." : "Update Password"}</button>
            </form>
          </motion.div>
        );
    }
  };

  return (
    <main className="auth-page">
      <div className="auth-container">
        {/* ── Left Hero Panel (Floating Effect) ── */}
        <div className="auth-hero-wrapper">
          <div className="auth-hero">
            <div className="auth-hero-slideshow">
              {SLIDES.map((src, i) => (
                <img key={src} src={src} alt="Architecture" className={`auth-hero-slide ${i === activeSlide ? "active" : ""}`} />
              ))}
            </div>
            
            <div className="auth-hero-top">
              <div className="auth-hero-brand">AI Architect</div>
              <button 
                type="button" 
                className="auth-hero-back-btn"
                onClick={() => router.push("/")}
              >
                Back to website <span className="arrow">→</span>
              </button>
            </div>

            <div className="auth-hero-footer">
              <h2 className="auth-hero-tagline">Intelligence Reinventing the Building Blocks of Design</h2>
              <div className="auth-hero-dots">
                {SLIDES.map((_, i) => (
                  <div key={i} className={`auth-hero-dot ${i === activeSlide ? "active" : ""}`} />
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* ── Right Form Panel ── */}
        <div className="auth-form-panel">
          <div className="auth-form-content-inner">
            <AnimatePresence mode="wait">
              {renderForm()}
            </AnimatePresence>

            {(mode === "login" || mode === "signup") && (
              <div style={{ marginTop: '20px' }}>
                <div className="auth-divider"><span>Or continue with</span></div>
                <div className="auth-social-row">
                  <button className="auth-btn-social"><GoogleIcon /> Google</button>
                  <button className="auth-btn-social"><AppleIcon /> Apple</button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
      
      <TermsModal 
        isOpen={isTermsOpen} 
        onClose={() => setIsTermsOpen(false)} 
        onAgree={() => setAgreedTerms(true)}
      />
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <AuthPageInner />
    </Suspense>
  );
}
