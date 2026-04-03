"use client";

import { useState, useRef, useEffect } from "react";
import type { LocationLevel } from "./useLocationHierarchy";
import type { BreadcrumbItem } from "./useLocationHierarchy";

type BreadcrumbSelectorProps = {
  breadcrumbs: BreadcrumbItem[];
  getOptionsForLevel: (level: LocationLevel) => { id: string; label: string }[];
  onSelectFp: (fpId: string) => void;
  onSelectLevel?: (level: LocationLevel, valueId: string) => void;
};

const SEARCH_MIN_OPTIONS = 4;

export function BreadcrumbSelector({
  breadcrumbs,
  getOptionsForLevel,
  onSelectFp,
  onSelectLevel,
}: BreadcrumbSelectorProps) {
  const [openLevel, setOpenLevel] = useState<LocationLevel | null>(null);
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!openLevel) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpenLevel(null);
        setSearchQuery("");
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [openLevel]);

  const handleSegmentClick = (item: BreadcrumbItem, el: HTMLElement) => {
    setAnchorEl(el);
    setOpenLevel(item.level);
    setSearchQuery("");
  };

  const allOptions = openLevel ? getOptionsForLevel(openLevel) : [];
  const searchLower = searchQuery.trim().toLowerCase();
  const options =
    searchLower && allOptions.length >= SEARCH_MIN_OPTIONS
      ? allOptions.filter(
          (opt) =>
            opt.label.toLowerCase().includes(searchLower) ||
            opt.id.toLowerCase().includes(searchLower),
        )
      : allOptions;

  const currentItem = openLevel
    ? breadcrumbs.find((b) => b.level === openLevel)
    : null;
  const showSearch = allOptions.length >= SEARCH_MIN_OPTIONS;

  const handleSelect = (id: string, label: string) => {
    if (openLevel === "fp") {
      onSelectFp(id);
    } else if (onSelectLevel) {
      onSelectLevel(openLevel!, id);
    }
    setOpenLevel(null);
    setSearchQuery("");
  };

  return (
    <div ref={ref} className="flex items-center gap-2 text-sm">
      {breadcrumbs.map((item, index) => (
        <span key={`${item.level}-${item.id}`} className="flex items-center gap-2">
          {index > 0 && (
            <span className="text-neutral-300 select-none">/</span>
          )}
          <button
            type="button"
            onClick={(e) => handleSegmentClick(item, e.currentTarget)}
            className="rounded px-1.5 py-0.5 text-neutral-700 hover:bg-neutral-100 hover:text-neutral-900 transition-colors"
          >
            {item.label}
          </button>
        </span>
      ))}

      {openLevel && anchorEl && (allOptions.length > 0 || searchQuery.length > 0) && (
        <div
          className="fixed z-50 mt-1 flex max-h-72 min-w-[220px] flex-col overflow-hidden rounded-lg border border-neutral-200 bg-white shadow-lg"
          style={{
            top: anchorEl.getBoundingClientRect().bottom + 4,
            left: anchorEl.getBoundingClientRect().left,
          }}
        >
          {showSearch && (
            <div className="border-b border-neutral-100 p-2">
              <input
                type="search"
                placeholder="Search..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.stopPropagation()}
                className="w-full rounded-md border border-neutral-200 px-3 py-2 text-sm placeholder:text-neutral-400 focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500"
                autoFocus
              />
            </div>
          )}
          <div className="max-h-60 min-h-0 overflow-auto py-1">
            {options.length === 0 ? (
              <div className="px-4 py-3 text-sm text-neutral-500">
                {searchQuery.trim() ? "No matches" : "No options"}
              </div>
            ) : (
              options.map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => handleSelect(opt.id, opt.label)}
                  className={`block w-full px-4 py-2 text-left text-sm hover:bg-neutral-50 ${
                    currentItem?.id === opt.id
                      ? "bg-orange-50 text-orange-700 font-medium"
                      : "text-neutral-700"
                  }`}
                >
                  {opt.label}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
