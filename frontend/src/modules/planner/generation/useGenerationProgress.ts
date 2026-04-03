"use client";

import { useState, useEffect, useRef } from "react";

const SIMULATED_INCREMENT = 1.5;
const SIMULATED_INTERVAL_MS = 500;
const SIMULATED_CAP = 92;

function stageLabelFromProgress(progress: number): string {
  if (progress <= 0)  return "Submitting job…";
  if (progress < 25)  return "Computing envelope…";
  if (progress < 45)  return "Building zones…";
  if (progress < 70)  return "Computing layout…";
  if (progress < 100) return "Finalizing…";
  return "Complete";
}

/**
 * Returns display progress and stage label for the generation loader.
 * Simulates smooth progress while the backend reports ≤10% (its only
 * real update). Simulation resets only when a fresh generation starts
 * (isRunning transitions false → true).
 */
export function useGenerationProgress(
  backendProgress: number | null,
  status: "pending" | "running" | "completed" | "failed" | undefined,
) {
  const [simulated, setSimulated] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const wasRunningRef = useRef(false);

  const isRunning = status === "running" || status === "pending";

  useEffect(() => {
    if (!isRunning) {
      // Stop simulation when job ends
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      wasRunningRef.current = false;
      return;
    }

    // Reset only on fresh start (false → true transition)
    if (!wasRunningRef.current) {
      wasRunningRef.current = true;
      setSimulated(5);
    }

    // Start simulation if not already running
    if (intervalRef.current) return;
    intervalRef.current = setInterval(() => {
      setSimulated((p) => Math.min(SIMULATED_CAP, p + SIMULATED_INCREMENT));
    }, SIMULATED_INTERVAL_MS);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [isRunning]);

  // Use the higher of simulated vs backend (backend may report >10% eventually)
  const displayProgress: number | null =
    status === "completed" || status === "failed"
      ? 100
      : isRunning
        ? Math.max(simulated, backendProgress ?? 0)
        : backendProgress;

  const stageLabel =
    displayProgress !== null
      ? stageLabelFromProgress(displayProgress)
      : "Submitting job…";

  return { displayProgress, stageLabel };
}
