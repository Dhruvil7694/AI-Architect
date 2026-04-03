import { useAuthStore } from "@/state/authStore";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export function useAdminGuard() {
  const router = useRouter();
  const user = useAuthStore((state) => state.user);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);

  useEffect(() => {
    if (!isAuthenticated) {
      router.push("/login");
      return;
    }

    const isAdmin = user?.roles?.includes("admin");
    if (!isAdmin) {
      router.push("/dashboard");
    }
  }, [isAuthenticated, user, router]);

  return user?.roles?.includes("admin") || false;
}
