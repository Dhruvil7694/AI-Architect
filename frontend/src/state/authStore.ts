import { create } from "zustand";
import type { User } from "@/services/authService";

type AuthState = {
  user: User | null;
  isAuthenticated: boolean;
  /** True once GET /auth/me has completed (success or 401). Prevents flash of logged-out UI. */
  authLoaded: boolean;
  expiresAt?: string;
  sessionId?: string;
  lastVerifiedAt?: string;
};

type AuthActions = {
  loginSuccess: (user: User, options?: { expiresAt?: string }) => void;
  logout: () => void;
  setUser: (user: User | null) => void;
  setAuthLoaded: (loaded: boolean) => void;
  setSessionMeta: (meta: {
    expiresAt?: string;
    sessionId?: string;
    lastVerifiedAt?: string;
  }) => void;
};

export type AuthStore = AuthState & AuthActions;

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  isAuthenticated: false,
  authLoaded: false,
  expiresAt: undefined,
  sessionId: undefined,
  lastVerifiedAt: undefined,

  loginSuccess: (user, options) =>
    set({
      user,
      isAuthenticated: true,
      expiresAt: options?.expiresAt,
      lastVerifiedAt: new Date().toISOString(),
    }),

  logout: () =>
    set({
      user: null,
      isAuthenticated: false,
      authLoaded: true,
      expiresAt: undefined,
      sessionId: undefined,
      lastVerifiedAt: undefined,
    }),

  setAuthLoaded: (authLoaded) =>
    set((state) => ({ ...state, authLoaded })),

  setUser: (user) =>
    set((state) => ({
      ...state,
      user,
      isAuthenticated: Boolean(user),
    })),

  setSessionMeta: (meta) =>
    set((state) => ({
      ...state,
      ...meta,
    })),
}));

