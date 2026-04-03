"use client";

import React, { ReactNode } from "react";
import { usePathname } from "next/navigation";
import BurgerNav from "@/components/BurgerNav";
import { ProtectedRoute } from "@/components/ProtectedRoute";

type ProtectedLayoutProps = {
  children: ReactNode;
};

export default function ProtectedLayout({ children }: ProtectedLayoutProps) {
  const pathname = usePathname();
  const isPlanner = pathname?.startsWith("/planner");

  return (
    <ProtectedRoute>
      <div className="flex min-h-screen w-full bg-[#fdfdfc] text-neutral-900 font-sans">
        {!isPlanner && <BurgerNav />}
        <div className={`flex flex-1 flex-col min-w-0 ${isPlanner ? "" : "pt-14"}`}>
          <main
            className={`flex min-h-[calc(100vh-3.5rem)] w-full flex-col ${
              isPlanner ? "flex-1" : "mx-auto max-w-[1600px] px-6 pb-10"
            }`}
          >
            {children}
          </main>
        </div>
      </div>
    </ProtectedRoute>
  );
}
