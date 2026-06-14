// lib/onboarding-store.ts
// Lightweight reactive store backed by localStorage.
// No external state library required.

import { useState, useEffect } from "react";

// ─── Domain types ─────────────────────────────────────────────────────────────

export type HouseholdMember = {
  id: string;
  name: string;
  role: "owner" | "partner" | "child" | "parent" | "grandparent" | "other";
  ageGroup: "baby" | "child" | "teen" | "adult" | "senior";
  emoji: string;
};

export type Priority =
  | "energy_saving"
  | "security"
  | "family_health"
  | "comfort"
  | "convenience"
  | "privacy";

export type Device = {
  id: string;
  name: string;
  type:
    | "ac"
    | "tv"
    | "water_motor"
    | "geyser"
    | "fridge"
    | "washing_machine"
    | "pressure_cooker"
    | "lights"
    | "security_camera"
    | "doorbell"
    | "other";
  room: string;
  brand?: string;
};

export type CareNeed = {
  memberId: string;
  needs: string[];
};

export type Routine = {
  id: string;
  label: string;
  time?: string;
  selected: boolean;
};

export interface OnboardingState {
  currentStep: number;
  householdId: string | null;
  householdName: string;
  householdCity: string;
  members: HouseholdMember[];
  careNeeds: CareNeed[];
  priorities: Priority[];
  devices: Device[];
  routines: Routine[];
  completed: boolean;
}

// ─── Default routines ─────────────────────────────────────────────────────────

const DEFAULT_ROUTINES: Routine[] = [
  { id: "morning_tea",      label: "Morning tea / chai",        time: "",  selected: false },
  { id: "school_run",       label: "School drop & pickup",      time: "",  selected: false },
  { id: "medicine_morning", label: "Morning medicines",         time: "",  selected: false },
  { id: "work_from_home",   label: "Work from home",            time: "",  selected: false },
  { id: "afternoon_nap",    label: "Afternoon rest / nap",      time: "",  selected: false },
  { id: "evening_walk",     label: "Evening walk",              time: "",  selected: false },
  { id: "dinner_together",  label: "Family dinner together",    time: "",  selected: false },
  { id: "medicine_night",   label: "Night medicines",           time: "",  selected: false },
  { id: "movie_night",      label: "Movie / TV night",          time: "",  selected: false },
  { id: "prayer_time",      label: "Prayer / pooja time",       time: "",  selected: false },
];

const INITIAL_STATE: OnboardingState = {
  currentStep: 0,
  householdId: null,
  householdName: "",
  householdCity: "",
  members: [],
  careNeeds: [],
  priorities: [],
  devices: [],
  routines: DEFAULT_ROUTINES,
  completed: false,
};

// ─── Persistence ──────────────────────────────────────────────────────────────

const STORAGE_KEY = "saathi_onboarding_v1";

function load(): OnboardingState {
  if (typeof window === "undefined") return { ...INITIAL_STATE };
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...INITIAL_STATE };
    const parsed = JSON.parse(raw) as Partial<OnboardingState>;
    // Merge with defaults so new fields added later don't break old saves
    return {
      ...INITIAL_STATE,
      ...parsed,
      // Always ensure routines list is complete (merge saved selections in)
      routines: DEFAULT_ROUTINES.map((r) => {
        const saved = parsed.routines?.find((sr) => sr.id === r.id);
        return saved ? { ...r, selected: saved.selected } : r;
      }),
    };
  } catch {
    return { ...INITIAL_STATE };
  }
}

function save(state: OnboardingState) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // quota exceeded — ignore
  }
}

// ─── Store ────────────────────────────────────────────────────────────────────

type Listener = (state: OnboardingState) => void;

class OnboardingStore {
  private _state: OnboardingState = load();
  private _listeners: Set<Listener> = new Set();

  // ── Read ──────────────────────────────────────────────────

  getState(): OnboardingState {
    return this._state;
  }

  subscribe(listener: Listener): () => void {
    this._listeners.add(listener);
    return () => this._listeners.delete(listener);
  }

  // ── Write ─────────────────────────────────────────────────

  private _set(partial: Partial<OnboardingState>) {
    this._state = { ...this._state, ...partial };
    save(this._state);
    this._listeners.forEach((fn) => fn(this._state));
  }

  // Navigation
  next() {
    this._set({ currentStep: Math.min(this._state.currentStep + 1, 8) });
  }

  back() {
    this._set({ currentStep: Math.max(this._state.currentStep - 1, 0) });
  }

  goTo(step: number) {
    this._set({ currentStep: Math.max(0, Math.min(step, 8)) });
  }

  reset() {
    this._state = { ...INITIAL_STATE };
    save(this._state);
    this._listeners.forEach((fn) => fn(this._state));
  }

  // Step 2 — household
  setHousehold(name: string, city: string) {
    this._set({ householdName: name, householdCity: city });
  }

  setHouseholdId(id: string) {
    this._set({ householdId: id });
  }

  // Step 3 — members
  addMember(member: HouseholdMember) {
    this._set({ members: [...this._state.members, member] });
  }

  removeMember(id: string) {
    this._set({ members: this._state.members.filter((m) => m.id !== id) });
  }

  // Step 4 — care needs
  updateCareNeed(memberId: string, needs: string[]) {
    const existing = this._state.careNeeds.filter((c) => c.memberId !== memberId);
    this._set({ careNeeds: needs.length > 0 ? [...existing, { memberId, needs }] : existing });
  }

  // Step 5 — priorities
  togglePriority(priority: Priority) {
    const current = this._state.priorities;
    const updated = current.includes(priority)
      ? current.filter((p) => p !== priority)
      : [...current, priority];
    this._set({ priorities: updated });
  }

  // Step 6 — devices
  addDevice(device: Device) {
    this._set({ devices: [...this._state.devices, device] });
  }

  removeDevice(id: string) {
    this._set({ devices: this._state.devices.filter((d) => d.id !== id) });
  }

  // Step 8 — routines
  toggleRoutine(id: string) {
    this._set({
      routines: this._state.routines.map((r) =>
        r.id === id ? { ...r, selected: !r.selected } : r
      ),
    });
  }

  updateRoutineTime(id: string, time: string) {
    this._set({
      routines: this._state.routines.map((r) =>
        r.id === id ? { ...r, time } : r
      ),
    });
  }

  // Step 8 complete
  complete() {
    this._set({ completed: true });
  }
}

// Singleton — shared across the app
export const onboardingStore = new OnboardingStore();

// ─── React hook ───────────────────────────────────────────────────────────────

export function useOnboardingStore(): OnboardingState {
  const [state, setState] = useState<OnboardingState>(() => onboardingStore.getState());

  useEffect(() => {
    // Sync with localStorage on mount (SSR→client hydration)
    setState(onboardingStore.getState());
    return onboardingStore.subscribe(setState);
  }, []);

  return state;
}
