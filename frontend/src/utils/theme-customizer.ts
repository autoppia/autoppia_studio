export interface StudioThemeSettings {
  primary: string;
  secondary: string;
  accent: string;
  fontFamily: string;
  monoFont: string;
  radius: number;
}

export const THEME_STORAGE_KEY = "autoppia_studio_theme_settings";

export const DEFAULT_THEME_SETTINGS: StudioThemeSettings = {
  primary: "#FB923C",
  secondary: "#FB7185",
  accent: "#FCD34D",
  fontFamily: "Inter",
  monoFont: "JetBrains Mono",
  radius: 13,
};

export const THEME_PRESETS: Array<{ name: string; settings: StudioThemeSettings }> = [
  { name: "Studio", settings: DEFAULT_THEME_SETTINGS },
  {
    name: "Cyan",
    settings: { primary: "#22D3EE", secondary: "#3B82F6", accent: "#A78BFA", fontFamily: "Inter", monoFont: "JetBrains Mono", radius: 12 },
  },
  {
    name: "Emerald",
    settings: { primary: "#34D399", secondary: "#10B981", accent: "#FBBF24", fontFamily: "Inter", monoFont: "JetBrains Mono", radius: 10 },
  },
  {
    name: "Rose",
    settings: { primary: "#FB7185", secondary: "#F472B6", accent: "#FCD34D", fontFamily: "Inter", monoFont: "JetBrains Mono", radius: 16 },
  },
];

export const FONT_OPTIONS = [
  { label: "Inter", value: "Inter" },
  { label: "System", value: "System" },
  { label: "SF Pro", value: "SF Pro" },
  { label: "Segoe UI", value: "Segoe UI" },
  { label: "Roboto", value: "Roboto" },
  { label: "Helvetica", value: "Helvetica" },
  { label: "Aptos", value: "Aptos" },
  { label: "IBM Plex Sans", value: "IBM Plex Sans" },
  { label: "Manrope", value: "Manrope" },
  { label: "Satoshi", value: "Satoshi" },
  { label: "DM Sans", value: "DM Sans" },
  { label: "Geist", value: "Geist" },
  { label: "Nunito Sans", value: "Nunito Sans" },
  { label: "Serif", value: "Serif" },
  { label: "Georgia", value: "Georgia" },
  { label: "Mono", value: "Mono" },
];

export const MONO_FONT_OPTIONS = [
  { label: "JetBrains Mono", value: "JetBrains Mono" },
  { label: "Geist Mono", value: "Geist Mono" },
  { label: "IBM Plex Mono", value: "IBM Plex Mono" },
  { label: "Roboto Mono", value: "Roboto Mono" },
  { label: "Fira Code", value: "Fira Code" },
  { label: "Cascadia Code", value: "Cascadia Code" },
  { label: "SF Mono", value: "SF Mono" },
  { label: "System Mono", value: "System Mono" },
];

function clampRadius(value: unknown): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return DEFAULT_THEME_SETTINGS.radius;
  return Math.max(6, Math.min(22, Math.round(parsed)));
}

