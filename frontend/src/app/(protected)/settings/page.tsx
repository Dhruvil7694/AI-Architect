"use client";

import { useState } from "react";

export default function SettingsPage() {
  const [notifications, setNotifications] = useState(true);
  const [autoSave, setAutoSave] = useState(true);

  return (
    <section className="max-w-3xl space-y-6">
      <header>
        <h2 className="text-2xl font-semibold text-neutral-900">Settings</h2>
        <p className="text-sm text-neutral-600 mt-1">
          Configure your application preferences
        </p>
      </header>

      {/* General Settings */}
      <div className="rounded-lg border border-neutral-200 bg-white p-6">
        <h3 className="text-sm font-semibold text-neutral-900 mb-4">General</h3>
        <div className="space-y-4">
          <div className="flex items-center justify-between py-3 border-b border-neutral-100 last:border-0">
            <div>
              <p className="text-sm font-medium text-neutral-900">Notifications</p>
              <p className="text-xs text-neutral-600 mt-0.5">Receive updates about your projects</p>
            </div>
            <button
              onClick={() => setNotifications(!notifications)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                notifications ? "bg-neutral-900" : "bg-neutral-300"
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  notifications ? "translate-x-6" : "translate-x-1"
                }`}
              />
            </button>
          </div>

          <div className="flex items-center justify-between py-3">
            <div>
              <p className="text-sm font-medium text-neutral-900">Auto-save</p>
              <p className="text-xs text-neutral-600 mt-0.5">Automatically save your work</p>
            </div>
            <button
              onClick={() => setAutoSave(!autoSave)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                autoSave ? "bg-neutral-900" : "bg-neutral-300"
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  autoSave ? "translate-x-6" : "translate-x-1"
                }`}
              />
            </button>
          </div>
        </div>
      </div>

      {/* Appearance */}
      <div className="rounded-lg border border-neutral-200 bg-white p-6">
        <h3 className="text-sm font-semibold text-neutral-900 mb-4">Appearance</h3>
        <div>
          <label className="block text-sm font-medium text-neutral-900 mb-3">
            Theme
          </label>
          <div className="grid grid-cols-3 gap-3">
            {["Light", "Dark", "System"].map((theme) => (
              <button
                key={theme}
                className="rounded-md border border-neutral-300 py-3 text-sm font-medium text-neutral-700 transition-colors hover:border-neutral-900 hover:bg-neutral-50"
              >
                {theme}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Danger Zone */}
      <div className="rounded-lg border border-red-200 bg-red-50 p-6">
        <h3 className="text-sm font-semibold text-red-900 mb-2">Danger Zone</h3>
        <p className="text-sm text-red-700 mb-4">
          Irreversible actions that affect your account
        </p>
        <button className="rounded-md border border-red-300 bg-white px-4 py-2 text-sm font-medium text-red-700 transition-colors hover:bg-red-100">
          Delete Account
        </button>
      </div>
    </section>
  );
}
