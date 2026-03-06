import type { ReactNode } from "react";

type AdminLayoutProps = {
  children: ReactNode;
};

export default function AdminLayout({ children }: AdminLayoutProps) {
  return (
    <div className="flex h-full flex-col gap-2">
      <header className="flex items-center justify-between rounded-md border border-amber-300 bg-amber-50 px-4 py-2">
        <div>
          <h2 className="text-sm font-semibold text-amber-900">Admin</h2>
          <p className="text-xs text-amber-800">
            User administration and system-level controls.
          </p>
        </div>
        <div className="text-xs text-amber-800">
          {/* Access control will be enforced via RBAC and middleware */}
          Admin only
        </div>
      </header>
      <div className="flex min-h-0 flex-1 rounded-md border border-neutral-200 bg-white p-4">
        {children}
      </div>
    </div>
  );
}

