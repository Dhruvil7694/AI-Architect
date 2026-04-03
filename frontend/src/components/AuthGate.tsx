"use client";

import { useAuthStore } from "@/state/authStore";

type AuthGateProps = {
  children: React.ReactNode;
};

/**
 * Shows a loading state until GET /auth/me has completed, then renders children.
 * Prevents flash of logged-out UI on app load.
 */
export function AuthGate({ children }: AuthGateProps) {
  const authLoaded = useAuthStore((state) => state.authLoaded);

  if (!authLoaded) {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-[#fdfdfc]">
        <div className="flex flex-col items-center gap-4">
          <div
            className="h-10 w-10 animate-spin rounded-full border-2 border-neutral-200 border-t-orange-500"
            aria-hidden
          />
          <p className="text-sm text-neutral-500">Loading…</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
