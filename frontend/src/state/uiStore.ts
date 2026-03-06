import { create } from "zustand";

type UiState = {
  sidebarCollapsed: boolean;
  isLoadingOverlay: boolean;
  theme?: "light" | "dark";
};

type UiActions = {
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setLoadingOverlay: (visible: boolean) => void;
  setTheme: (theme: UiState["theme"]) => void;
};

export type UiStore = UiState & UiActions;

export const useUiStore = create<UiStore>((set) => ({
  sidebarCollapsed: false,
  isLoadingOverlay: false,
  theme: undefined,

  toggleSidebar: () =>
    set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),

  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),

  setLoadingOverlay: (visible) => set({ isLoadingOverlay: visible }),

  setTheme: (theme) => set({ theme }),
}));

