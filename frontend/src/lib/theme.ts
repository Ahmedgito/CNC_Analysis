"use client";

import { useSyncExternalStore } from "react";

/**
 * Light / dark / system theme without a dependency. The no-flash script in the root layout sets
 * the `dark` class before first paint; these helpers keep it in sync afterwards.
 */
export type ThemeMode = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "theme";

/** Inlined into <head> by the root layout. Runs before paint, so there is no theme flash. */
export const THEME_SCRIPT = `(function(){try{var m=localStorage.getItem("${STORAGE_KEY}")||"system";var d=m==="dark"||(m==="system"&&matchMedia("(prefers-color-scheme: dark)").matches);var e=document.documentElement;e.classList.toggle("dark",d);e.style.colorScheme=d?"dark":"light";e.dataset.themeMode=m}catch(_){}})();`;

function systemPrefersDark() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export function readMode(): ThemeMode {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : "system";
  } catch {
    return "system";
  }
}

export function applyMode(mode: ThemeMode) {
  const dark = mode === "dark" || (mode === "system" && systemPrefersDark());
  const root = document.documentElement;
  root.classList.toggle("dark", dark);
  root.style.colorScheme = dark ? "dark" : "light";
  root.dataset.themeMode = mode;
  try {
    if (mode === "system") window.localStorage.removeItem(STORAGE_KEY);
    else window.localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    /* storage blocked: the class change still applies for this page view */
  }
}

function subscribe(onChange: () => void) {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["class", "data-theme-mode"],
  });
  // Follow the OS while the user has not picked a theme explicitly.
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  const onSystem = () => {
    if (readMode() === "system") applyMode("system");
  };
  media.addEventListener("change", onSystem);
  return () => {
    observer.disconnect();
    media.removeEventListener("change", onSystem);
  };
}

/** The theme actually showing. Server render assumes dark, the default look of the app. */
export function useResolvedTheme(): ResolvedTheme {
  return useSyncExternalStore(
    subscribe,
    () => (document.documentElement.classList.contains("dark") ? "dark" : "light"),
    () => "dark",
  );
}

/** The user's choice (light, dark or follow the system). */
export function useThemeMode(): ThemeMode {
  return useSyncExternalStore(
    subscribe,
    () => (document.documentElement.dataset.themeMode as ThemeMode | undefined) ?? "system",
    () => "system",
  );
}

/** True only after hydration; for UI that must not render on the server. */
export function useMounted() {
  return useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
}
