import { useAuthStore } from "@/state/authStore";
import type { Role } from "@/services/authService";

export function useRoleGuard(requiredRoles: Role[] | Role) {
  const roles = useAuthStore((state) => state.user?.roles ?? []);
  const required = Array.isArray(requiredRoles) ? requiredRoles : [requiredRoles];

  const hasRole = required.length === 0
    ? true
    : required.some((role) => roles.includes(role));

  return {
    hasRole,
    roles,
  };
}

