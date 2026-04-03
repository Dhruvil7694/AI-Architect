"use client";

import { useEffect } from "react";
import { getCurrentUser } from "@/services/authService";
import { useAuthStore } from "@/state/authStore";

/**
 * On app load: GET /api/auth/me (CSRF cookie is set automatically by that response).
 * Populates auth store if session valid; sets authLoaded when done to avoid flash of logged-out UI.
 */
export function AuthHydration() {
  const setUser = useAuthStore((state) => state.setUser);
  const setAuthLoaded = useAuthStore((state) => state.setAuthLoaded);

  useEffect(() => {
    getCurrentUser()
      .then((user) => {
        setUser(user);
        setAuthLoaded(true);
      })
      .catch(() => {
        setAuthLoaded(true);
      });
  }, [setUser, setAuthLoaded]);

  return null;
}
