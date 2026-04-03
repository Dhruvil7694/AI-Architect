"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/state/authStore";
import { useNotificationStore } from "@/state/notificationStore";

type ProtectedRouteProps = {
  children: ReactNode;
};

/**
 * Shows a "Login required" toast and redirects to /login if the user is not authenticated.
 */
export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const router = useRouter();
  const authLoaded = useAuthStore((state) => state.authLoaded);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const addToast = useNotificationStore((state) => state.addToast);
  const toastFired = useRef(false);

  useEffect(() => {
    if (!authLoaded) return;
    if (!isAuthenticated) {
      if (!toastFired.current) {
        toastFired.current = true;
        addToast({
          type: "warning",
          title: "Login required",
          message: "Please log in to access this page.",
          duration: 4000,
        });
      }
      router.replace("/login");
    }
  }, [authLoaded, isAuthenticated, router, addToast]);

  if (!authLoaded) return null;
  if (!isAuthenticated) return null;

  return <>{children}</>;
}
