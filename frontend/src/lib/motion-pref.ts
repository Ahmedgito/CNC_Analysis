"use client";

import { useSyncExternalStore } from "react";

/**
 * In-app motion preference. "system" follows the OS reduced-motion setting (the accessible
 * default); "full" and "reduced" are explicit user choices that override it.
 */
export type MotionPref = "system" | "full" | "reduced";

const KEY = "motion";
const EVENT = "motion-pref-change";

function read(): MotionPref {
  try {
    const v = window.localStorage.getItem(KEY);
    return v === "full" || v === "reduced" ? v : "system";
  } catch {
    return "system";
  }
}

export function setMotionPref(pref: MotionPref) {
  try {
    if (pref === "system") window.localStorage.removeItem(KEY);
    else window.localStorage.setItem(KEY, pref);
  } catch {
    /* storage blocked: preference lasts for this page view only */
  }
  window.dispatchEvent(new Event(EVENT));
}

function subscribe(onChange: () => void) {
  window.addEventListener(EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

export function useMotionPref(): MotionPref {
  return useSyncExternalStore(subscribe, read, () => "system");
}

function subscribeOs(onChange: () => void) {
  const media = window.matchMedia("(prefers-reduced-motion: reduce)");
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}

/** Whether the operating system asks for reduced motion. */
export function useOsReducedMotion() {
  return useSyncExternalStore(
    subscribeOs,
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => false,
  );
}
