"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/state/authStore";

/**
 * AuthPopup — appears after a delay when user is not logged in.
 * Shows a cinematic modal prompting signup/login.
 * 
 * Usage: Add <AuthPopup /> to your layout or protected pages.
 * 
 * Props:
 *  - delayMs: time before popup appears (default: 120000 = 2 min)
 *  - dismissCooldownMs: how long before showing again after dismiss (default: 300000 = 5 min)
 */

const POPUP_DELAY_KEY = "auth_popup_last_dismissed";

interface AuthPopupProps {
  delayMs?: number;
  dismissCooldownMs?: number;
}

export default function AuthPopup({
  delayMs = 120000,
  dismissCooldownMs = 300000,
}: AuthPopupProps) {
  const [visible, setVisible] = useState(false);
  const [closing, setClosing] = useState(false);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const router = useRouter();

  useEffect(() => {
    // Don't show if already authenticated
    if (isAuthenticated) return;

    // Check if recently dismissed
    const lastDismissed = localStorage.getItem(POPUP_DELAY_KEY);
    if (lastDismissed) {
      const elapsed = Date.now() - parseInt(lastDismissed, 10);
      if (elapsed < dismissCooldownMs) {
        // Schedule after remaining cooldown
        const remaining = dismissCooldownMs - elapsed;
        const timer = setTimeout(() => setVisible(true), remaining);
        return () => clearTimeout(timer);
      }
    }

    // Show popup after delay
    const timer = setTimeout(() => setVisible(true), delayMs);
    return () => clearTimeout(timer);
  }, [isAuthenticated, delayMs, dismissCooldownMs]);

  const handleDismiss = useCallback(() => {
    setClosing(true);
    localStorage.setItem(POPUP_DELAY_KEY, Date.now().toString());
    setTimeout(() => {
      setVisible(false);
      setClosing(false);
    }, 300);
  }, []);

  const handleNavigate = useCallback((path: string) => {
    setClosing(true);
    setTimeout(() => {
      router.push(path);
    }, 200);
  }, [router]);

  if (!visible || isAuthenticated) return null;

  return (
    <div
      className={`auth-popup-overlay ${closing ? "closing" : ""}`}
      onClick={(e) => {
        if (e.target === e.currentTarget) handleDismiss();
      }}
    >
      <div className={`auth-popup-card ${closing ? "closing" : ""}`}>
        <button
          className="auth-popup-close"
          onClick={handleDismiss}
          aria-label="Close"
        >
          ✕
        </button>

        <div className="auth-popup-icon">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#f97316" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 21h18" />
            <path d="M5 21V7a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v14" />
            <path d="M9 21v-4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v4" />
            <path d="M10 9h4" />
            <path d="M10 13h4" />
          </svg>
        </div>

        <h2 className="auth-popup-title">Unlock Full Access</h2>
        <p className="auth-popup-desc">
          Create a free account to save your projects, access AI-powered
          architectural tools, and collaborate with your team.
        </p>

        <div className="auth-popup-buttons">
          <button
            className="auth-popup-btn-primary"
            onClick={() => handleNavigate("/signup")}
          >
            Create Free Account
          </button>
          <button
            className="auth-popup-btn-secondary"
            onClick={() => handleNavigate("/login")}
          >
            I already have an account
          </button>
        </div>

        <div style={{ marginTop: '16px' }}>
          <button className="auth-popup-dismiss" onClick={handleDismiss}>
            Maybe later
          </button>
        </div>
      </div>
    </div>
  );
}
