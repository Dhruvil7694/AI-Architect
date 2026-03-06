import Link from "next/link";
import type { ReactNode } from "react";

type ProtectedLayoutProps = {
  children: ReactNode;
};

export default function ProtectedLayout({ children }: ProtectedLayoutProps) {
  return (
    <div className="flex min-h-screen bg-neutral-100 text-neutral-900">
      <aside className="flex w-64 flex-col border-r border-neutral-200 bg-white px-4 py-6">
        <div className="mb-6">
          <h1 className="text-sm font-semibold tracking-wide text-neutral-900">
            AI Site Planner
          </h1>
          <p className="mt-1 text-xs text-neutral-500">
            Plots · Metrics · Geometry
          </p>
        </div>
        <nav className="flex-1 space-y-1 text-sm">
          <Link
            href="/dashboard"
            className="block rounded-md px-3 py-2 text-neutral-700 hover:bg-neutral-100"
          >
            Dashboard
          </Link>
          <Link
            href="/planner"
            className="block rounded-md px-3 py-2 text-neutral-700 hover:bg-neutral-100"
          >
            Planner
          </Link>
          <Link
            href="/plots"
            className="block rounded-md px-3 py-2 text-neutral-700 hover:bg-neutral-100"
          >
            Plots
          </Link>
          <Link
            href="/admin/users"
            className="block rounded-md px-3 py-2 text-neutral-700 hover:bg-neutral-100"
          >
            Admin · Users
          </Link>
        </nav>
        <div className="mt-4 border-t border-neutral-200 pt-4 text-xs text-neutral-500">
          {/* User info / logout will be wired to auth later */}
          <p>Signed in user</p>
        </div>
      </aside>
      <div className="flex min-h-screen flex-1 flex-col">
        <header className="flex h-14 items-center justify-between border-b border-neutral-200 bg-white px-6">
          <div className="text-xs font-medium uppercase tracking-wide text-neutral-500">
            Planner Console
          </div>
          <div className="text-xs text-neutral-500">
            {/* Breadcrumbs / status bar can go here */}
          </div>
        </header>
        <main className="flex-1 overflow-auto bg-neutral-50 p-6">{children}</main>
      </div>
    </div>
  );
}

