"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useUsersQuery } from "@/modules/admin/hooks/useAdminUsers";
import type { AdminUser } from "@/services/adminService";

export default function AdminUsersPage() {
  const router = useRouter();
  const { data, isLoading, isError } = useUsersQuery();

  function handleRowClick(user: AdminUser) {
    router.push(`/admin/users/${user.id}`);
  }

  return (
    <section className="w-full space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-neutral-900">Users</h2>
          <p className="text-sm text-neutral-500">
            Manage application users, roles, and access.
          </p>
        </div>
        <Link
          href="/admin/users/new"
          className="rounded-md border border-neutral-300 bg-neutral-900 px-3 py-1.5 text-xs font-medium text-neutral-50"
        >
          New user
        </Link>
      </header>
      <div className="rounded-md border border-neutral-200 bg-white p-4 text-sm text-neutral-600">
        {isLoading && (
          <p className="text-xs text-neutral-500">Loading users…</p>
        )}
        {isError && (
          <p className="text-xs text-red-600">
            Unable to load users. Please try again.
          </p>
        )}
        {!isLoading && !isError && (
          <table className="w-full table-auto border-collapse text-xs">
            <thead>
              <tr className="border-b border-neutral-200 text-left text-[11px] uppercase tracking-wide text-neutral-500">
                <th className="pb-2 pr-2">Name</th>
                <th className="pb-2 pr-2">Email</th>
                <th className="pb-2 pr-2">Roles</th>
                <th className="pb-2 pr-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {data?.map((user) => (
                <tr
                  key={user.id}
                  className="cursor-pointer border-b border-neutral-100 hover:bg-neutral-50"
                  onClick={() => handleRowClick(user)}
                >
                  <td className="py-1.5 pr-2">
                    {user.name ?? <span className="text-neutral-400">—</span>}
                  </td>
                  <td className="py-1.5 pr-2 text-neutral-700">
                    {user.email}
                  </td>
                  <td className="py-1.5 pr-2 text-neutral-500">
                    {user.roles.join(", ")}
                  </td>
                  <td className="py-1.5 pr-2 text-neutral-500">
                    {user.isActive ? "Active" : "Inactive"}
                  </td>
                </tr>
              ))}
              {!data?.length && (
                <tr>
                  <td
                    colSpan={4}
                    className="py-2 text-center text-neutral-500"
                  >
                    No users found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

