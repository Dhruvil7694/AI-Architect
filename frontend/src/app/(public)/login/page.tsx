"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import type { FormEvent } from "react";
import { login } from "@/services/authService";
import { useAuthStore } from "@/state/authStore";

function LoginPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const loginSuccess = useAuthStore((state) => state.loginSuccess);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const result = await login({ email, password });
      loginSuccess(result.user, { expiresAt: result.accessTokenExpiresAt });
      // Set cookie so middleware allows access to protected routes
      if (typeof document !== "undefined") {
        const maxAge = 86400; // 1 day
        document.cookie = `access_token=1; path=/; max-age=${maxAge}; SameSite=Lax`;
      }
      const redirectTo = searchParams.get("redirect") ?? "/dashboard";
      router.push(redirectTo);
    } catch (err) {
      const errorMessage =
        err instanceof Error
          ? err.message
          : "Unable to sign in. Please try again.";
      setError(errorMessage);
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-neutral-100 text-neutral-900">
      <section className="w-full max-w-md rounded-xl bg-white p-8 shadow-sm">
        <header className="mb-6">
          <h1 className="text-xl font-semibold text-neutral-900">
            Sign in to Site Planner
          </h1>
          <p className="mt-1 text-sm text-neutral-500">
            Access plots, metrics, and development scenarios.
          </p>
        </header>
        <form onSubmit={handleSubmit} className="space-y-4 text-sm">
          <div className="space-y-1">
            <label
              htmlFor="email"
              className="block text-xs font-medium text-neutral-700"
            >
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border border-neutral-300 px-3 py-2 text-sm text-neutral-900 outline-none ring-0 placeholder:text-neutral-400 focus:border-neutral-900"
            />
          </div>
          <div className="space-y-1">
            <label
              htmlFor="password"
              className="block text-xs font-medium text-neutral-700"
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border border-neutral-300 px-3 py-2 text-sm text-neutral-900 outline-none ring-0 placeholder:text-neutral-400 focus:border-neutral-900"
            />
          </div>
          {error && (
            <p className="text-xs text-red-600" role="alert">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={submitting}
            className="mt-2 inline-flex w-full items-center justify-center rounded-md bg-neutral-900 px-3 py-2 text-sm font-medium text-neutral-50 disabled:opacity-60"
          >
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <footer className="mt-8 flex justify-between text-xs text-neutral-400">
          <span>AI Site Planning System</span>
          <Link href="https://nextjs.org" className="hover:text-neutral-600">
            Powered by Next.js
          </Link>
        </footer>
      </section>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center bg-neutral-100 text-neutral-900">
          <span className="text-sm text-neutral-500">Loading login…</span>
        </main>
      }
    >
      <LoginPageInner />
    </Suspense>
  );
}

