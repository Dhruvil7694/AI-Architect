"use client";

import { useState } from "react";
import Link from "next/link";
import { Twitter, Linkedin, Instagram } from "lucide-react";
import { usePlannerStore } from "@/state/plannerStore";
import type { PlannerStage } from "@/state/plannerStore";
import { useAuthStore } from "@/state/authStore";
import { BreadcrumbSelector, useLocationHierarchy } from "@/modules/planner/location";
import { DevelopmentInputs } from "@/modules/planner/components/DevelopmentInputs";
import { CalculationModal } from "./CalculationModal";
import StaggeredMenu from "@/components/StaggeredMenu";

type PlannerTopBarProps = {
  profileName: string;
  isHighRise: boolean;
  stage: PlannerStage;
  isGenerating: boolean;
  onGeneratePlan: () => void;
  imageModel: string;
  onImageModelChange: (model: string) => void;
};

export function PlannerTopBar({
  profileName,
  isHighRise,
  stage,
  isGenerating,
  onGeneratePlan,
  imageModel,
  onImageModelChange,
}: PlannerTopBarProps) {
  const [calculationOpen, setCalculationOpen] = useState(false);
  const isInputsPanelOpen = usePlannerStore((s) => s.isInputsPanelOpen);
  const toggleInputsPanel = usePlannerStore((s) => s.toggleInputsPanel);
  const selectedPlotId = usePlannerStore((s) => s.selectedPlotId);
  const hasUnitMix = usePlannerStore((s) => s.inputs.unitMix?.length) ?? 0;

  const [menuOpen, setMenuOpen] = useState(false);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const {
    breadcrumbs,
    getOptionsForLevel,
    selectFp,
    selectLevel,
  } = useLocationHierarchy();

  const showPostGenerationActions = stage === "floor-design";
  const canGenerate =
    isHighRise && !!selectedPlotId && hasUnitMix > 0 && !isGenerating;

  return (
    <>
      {menuOpen && (
        <div
          className="fixed inset-0 z-[55] bg-neutral-900/20 backdrop-blur-sm"
          aria-hidden
          onClick={() => setMenuOpen(false)}
        />
      )}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-neutral-200 bg-white px-6 shadow-sm">
        <div className="flex items-center gap-6 min-w-0">
          <Link
            href="/"
            className="shrink-0 font-semibold text-neutral-800 hover:text-neutral-600"
          >
            Formless Architect
          </Link>
          <div className="min-w-0 flex items-center gap-2 text-sm">
            <BreadcrumbSelector
              breadcrumbs={breadcrumbs}
              getOptionsForLevel={getOptionsForLevel}
              onSelectFp={selectFp}
              onSelectLevel={selectLevel}
            />
          </div>
          <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={() => {
              setMenuOpen(false);
              toggleInputsPanel();
            }}
            className={`rounded-full px-4 py-2 text-sm font-medium transition-colors ${
              isInputsPanelOpen
                ? "bg-orange-100 text-orange-700"
                : "border border-neutral-200 text-neutral-700 hover:bg-neutral-50"
            }`}
          >
            Input
          </button>

          {/* Image model selector */}
          <div className="flex items-center gap-1.5">
            <span className="hidden lg:inline text-[10px] font-medium text-neutral-400 uppercase tracking-wide">Image</span>
            <select
              value={imageModel}
              onChange={(e) => onImageModelChange(e.target.value)}
              disabled={isGenerating}
              className="rounded-lg border border-neutral-200 bg-white px-2.5 py-1.5 text-xs font-medium text-neutral-700 focus:outline-none focus:ring-1 focus:ring-neutral-400 disabled:opacity-50"
              title="Image generation model"
            >
              <option value="dalle3">DALL-E 3</option>
              <option value="gemini">Nano Banana (Gemini)</option>
              <option value="recraft">Recraft</option>
              <option value="ideogram">Ideogram V2</option>
              <option value="flux">FLUX</option>
              <option value="svg_only">SVG only</option>
            </select>
          </div>

          {isHighRise && (
            <button
              type="button"
              onClick={onGeneratePlan}
              disabled={!canGenerate}
              className={`rounded-xl px-5 py-2 text-sm font-semibold transition-all ${
                canGenerate
                  ? "bg-neutral-900 text-white hover:bg-neutral-800"
                  : "cursor-not-allowed bg-neutral-100 text-neutral-400"
              }`}
            >
              {isGenerating ? "Generating…" : "Generate Plan"}
            </button>
          )}

          {showPostGenerationActions && (
            <>
              <button
                type="button"
                onClick={() => setCalculationOpen(true)}
                className="rounded-xl border border-neutral-200 bg-white px-4 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-50"
              >
                Calculation
              </button>
            </>
          )}
          </div>
        </div>

        <div className="shrink-0 flex items-center">
          <StaggeredMenu
            position="right"
            isFixed={false}
            isAuthenticated={isAuthenticated}
            open={menuOpen}
            onOpenChange={setMenuOpen}
            hideHeader={true}
            closeOnClickAway={true}
            onMenuClose={() => setMenuOpen(false)}
            trigger={
              <button
                type="button"
                className="flex h-9 w-9 items-center justify-center rounded-lg text-neutral-600 transition-colors hover:bg-neutral-100 hover:text-neutral-900"
                aria-label="Open menu"
              >
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              </button>
            }
            socialItems={[
              { label: "Twitter", link: "#", icon: <Twitter size={20} style={{ display: "block" }} /> },
              { label: "LinkedIn", link: "#", icon: <Linkedin size={20} style={{ display: "block" }} /> },
              { label: "Instagram", link: "#", icon: <Instagram size={20} style={{ display: "block" }} /> },
            ]}
            displaySocials={true}
            displayItemNumbering={false}
            colors={["#ff9c63", "#ff5900"]}
          />
        </div>
      </header>

      {isInputsPanelOpen && (
        <>
          <div
            className="fixed inset-0 z-[58] bg-neutral-900/25 backdrop-blur-sm"
            aria-hidden
            onClick={toggleInputsPanel}
          />
          <aside className="fixed right-0 top-0 z-[60] h-full w-full max-w-md overflow-hidden border-l border-neutral-200 bg-white shadow-2xl">
            <div className="flex h-14 items-center justify-between border-b border-neutral-200 px-6">
              <h2 className="text-lg font-semibold tracking-tight text-neutral-900">
                Development Inputs
              </h2>
              <button
                type="button"
                onClick={toggleInputsPanel}
                className="rounded-full p-2 text-neutral-500 transition-colors hover:bg-neutral-100 hover:text-neutral-800"
                aria-label="Close inputs"
              >
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="h-[calc(100%-3.5rem)] overflow-y-auto bg-neutral-50 px-5 py-5">
              <DevelopmentInputs key={selectedPlotId ?? "none"} />
            </div>
          </aside>
        </>
      )}

      <CalculationModal
        open={calculationOpen}
        onClose={() => setCalculationOpen(false)}
      />
    </>
  );
}
