// Subscription plan definitions and local persistence.
//
// Billing is not wired to a payment backend yet (see the Credit/Invoices tabs,
// which show "coming soon"), so the selected plan lives in localStorage and is
// broadcast via a window event so the sidebar and settings stay in sync.

export type PlanId = "free" | "pro" | "max";

export interface Plan {
  id: PlanId;
  name: string;
  price: string;
  priceSuffix: string;
  tagline: string;
  features: string[];
  highlight?: boolean;
}

export const PLANS: Plan[] = [
  {
    id: "free",
    name: "Free",
    price: "$0",
    priceSuffix: "/month",
    tagline: "Try Automata and explore what your agents can do.",
    features: [
      "Access to core agents and connectors",
      "Limited daily sessions",
      "Community support",
    ],
  },
  {
    id: "pro",
    name: "Pro",
    price: "$20",
    priceSuffix: "/month",
    tagline: "For individuals running automations every day.",
    highlight: true,
    features: [
      "Everything in Free",
      "Much higher usage limits",
      "Priority session scheduling",
      "Email support",
    ],
  },
  {
    id: "max",
    name: "Max",
    price: "$100",
    priceSuffix: "/month",
    tagline: "Maximum throughput for power users and teams.",
    features: [
      "Everything in Pro",
      "Highest usage limits",
      "Dedicated runtime throughput",
      "Priority support",
    ],
  },
];

export const PLAN_STORAGE_KEY = "automata.plan";
export const PLAN_CHANGED_EVENT = "automata-plan-changed";

export function getStoredPlan(): PlanId {
  if (typeof window === "undefined") return "free";
  try {
    const stored = window.localStorage.getItem(PLAN_STORAGE_KEY) as PlanId | null;
    if (stored && PLANS.some((plan) => plan.id === stored)) return stored;
  } catch {
    // ignore storage failures
  }
  return "free";
}

export function setStoredPlan(planId: PlanId): void {
  try {
    window.localStorage.setItem(PLAN_STORAGE_KEY, planId);
  } catch {
    // ignore storage failures
  }
  try {
    window.dispatchEvent(new CustomEvent(PLAN_CHANGED_EVENT, { detail: { planId } }));
  } catch {
    // ignore event failures
  }
}

export function planById(planId: PlanId): Plan {
  return PLANS.find((plan) => plan.id === planId) || PLANS[0];
}
