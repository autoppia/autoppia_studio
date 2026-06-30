import { useEffect, useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faCheck, faPalette, faRotateLeft } from "@fortawesome/free-solid-svg-icons";
import {
  applyThemeSettings,
  DEFAULT_THEME_SETTINGS,
  FONT_OPTIONS,
  loadThemeSettings,
  MONO_FONT_OPTIONS,
  resetThemeSettings,
  saveThemeSettings,
  StudioThemeSettings,
  THEME_PRESETS,
} from "../../utils/theme-customizer";

function ColorField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const [draft, setDraft] = useState(value);

  useEffect(() => {
    setDraft(value);
  }, [value]);

  const handleTextChange = (next: string) => {
    setDraft(next);
    if (/^#[0-9a-fA-F]{6}$/.test(next) || /^#[0-9a-fA-F]{3}$/.test(next)) {
      onChange(next);
    }
  };

  return (
    <label className="ck-theme-field">
      <span>{label}</span>
      <span className="ck-theme-color-row">
        <input type="color" value={value} onChange={(event) => onChange(event.target.value)} aria-label={label} />
        <input value={draft} onChange={(event) => handleTextChange(event.target.value)} onBlur={() => setDraft(value)} spellCheck={false} />
      </span>
    </label>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<{ label: string; value: string }>;
  onChange: (value: string) => void;
}) {
  return (
    <label className="ck-theme-field">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function ThemeCustomizer() {
  const [open, setOpen] = useState(false);
  const [settings, setSettings] = useState<StudioThemeSettings>(() => loadThemeSettings());

  useEffect(() => {
    const applied = applyThemeSettings(settings);
    saveThemeSettings(applied);
  }, [settings]);

  const patch = (update: Partial<StudioThemeSettings>) => {
    setSettings((current) => ({ ...current, ...update }));
  };

  const reset = () => {
    setSettings(resetThemeSettings());
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex h-9 w-9 flex-none items-center justify-center rounded-xl border border-[color:var(--accent-line)] bg-[color:var(--accent-soft)] text-[color:var(--accent)] transition-colors hover:bg-[color:var(--accent)] hover:text-[color:var(--on-accent)]"
        title="Customize theme"
        aria-label="Customize theme"
      >
        <FontAwesomeIcon icon={faPalette} className="text-[13px]" />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-[80]" onClick={() => setOpen(false)} />
          <div className="ck-theme-popover">
            <div className="ck-theme-head">
              <div>
                <p>Theme</p>
                <span>Live style variables</span>
              </div>
              <button type="button" onClick={reset} title="Reset theme" aria-label="Reset theme">
                <FontAwesomeIcon icon={faRotateLeft} />
              </button>
            </div>

            <div className="ck-theme-preview" style={{ background: `linear-gradient(135deg, ${settings.accent}, ${settings.primary} 52%, ${settings.secondary})` }}>
              <span>Primary</span>
              <strong>{settings.primary}</strong>
            </div>

            <div className="ck-theme-presets">
              {THEME_PRESETS.map((preset) => {
                const selected =
                  preset.settings.primary === settings.primary &&
                  preset.settings.secondary === settings.secondary &&
                  preset.settings.accent === settings.accent &&
                  preset.settings.fontFamily === settings.fontFamily &&
                  preset.settings.monoFont === settings.monoFont &&
                  preset.settings.radius === settings.radius;
                return (
                  <button key={preset.name} type="button" onClick={() => setSettings(preset.settings)} className={selected ? "is-active" : ""}>
                    <span style={{ background: `linear-gradient(135deg, ${preset.settings.accent}, ${preset.settings.primary}, ${preset.settings.secondary})` }} />
                    {preset.name}
                    {selected && <FontAwesomeIcon icon={faCheck} />}
                  </button>
                );
              })}
            </div>

            <div className="ck-theme-grid">
              <ColorField label="Primary" value={settings.primary} onChange={(primary) => patch({ primary })} />
              <ColorField label="Secondary" value={settings.secondary} onChange={(secondary) => patch({ secondary })} />
              <ColorField label="Accent" value={settings.accent} onChange={(accent) => patch({ accent })} />
              <SelectField label="Font" value={settings.fontFamily} options={FONT_OPTIONS} onChange={(fontFamily) => patch({ fontFamily })} />
              <SelectField label="Mono" value={settings.monoFont} options={MONO_FONT_OPTIONS} onChange={(monoFont) => patch({ monoFont })} />
              <label className="ck-theme-field">
                <span>Radius</span>
                <input type="range" min="6" max="22" value={settings.radius} onChange={(event) => patch({ radius: Number(event.target.value) })} />
              </label>
            </div>

            <button type="button" className="ck-theme-reset" onClick={() => setSettings(DEFAULT_THEME_SETTINGS)}>
              Restore Studio default
            </button>
          </div>
        </>
      )}
    </div>
  );
}
