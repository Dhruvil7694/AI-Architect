"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";

const COOKIE_CONSENT_KEY = "ai_arch_cookie_consent";

export default function CookieConsent() {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    // Check if consent has already been given or denied
    const consent = localStorage.getItem(COOKIE_CONSENT_KEY);
    if (!consent) {
      // Delay to not immediately annoy user
      const timer = setTimeout(() => setIsVisible(true), 1500);
      return () => clearTimeout(timer);
    }
  }, []);

  const handleAction = (type: 'accept' | 'reject') => {
    localStorage.setItem(COOKIE_CONSENT_KEY, type);
    setIsVisible(false);
    // You could trigger analytics opt-in/out here
  };

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          className="cookie-consent-bar"
          initial={{ y: 100, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 100, opacity: 0 }}
          transition={{ type: "spring", stiffness: 200, damping: 25 }}
        >
          <div className="cookie-content">
            <div className="cookie-icon">🍪</div>
            <div className="cookie-text">
              <h4>Architectural Insights</h4>
              <p>
                We use cookies to understand how you interact with our AI and to refine your experience.
              </p>
            </div>
            <div className="cookie-actions">
              <button 
                onClick={() => handleAction('reject')}
                className="cookie-btn cookie-btn-secondary"
              >
                Reject
              </button>
              <button 
                onClick={() => handleAction('accept')}
                className="cookie-btn cookie-btn-primary"
              >
                Accept All
              </button>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
