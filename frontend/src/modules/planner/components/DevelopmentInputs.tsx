"use client";

import { useEffect } from "react";
import { useForm, Controller } from "react-hook-form";
import type { PlannerInputs } from "@/types/plannerInputs";
import { usePlannerStore } from "@/state/plannerStore";

const UNIT_OPTIONS = ["1BHK", "2BHK", "3BHK", "4BHK", "5BHK"] as const;

export function DevelopmentInputs() {
  const inputs = usePlannerStore((state) => state.inputs);
  const setInputs = usePlannerStore((state) => state.setInputs);

  const { register, control, watch } = useForm<PlannerInputs>({
    defaultValues: inputs,
  });

  // Push changes back into the store in real time.
  useEffect(() => {
    const subscription = watch((value) => {
      setInputs(value as Partial<PlannerInputs>);
    });
    return () => subscription.unsubscribe();
  }, [watch, setInputs]);

  return (
    <div className="space-y-5 rounded-xl bg-white p-5 text-sm shadow-sm">
      <h2 className="text-sm font-semibold text-neutral-900">
        Development inputs
      </h2>

      {/* Unit mix */}
      <section className="space-y-2">
        <h3 className="text-xs font-medium tracking-wide text-neutral-700">
          Unit mix
        </h3>
        <div className="grid grid-cols-2 gap-2 text-xs text-neutral-700">
          {UNIT_OPTIONS.map((label) => (
            <label
              key={label}
              className="inline-flex items-center gap-2 rounded-md border border-neutral-200 bg-neutral-50 px-2 py-1.5"
            >
              <input
                type="checkbox"
                value={label}
                className="h-3 w-3 rounded border-neutral-300 text-neutral-900"
                {...register("unitMix")}
              />
              <span>{label}</span>
            </label>
          ))}
        </div>
      </section>

      {/* Development segment */}
      <section className="space-y-2">
        <h3 className="text-xs font-medium tracking-wide text-neutral-700">
          Development segment
        </h3>
        <div className="grid grid-cols-2 gap-2 text-xs text-neutral-700">
          {["budget", "mid", "premium", "luxury"].map((value) => (
            <label
              key={value}
              className="inline-flex items-center gap-2 rounded-md border border-neutral-200 bg-neutral-50 px-2 py-1.5"
            >
              <input
                type="radio"
                value={value}
                className="h-3 w-3 text-blue-600"
                {...register("segment")}
              />
              <span className="capitalize">{value}</span>
            </label>
          ))}
        </div>
      </section>

      {/* Tower count */}
      <section className="space-y-2">
        <h3 className="text-xs font-medium tracking-wide text-neutral-700">
          Tower configuration
        </h3>
        <div className="text-xs text-neutral-700">
          <Controller
            name="towerCount"
            control={control}
            render={({ field }) => (
              <select
                {...field}
                value={field.value === "auto" ? "auto" : String(field.value)}
                onChange={(e) => {
                  const v =
                    e.target.value === "auto"
                      ? "auto"
                      : Number(e.target.value);
                  field.onChange(v);
                }}
                className="w-full rounded-md border border-neutral-300 bg-white px-2 py-1.5 text-xs text-neutral-900"
              >
                <option value="auto">Auto</option>
                <option value="1">1</option>
                <option value="2">2</option>
                <option value="3">3</option>
                <option value="4">4</option>
              </select>
            )}
          />
        </div>
      </section>

      {/* Preferred floors */}
      <section className="space-y-2">
        <h3 className="text-xs font-medium tracking-wide text-neutral-700">
          Preferred floors (optional)
        </h3>
        <div className="grid grid-cols-2 gap-3 text-xs text-neutral-700">
          <div className="space-y-1">
            <label className="block text-[11px] text-neutral-500">
              Min floors
            </label>
            <input
              type="number"
              min={0}
              {...register("preferredFloors.min", { valueAsNumber: true })}
              className="w-full rounded-md border border-neutral-300 px-2 py-1 text-xs text-neutral-900"
            />
          </div>
          <div className="space-y-1">
            <label className="block text-[11px] text-neutral-500">
              Max floors
            </label>
            <input
              type="number"
              min={0}
              {...register("preferredFloors.max", { valueAsNumber: true })}
              className="w-full rounded-md border border-neutral-300 px-2 py-1 text-xs text-neutral-900"
            />
          </div>
        </div>
      </section>

      {/* Design preferences */}
      <section className="space-y-2">
        <h3 className="text-xs font-medium tracking-wide text-neutral-700">
          Design preferences
        </h3>
        <label className="inline-flex items-center gap-2 text-xs text-neutral-700">
          <input
            type="checkbox"
            className="h-3 w-3 rounded border-neutral-300 text-blue-600"
            {...register("vastu")}
          />
          <span>Enable Vastu optimisation</span>
        </label>
      </section>
    </div>
  );
}

