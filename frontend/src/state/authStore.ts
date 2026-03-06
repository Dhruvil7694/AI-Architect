import { create } from "zustand";
import type { User } from "@/services/authService";

type AuthState = {
  user: User | null;
  isAuthenticated: boolean;
  expiresAt?: string;
  sessionId?: string;
  lastVerifiedAt?: string;
};

type AuthActions = {
  loginSuccess: (user: User, options?: { expiresAt?: string }) => void;
  logout: () => void;
  setUser: (user: User | null) => void;
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
      expiresAt: undefined,
      sessionId: undefined,
      lastVerifiedAt: undefined,
    }),

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

