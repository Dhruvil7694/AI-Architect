"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import GlassSurface from "@/components/GlassSurface";

const navItems = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/planner/inputs", label: "Planner" },
  { href: "/admin/users", label: "User Management" },
  { href: "/settings", label: "Settings" },
  { href: "/profile", label: "Profile" },
];

export default function TopNavGlass() {
  const pathname = usePathname();

  const isActive = (href: string) => {
    if (href === "/planner/inputs") {
      return pathname?.startsWith("/planner");
    }
    return pathname === href || pathname?.startsWith(href + "/");
  };

  return (
    <GlassSurface
      width={"100%" as any}
      height={80}
      borderRadius={24}
      borderWidth={0.09}
      brightness={98}
      opacity={0.8}
      blur={12}
      backgroundOpacity={0.4}
      saturation={1.1}
      className="shadow-[0_20px_50px_rgba(0,0,0,0.06)]"
    >
      <div className="flex w-full items-center justify-between px-8 py-2 h-full">
        {/* Brand */}
        <Link href="/dashboard" className="flex items-center gap-2">
          <div className="h-10 w-10 flex items-center justify-center rounded-xl bg-orange-500 text-white shadow-lg shadow-orange-500/20">
             <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
             </svg>
          </div>
          <span className="font-heading text-xl font-bold tracking-tight text-neutral-900">
            AI<span className="text-orange-500">Architect</span>
          </span>
        </Link>

        {/* Navigation */}
        <nav className="flex items-center gap-2">
          {navItems.map((item) => {
            const active = isActive(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`group relative rounded-full px-5 py-2 text-sm font-semibold transition-all duration-300 ${
                  active
                    ? "bg-neutral-900 text-white shadow-md shadow-neutral-900/10"
                    : "text-neutral-500 hover:bg-neutral-100/50 hover:text-neutral-900"
                }`}
              >
                <span>{item.label}</span>
                {active && (
                  <span className="absolute -bottom-1.5 left-1/2 h-1 w-5 -translate-x-1/2 rounded-full bg-orange-500" />
                )}
              </Link>
            );
          })}
        </nav>

        {/* Right Actions */}
        <div className="flex items-center gap-4">
          <button className="h-10 w-10 flex items-center justify-center rounded-full border border-neutral-100 bg-white shadow-sm hover:shadow-md transition-all text-neutral-500 hover:text-orange-500">
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
            </svg>
          </button>
          <div className="h-10 w-10 rounded-full border-2 border-orange-100 p-0.5 shadow-sm">
             <div className="h-full w-full rounded-full bg-gradient-to-tr from-orange-400 to-amber-300 flex items-center justify-center text-white font-bold text-sm">
                JS
             </div>
          </div>
        </div>
      </div>
    </GlassSurface>
  );
}

