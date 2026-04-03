"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import ArchitectLoader from "@/components/ArchitectLoader";

export default function SignupRedirect() {
  const router = useRouter();

  useEffect(() => {
    // Redirect to the unified auth page with signup mode
    router.replace("/login?mode=signup");
  }, [router]);

  return <ArchitectLoader label="Preparing secure portal..." />;
}
