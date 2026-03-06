import { useAuthStore } from "@/state/authStore";

export function useAuth() {
  const user = useAuthStore((state) => state.user);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const loginSuccess = useAuthStore((state) => state.loginSuccess);
  const logout = useAuthStore((state) => state.logout);

  return {
    user,
    isAuthenticated,
    loginSuccess,
    logout,
  };
}

