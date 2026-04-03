"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { plannerProfiles } from "../../../../../modules/planner/config/plannerProfiles";
import PlannerWorkspace from "../../../../../modules/planner/workspace/PlannerWorkspace";
import { useNotificationStore } from "../../../../../state/notificationStore";

export default function PlannerWorkspacePage() {
  const params = useParams();
  const { addToast } = useNotificationStore();
  const [hasLoaded, setHasLoaded] = useState(false);
  
  const rawMode = params?.mode;
  const modeParam = typeof rawMode === "string" ? rawMode : rawMode?.[0];
  const profile = modeParam ? plannerProfiles[modeParam] : undefined;

  useEffect(() => {
    if (profile && !hasLoaded) {
      addToast({
        title: "Workspace Loaded",
        message: `Planner mode loaded: ${profile.name}`,
        type: "success"
      });
      setHasLoaded(true);
    } else if (!profile && modeParam && !hasLoaded) {
      addToast({
        title: "Error",
        message: "Invalid planner mode",
        type: "error"
      });
      setHasLoaded(true);
    }
  }, [profile, modeParam, hasLoaded, addToast]);

  if (!profile) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-slate-950 text-slate-400 font-sans">
        <div className="text-center border border-slate-800 bg-slate-900/50 p-8 rounded-xl max-w-md">
          <h2 className="text-xl font-bold text-slate-200 mb-2">Planner Mode Not Found</h2>
          <p className="text-sm">The requested planner configuration <span className="text-slate-300 font-mono bg-slate-800 px-1 py-0.5 rounded">[{modeParam}]</span> does not exist or has not been implemented yet.</p>
        </div>
      </div>
    );
  }

  return <PlannerWorkspace profile={profile} />;
}