function normalizeHex(value: unknown, fallback: string): string {
  const raw = String(value || "").trim();
  if (/^#[0-9a-fA-F]{6}$/.test(raw)) return raw.toUpperCase();
  if (/^#[0-9a-fA-F]{3}$/.test(raw)) {
    const r = raw.charAt(1);
    const g = raw.charAt(2);
    const b = raw.charAt(3);
    return `#${r}${r}${g}${g}${b}${b}`.toUpperCase();
  }
  return fallback;
}

function fontStack(name: string): string {
  if (name === "Mono") return '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
  if (name === "Georgia") return 'Georgia, Cambria, "Times New Roman", Times, serif';
  if (name === "Serif") return 'Georgia, Cambria, "Times New Roman", Times, serif';
  if (name === "SF Pro") return '"SF Pro Display", "SF Pro Text", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
  if (name === "Segoe UI") return '"Segoe UI", Inter, ui-sans-serif, system-ui, sans-serif';
  if (name === "Roboto") return 'Roboto, Inter, ui-sans-serif, system-ui, sans-serif';
  if (name === "Helvetica") return '"Helvetica Neue", Helvetica, Arial, Inter, ui-sans-serif, sans-serif';
  if (name === "Aptos") return 'Aptos, "Aptos Display", Calibri, Inter, ui-sans-serif, sans-serif';
  if (name === "IBM Plex Sans") return '"IBM Plex Sans", Inter, ui-sans-serif, system-ui, sans-serif';
  if (name === "Manrope") return 'Manrope, Inter, ui-sans-serif, system-ui, sans-serif';
  if (name === "Satoshi") return 'Satoshi, Inter, ui-sans-serif, system-ui, sans-serif';
  if (name === "DM Sans") return '"DM Sans", Inter, ui-sans-serif, system-ui, sans-serif';
  if (name === "Geist") return 'Geist, Inter, ui-sans-serif, system-ui, sans-serif';
  if (name === "Nunito Sans") return '"Nunito Sans", Inter, ui-sans-serif, system-ui, sans-serif';
  if (name === "System") return 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
  return 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
}

function monoStack(name: string): string {
  if (name === "Geist Mono") return '"Geist Mono", "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
  if (name === "IBM Plex Mono") return '"IBM Plex Mono", "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
  if (name === "Roboto Mono") return '"Roboto Mono", "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
  if (name === "Fira Code") return '"Fira Code", "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
  if (name === "Cascadia Code") return '"Cascadia Code", "Cascadia Mono", "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
  if (name === "SF Mono") return '"SF Mono", SFMono-Regular, Menlo, Consolas, monospace';
  if (name === "System Mono") return 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
  return '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
}

export function hexToRgbParts(hex: string): string {
  const clean = normalizeHex(hex, DEFAULT_THEME_SETTINGS.primary).slice(1);
  const value = Number.parseInt(clean, 16);
  return `${(value >> 16) & 255} ${(value >> 8) & 255} ${value & 255}`;
}

export function normalizeThemeSettings(settings: Partial<StudioThemeSettings> | null | undefined): StudioThemeSettings {
  return {
    primary: normalizeHex(settings?.primary, DEFAULT_THEME_SETTINGS.primary),
    secondary: normalizeHex(settings?.secondary, DEFAULT_THEME_SETTINGS.secondary),
    accent: normalizeHex(settings?.accent, DEFAULT_THEME_SETTINGS.accent),
    fontFamily: FONT_OPTIONS.some((item) => item.value === settings?.fontFamily) ? String(settings?.fontFamily) : DEFAULT_THEME_SETTINGS.fontFamily,
    monoFont: MONO_FONT_OPTIONS.some((item) => item.value === settings?.monoFont) ? String(settings?.monoFont) : DEFAULT_THEME_SETTINGS.monoFont,
    radius: clampRadius(settings?.radius),
  };
}

export function loadThemeSettings(): StudioThemeSettings {
  try {
    const raw = localStorage.getItem(THEME_STORAGE_KEY);
    return normalizeThemeSettings(raw ? JSON.parse(raw) : null);
  } catch {
    return DEFAULT_THEME_SETTINGS;
  }
}

export function saveThemeSettings(settings: StudioThemeSettings): void {
  localStorage.setItem(THEME_STORAGE_KEY, JSON.stringify(normalizeThemeSettings(settings)));
}

export function resetThemeSettings(): StudioThemeSettings {
  localStorage.removeItem(THEME_STORAGE_KEY);
  applyThemeSettings(DEFAULT_THEME_SETTINGS);
  return DEFAULT_THEME_SETTINGS;
}

export function applyThemeSettings(rawSettings: Partial<StudioThemeSettings>): StudioThemeSettings {
  const settings = normalizeThemeSettings(rawSettings);
  const root = document.documentElement;
  const primaryRgb = hexToRgbParts(settings.primary);
  const secondaryRgb = hexToRgbParts(settings.secondary);
  const accentRgb = hexToRgbParts(settings.accent);
  root.style.setProperty("--color-primary", primaryRgb);
  root.style.setProperty("--color-primary-strong", secondaryRgb);
  root.style.setProperty("--color-accent-2", accentRgb);
  root.style.setProperty("--accent", settings.primary);
  root.style.setProperty("--accent-2", settings.accent);
  root.style.setProperty("--accent-soft", `rgb(${primaryRgb} / 0.13)`);
  root.style.setProperty("--accent-line", `rgb(${primaryRgb} / 0.38)`);
  root.style.setProperty("--brand-bg", `linear-gradient(135deg, ${settings.accent}, ${settings.primary} 52%, ${settings.secondary})`);
  root.style.setProperty("--glow", `0 0 20px rgb(${primaryRgb} / 0.22)`);
  root.style.setProperty("--glow-lg", `0 0 40px rgb(${secondaryRgb} / 0.26)`);
  root.style.setProperty("--sans", fontStack(settings.fontFamily));
  root.style.setProperty("--display", fontStack(settings.fontFamily));
  root.style.setProperty("--mono", monoStack(settings.monoFont));
  root.style.setProperty("--radius", `${settings.radius}px`);
  root.style.setProperty("--radius-sm", `${Math.max(6, settings.radius - 4)}px`);
  root.style.setProperty("--radius-lg", `${settings.radius + 5}px`);
  root.style.setProperty("--focus-ring", `rgb(${primaryRgb} / 0.7)`);
  root.style.setProperty("--selection-bg", `rgb(${primaryRgb} / 0.3)`);
  return settings;
}
