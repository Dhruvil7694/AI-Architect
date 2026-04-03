"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * Admin index: redirect to user management.
 */
export default function AdminPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/admin/users");
  }, [router]);

  return (
    <div className="flex min-h-[200px] items-center justify-center text-neutral-500">
      Redirecting to Admin…
    </div>
  );
}
