"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, useRef, useEffect } from "react";
import { useAuthStore } from "@/state/authStore";
import { logout as logoutService } from "@/services/authService";
import { 
  LayoutDashboard, 
  CheckSquare, 
  Calendar, 
  BarChart3, 
  Users, 
  Settings, 
  HelpCircle, 
  LogOut,
  Download
} from "lucide-react";

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const user = useAuthStore((state) => state.user);
  const logoutStore = useAuthStore((state) => state.logout);
  
  const [isCollapsed, setIsCollapsed] = useState(false);
  
  const handleLogout = async () => {
    try {
      await logoutService();
    } catch (error) {
      console.error("Logout error:", error);
    } finally {
      logoutStore();
      router.push("/login");
    }
  };

  const menuItems = [
    { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { href: "/planner", label: "Tasks", icon: CheckSquare, badge: "12+" },
    { href: "/plots", label: "Calendar", icon: Calendar },
    { href: "/analytics", label: "Analytics", icon: BarChart3 },
    { href: "/admin/users", label: "Team", icon: Users },
  ];

  const generalItems = [
    { href: "/settings", label: "Settings", icon: Settings },
    { href: "/help", label: "Help", icon: HelpCircle },
  ];

  const isActive = (href: string) => pathname === href || pathname?.startsWith(href + "/");

  return (
    <aside className={`flex flex-col border-r border-neutral-100 bg-white transition-all duration-300 ${
      isCollapsed ? "w-20" : "w-64"
    }`}>
      {/* Brand */}
      <div className="px-6 py-8 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-orange-500 text-white shadow-lg shadow-orange-200">
          <div className="h-6 w-6 border-2 border-white rounded-full flex items-center justify-center">
             <div className="h-2 w-2 bg-white rounded-full" />
          </div>
        </div>
        {!isCollapsed && (
          <span className="text-xl font-bold text-neutral-900 tracking-tight">Donezo</span>
        )}
      </div>

      <div className="flex-1 px-4 overflow-y-auto custom-scrollbar">
        {/* Menu Section */}
        <div className="mb-8">
          {!isCollapsed && (
            <p className="px-4 mb-4 text-[11px] font-bold text-neutral-400 uppercase tracking-widest">
              Menu
            </p>
          )}
          <nav className="space-y-1">
            {menuItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`group flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition-all ${
                  isActive(item.href)
                    ? "bg-orange-500/5 text-orange-600"
                    : "text-neutral-500 hover:bg-neutral-50 hover:text-neutral-900"
                } ${isCollapsed ? "justify-center" : ""}`}
              >
                <item.icon className={`h-5 w-5 ${isActive(item.href) ? "text-orange-600" : "text-neutral-400 group-hover:text-neutral-900"}`} strokeWidth={isActive(item.href) ? 2.5 : 2} />
                {!isCollapsed && (
                  <div className="flex flex-1 items-center justify-between">
                    <span>{item.label}</span>
                    {item.badge && (
                      <span className="px-1.5 py-0.5 rounded-md bg-neutral-900 text-[10px] text-white font-bold">
                        {item.badge}
                      </span>
                    )}
                  </div>
                )}
                {isActive(item.href) && !isCollapsed && (
                   <div className="absolute left-0 w-1 h-6 bg-orange-600 rounded-r-full" />
                )}
              </Link>
            ))}
          </nav>
        </div>

        {/* General Section */}
        <div className="mb-8">
          {!isCollapsed && (
            <p className="px-4 mb-4 text-[11px] font-bold text-neutral-400 uppercase tracking-widest">
              General
            </p>
          )}
          <nav className="space-y-1">
            {generalItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`group flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition-all ${
                  isActive(item.href)
                    ? "bg-orange-500/5 text-orange-600"
                    : "text-neutral-500 hover:bg-neutral-50 hover:text-neutral-900"
                } ${isCollapsed ? "justify-center" : ""}`}
              >
                <item.icon className="h-5 w-5 text-neutral-400 group-hover:text-neutral-900" strokeWidth={2} />
                {!isCollapsed && <span>{item.label}</span>}
              </Link>
            ))}
            <button
              onClick={handleLogout}
              className={`w-full group flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition-all text-neutral-500 hover:bg-red-50 hover:text-red-600 ${isCollapsed ? "justify-center" : ""}`}
            >
              <LogOut className="h-5 w-5 text-neutral-400 group-hover:text-red-600" strokeWidth={2} />
              {!isCollapsed && <span>Logout</span>}
            </button>
          </nav>
        </div>
      </div>

      {/* Footer Card */}
      {!isCollapsed && (
        <div className="p-4 mt-auto">
          <div className="rounded-2xl bg-neutral-900 p-5 relative overflow-hidden group">
            <div className="relative z-10">
              <div className="h-10 w-10 rounded-full bg-white/10 backdrop-blur-md flex items-center justify-center mb-4">
                <Download className="h-5 w-5 text-white" />
              </div>
              <h4 className="text-white text-sm font-bold mb-1">Download our Mobile App</h4>
              <p className="text-neutral-400 text-xs mb-4">Get easy access in another way</p>
              <button className="w-full py-2 bg-orange-500 hover:bg-orange-600 text-white text-xs font-bold rounded-lg transition-colors">
                Download
              </button>
            </div>
            {/* Decorative background circle */}
            <div className="absolute -bottom-10 -right-10 w-32 h-32 bg-orange-500/20 rounded-full blur-2xl group-hover:bg-orange-500/30 transition-all" />
          </div>
        </div>
      )}

      {/* Collapse Button */}
      <button
        onClick={() => setIsCollapsed(!isCollapsed)}
        className="p-4 text-neutral-400 hover:text-neutral-900 transition-colors mx-auto"
      >
        <div className={`h-8 w-8 rounded-full border border-neutral-100 flex items-center justify-center transition-transform ${isCollapsed ? "rotate-180" : ""}`}>
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </div>
      </button>
    </aside>
  );
}

