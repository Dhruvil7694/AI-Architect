"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAdminGuard } from "@/middleware/roleGuard";
import { useUsersQuery } from "@/modules/admin/hooks/useAdminUsers";
import type { AdminUser } from "@/services/adminService";

export default function AdminUsersPage() {
  const router = useRouter();
  const isAdmin = useAdminGuard();
  const { data, isLoading, isError } = useUsersQuery();

  function handleRowClick(user: AdminUser) {
    router.push(`/admin/users/${user.id}`);
  }

  // Don't render anything while checking permissions
  if (!isAdmin) {
    return null;
  }

  return (
    <section className="max-w-7xl space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold text-neutral-900">Users</h2>
          <p className="text-sm text-neutral-600 mt-1">
            Manage application users, roles, and access
          </p>
        </div>
        <Link
          href="/admin/users/new"
          className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-neutral-800"
        >
          New User
        </Link>
      </header>

      <div className="rounded-lg border border-neutral-200 bg-white overflow-hidden">
        {isLoading && (
          <div className="p-8 text-center">
            <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-neutral-200 border-t-neutral-900"></div>
            <p className="mt-2 text-sm text-neutral-600">Loading users...</p>
          </div>
        )}
        
        {isError && (
          <div className="p-8 text-center">
            <p className="text-sm text-red-600">
              Unable to load users. Please try again.
            </p>
          </div>
        )}
        
        {!isLoading && !isError && (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-neutral-200 bg-neutral-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-neutral-600">
                    Name
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-neutral-600">
                    Email
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-neutral-600">
                    Roles
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-neutral-600">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-200">
                {data?.map((user) => (
                  <tr
                    key={user.id}
                    className="cursor-pointer transition-colors hover:bg-neutral-50"
                    onClick={() => handleRowClick(user)}
                  >
                    <td className="px-6 py-4 text-sm text-neutral-900">
                      {user.name || <span className="text-neutral-400">—</span>}
                    </td>
                    <td className="px-6 py-4 text-sm text-neutral-700">
                      {user.email}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex gap-1">
                        {user.roles?.map((role) => (
                          <span
                            key={role}
                            className="inline-flex items-center rounded bg-neutral-100 px-2 py-0.5 text-xs font-medium text-neutral-700"
                          >
                            {role}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                          user.isActive
                            ? "bg-emerald-100 text-emerald-700"
                            : "bg-red-100 text-red-700"
                        }`}
                      >
                        {user.isActive ? "Active" : "Inactive"}
                      </span>
                    </td>
                  </tr>
                ))}
                {!data?.length && (
                  <tr>
                    <td
                      colSpan={4}
                      className="px-6 py-8 text-center text-sm text-neutral-500"
                    >
                      No users found
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

