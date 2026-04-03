"use client";

import { useAuthStore } from "@/state/authStore";

export default function ProfilePage() {
  const user = useAuthStore((state) => state.user);

  return (
    <section className="max-w-3xl space-y-6">
      <header>
        <h2 className="text-2xl font-semibold text-neutral-900">Profile</h2>
        <p className="text-sm text-neutral-600 mt-1">
          Manage your account information
        </p>
      </header>

      <div className="rounded-lg border border-neutral-200 bg-white p-6">
        <div className="flex items-center gap-6 mb-6 pb-6 border-b border-neutral-200">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-neutral-900 text-xl font-medium text-white">
            {user?.name?.[0]?.toUpperCase() || user?.email?.[0]?.toUpperCase() || "U"}
          </div>
          <div>
            <h3 className="text-lg font-semibold text-neutral-900">
              {user?.name || "User"}
            </h3>
            <p className="text-sm text-neutral-600">{user?.email}</p>
            {user?.roles && user.roles.length > 0 && (
              <div className="mt-2 flex gap-2">
                {user.roles.map((role) => (
                  <span
                    key={role}
                    className="inline-flex items-center rounded bg-neutral-100 px-2 py-0.5 text-xs font-medium text-neutral-700"
                  >
                    {role}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-neutral-900 mb-1.5">
              Full Name
            </label>
            <input
              type="text"
              defaultValue={user?.name || ""}
              className="w-full rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none focus:ring-1 focus:ring-neutral-900"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-neutral-900 mb-1.5">
              Email Address
            </label>
            <input
              type="email"
              defaultValue={user?.email || ""}
              className="w-full rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none focus:ring-1 focus:ring-neutral-900"
            />
          </div>

          <div className="pt-4">
            <button className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-neutral-800">
              Save Changes
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
