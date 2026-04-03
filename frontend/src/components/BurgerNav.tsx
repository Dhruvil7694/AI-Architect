"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuthStore } from "@/state/authStore";

const menuItems = [
  { href: "/", label: "Home page" },
  { href: "/profile", label: "Profile" },
] as const;

type BurgerNavProps = {
  /** When true, only render the burger button + menu (no header). Use inside another bar with button on the right. */
  variant?: "standalone" | "embedded";
};

export default function BurgerNav({ variant = "standalone" }: BurgerNavProps) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.roles?.includes("admin") ?? false;

  const isActive = (href: string) =>
    pathname === href || pathname?.startsWith(href + "/");

  const burgerButton = (
    <button
      type="button"
      onClick={() => setOpen(true)}
      className="flex h-9 w-9 items-center justify-center rounded-lg text-neutral-600 transition-colors hover:bg-neutral-100 hover:text-neutral-900"
      aria-label="Open menu"
    >
      <svg
        className="h-5 w-5"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M4 6h16M4 12h16M4 18h16"
        />
      </svg>
    </button>
  );

  return (
    <>
      {variant === "standalone" ? (
        <header className="fixed left-0 right-0 top-0 z-40 flex h-14 items-center border-b border-neutral-100 bg-white/95 px-4 shadow-sm backdrop-blur supports-[backdrop-filter]:bg-white/80">
          {burgerButton}
        </header>
      ) : (
        burgerButton
      )}

      {/* Overlay */}
      {open && (
        <div
          className="fixed inset-0 z-50 bg-neutral-900/20 backdrop-blur-sm"
          aria-hidden
          onClick={() => setOpen(false)}
        />
      )}

      {/* Side menu */}
      <aside
        className={`fixed left-0 top-0 z-50 h-full w-64 border-r border-neutral-200 bg-white shadow-xl transition-transform duration-200 ease-out ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
        aria-label="Main navigation"
      >
        <div className="flex h-14 items-center justify-between border-b border-neutral-100 px-4">
          <span className="font-semibold text-neutral-800">Menu</span>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-neutral-500 hover:bg-neutral-100 hover:text-neutral-900"
            aria-label="Close menu"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <nav className="flex flex-col gap-0.5 p-3">
          {menuItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setOpen(false)}
              className={`rounded-lg px-4 py-3 text-sm font-medium transition-colors ${
                isActive(item.href)
                  ? "bg-orange-50 text-orange-700"
                  : "text-neutral-700 hover:bg-neutral-50"
              }`}
            >
              {item.label}
            </Link>
          ))}
          {isAdmin && (
            <Link
              href="/admin/users"
              onClick={() => setOpen(false)}
              className={`rounded-lg px-4 py-3 text-sm font-medium transition-colors ${
                isActive("/admin/users")
                  ? "bg-orange-50 text-orange-700"
                  : "text-neutral-700 hover:bg-neutral-50"
              }`}
            >
              User Management
            </Link>
          )}
        </nav>
      </aside>
    </>
  );
}
