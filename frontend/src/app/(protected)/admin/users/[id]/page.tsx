"use client";

import type { ChangeEvent, FormEvent } from "react";
import { useRouter } from "next/navigation";
import {
  useUserQuery,
  useUpdateUserMutation,
  useDeactivateUserMutation,
} from "@/modules/admin/hooks/useAdminUsers";
import type { Role } from "@/services/authService";

type AdminUserDetailPageProps = {
  params: {
    id: string;
  };
};

export default function AdminUserDetailPage({
  params,
}: AdminUserDetailPageProps) {
  const router = useRouter();
  const { data, isLoading } = useUserQuery(params.id);
  const updateUser = useUpdateUserMutation(params.id);
  const deactivateUser = useDeactivateUserMutation(params.id);

  if (isLoading || !data) {
    return (
      <section className="w-full space-y-4">
        <p className="text-sm text-neutral-500">Loading user…</p>
      </section>
    );
  }

  const handleRoleChange = (event: ChangeEvent<HTMLSelectElement>) => {
    const roles = event.target.value.split(",").filter(Boolean) as Role[];
    updateUser.mutate({ roles });
  };

  const handleToggleActive = (event: FormEvent) => {
    event.preventDefault();
    if (data.isActive) {
      deactivateUser.mutate();
    } else {
      updateUser.mutate({ isActive: true });
    }
  };

  return (
    <section className="w-full space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-neutral-900">
            User detail · {data.email}
          </h2>
          <p className="text-sm text-neutral-500">
            View and edit user information, roles, and status.
          </p>
        </div>
        <button
          type="button"
          onClick={() => router.back()}
          className="rounded-md border border-neutral-300 px-3 py-1.5 text-xs text-neutral-700"
        >
          Back
        </button>
      </header>
      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-md border border-neutral-200 bg-white p-4 text-sm text-neutral-700 md:col-span-2">
          <dl className="space-y-2 text-xs">
            <div className="flex justify-between">
              <dt className="text-neutral-500">Name</dt>
              <dd>{data.name ?? "—"}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-neutral-500">Email</dt>
              <dd>{data.email}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-neutral-500">Roles</dt>
              <dd>{data.roles.join(", ")}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-neutral-500">Status</dt>
              <dd>{data.isActive ? "Active" : "Inactive"}</dd>
            </div>
          </dl>
        </div>
        <div className="space-y-3 rounded-md border border-neutral-200 bg-white p-4 text-sm text-neutral-700">
          <form className="space-y-2">
            <label className="block text-[11px] font-medium text-neutral-600">
              Roles
            </label>
            <select
              defaultValue={data.roles.join(",")}
              onChange={handleRoleChange}
              className="w-full rounded-md border border-neutral-300 px-2 py-1 text-xs"
            >
              <option value="user">User</option>
              <option value="user,admin">User + Admin</option>
              <option value="admin">Admin</option>
            </select>
          </form>
          <form onSubmit={handleToggleActive} className="space-y-2">
            <label className="block text-[11px] font-medium text-neutral-600">
              Account status
            </label>
            <button
              type="submit"
              className={`w-full rounded-md px-3 py-1.5 text-xs font-medium ${
                data.isActive
                  ? "bg-red-600 text-white"
                  : "bg-emerald-600 text-white"
              }`}
            >
              {data.isActive ? "Deactivate user" : "Activate user"}
            </button>
          </form>
        </div>
      </div>
    </section>
  );
}

