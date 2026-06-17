import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faXmark,
  faWandMagicSparkles,
  faSpinner,
  faArrowRight,
  faChevronDown,
  faChevronRight,
  faTrash,
} from "@fortawesome/free-solid-svg-icons";
import { useToast } from "../common/toast";
import { SkillParameter } from "../../utils/types";
import { getApiUrl } from "../../utils/api-url";

const apiUrl = getApiUrl();

interface ActionEntry {
  action: string;
  args: Record<string, string>;
}

interface ConvertToSkillModalProps {
  onClose: () => void;
  userEmail: string;
  actionHistory?: any[];
  prompt?: string;
  initialUrl?: string;
  skillName?: string;
  skillGoal?: string;
  skillInstructions?: string;
  skillId?: string;
  initialActions?: any[];
  onSaved?: () => void;
}

function extractParamNames(text: string): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  const re = /\{\{(\w+)\}\}/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (!seen.has(m[1])) { seen.add(m[1]); result.push(m[1]); }
  }
  return result;
}

function applyParams(text: string, params: SkillParameter[]): string {
  return text.replace(/\{\{(\w+)\}\}/g, (match, name) => {
    const p = params.find((p) => p.name === name);
    return (p && p.defaultValue) ? p.defaultValue : match;
  });
}

function hasPlaceholder(text: string): boolean {
  return /\{\{\w+\}\}/.test(text);
}

function initActions(initialActions?: any[], actionHistory?: any[]): ActionEntry[] {
  const source = initialActions || (actionHistory || []).map((entry: any) => ({
    action: entry.tool_call?.name || "",
    args: entry.tool_call?.arguments || {},
  }));
  const filtered = source
    .filter((a: any) => a.action && !["browser.screenshot", "browser.wait"].includes(a.action))
    .map((a: any) => ({
      action: String(a.action),
      args: Object.fromEntries(
        Object.entries(a.args || {}).map(([k, v]) => [k, String(v)])
      ),
    }));

  return filtered;
}

export default function ConvertToSkillModal(props: ConvertToSkillModalProps) {
  const {
    onClose, actionHistory, prompt, skillName, skillGoal,
    skillInstructions, userEmail, skillId, initialActions, onSaved,
  } = props;

  const isEditMode = !!skillId;
  const navigate = useNavigate();
  const { showToast } = useToast();

  const initialInstructions = skillInstructions || prompt || "";

  const [saving, setSaving] = useState(false);
  const [name, setName] = useState(skillName || "");
  const [goal, setGoal] = useState(skillGoal || "");
  const [instructions, setInstructions] = useState(initialInstructions);
  const [parameters, setParameters] = useState<SkillParameter[]>(() => {
    const names = extractParamNames(initialInstructions);
    return names.map((n) => ({ name: n, description: "", defaultValue: "" }));
  });
  const [actions, setActions] = useState<ActionEntry[]>(() =>
    initActions(initialActions, actionHistory)
  );
  // Track which actions are expanded (collapsed by default)
  const [expandedActions, setExpandedActions] = useState<Set<number>>(new Set());

  const toggleAction = (i: number) => {
    setExpandedActions((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i); else next.add(i);
      return next;
    });
  };

  const handleInstructionsChange = (text: string) => {
    setInstructions(text);
    setParameters((prev) => {
      const names = extractParamNames(text);
      return names.map((n) => prev.find((p) => p.name === n) || { name: n, description: "", defaultValue: "" });
    });
  };

  const updateParam = (index: number, field: keyof SkillParameter, value: string) => {
    setParameters((prev) =>
      prev.map((p, i) => (i === index ? { ...p, [field]: value } : p))
    );
  };

  const updateActionArg = (actionIndex: number, key: string, value: string) => {
    setActions((prev) =>
      prev.map((a, i) =>
        i === actionIndex ? { ...a, args: { ...a.args, [key]: value } } : a
      )
    );
  };

  const deleteAction = (actionIndex: number) => {
    setActions((prev) => prev.filter((_, i) => i !== actionIndex));
    setExpandedActions((prev) => {
      const next = new Set<number>();
      prev.forEach((i) => {
        if (i < actionIndex) next.add(i);
        else if (i > actionIndex) next.add(i - 1);
      });
      return next;
    });
  };

  const handleSave = async () => {
    if (!name.trim() || !instructions.trim()) return;
    setSaving(true);
    try {
      const url = isEditMode ? `${apiUrl}/skills/${skillId}` : `${apiUrl}/skills`;
      const method = isEditMode ? "PUT" : "POST";
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: userEmail,
          name: name.trim(),
          goal: goal.trim(),
          instructions: instructions.trim(),
          parameters,
          actions,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      showToast(isEditMode ? "Skill updated!" : "Skill saved!", "success");
      onClose();
      if (onSaved) { onSaved(); } else { navigate("/skills"); }
    } catch (err) {
      console.error("Save skill failed:", err);
      showToast("Failed to save skill. Please try again.", "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="bg-white dark:bg-dark-surface rounded-2xl shadow-soft-lg border border-gray-200 dark:border-dark-border
        w-full max-w-2xl max-h-[90vh] flex flex-col">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-dark-border flex-shrink-0">
          <div className="flex items-center gap-2">
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-primary shadow-glow">
              <FontAwesomeIcon icon={faWandMagicSparkles} className="text-white text-xs" />
            </div>
            <h2 className="text-base font-semibold text-gray-900 dark:text-white">
              {isEditMode ? "Edit Skill" : "Save as Skill"}
            </h2>
          </div>
          <button onClick={onClose}
            className="flex items-center justify-center w-8 h-8 rounded-lg text-gray-500 dark:text-gray-400
              hover:bg-gray-100 dark:hover:bg-dark-border transition-colors duration-200">
            <FontAwesomeIcon icon={faXmark} className="text-sm" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5 scrollbar-thin">

          {/* Skill Name */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-gray-600 dark:text-gray-400 uppercase tracking-wide">
              Skill Name <span className="text-red-500">*</span>
            </label>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Login Automation"
              className="w-full h-9 px-3 rounded-lg bg-gray-50 dark:bg-dark-bg border border-gray-200 dark:border-dark-border
                text-sm text-gray-900 dark:text-white placeholder:text-gray-400
                outline-none focus:border-gray-300 dark:focus:border-gray-600 transition-colors" />
          </div>

          {/* Goal */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-gray-600 dark:text-gray-400 uppercase tracking-wide">
              Goal
            </label>
            <textarea value={goal} onChange={(e) => setGoal(e.target.value)}
              placeholder="Human-readable description of what this skill does"
              rows={2}
              className="w-full px-3 py-2 rounded-lg bg-gray-50 dark:bg-dark-bg border border-gray-200 dark:border-dark-border
                text-sm text-gray-900 dark:text-white placeholder:text-gray-400 resize-none
                outline-none focus:border-gray-300 dark:focus:border-gray-600 transition-colors" />
          </div>

          {/* Instructions */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-medium text-gray-600 dark:text-gray-400 uppercase tracking-wide">
                Instructions <span className="text-red-500">*</span>
              </label>
              <span className="text-[10px] text-gray-400 dark:text-gray-500">
                Use {"{{param_name}}"} to mark variables
              </span>
            </div>
            <textarea value={instructions} onChange={(e) => handleInstructionsChange(e.target.value)}
              placeholder="The task prompt sent to the agent — e.g. 'Log into {{website_url}} with email {{email}} and password {{password}}'"
              rows={4}
              className="w-full px-3 py-2 rounded-lg bg-gray-50 dark:bg-dark-bg border border-gray-200 dark:border-dark-border
                text-sm text-gray-900 dark:text-white placeholder:text-gray-400 resize-none
                outline-none focus:border-gray-300 dark:focus:border-gray-600 transition-colors font-mono" />
          </div>

          {/* Parameters */}
          {parameters.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-medium text-gray-600 dark:text-gray-400 uppercase tracking-wide">
                  Parameters ({parameters.length})
                </label>
                <div className="flex items-center gap-3 text-[10px] text-gray-400 dark:text-gray-500 font-medium">
                  <span className="w-[80px] text-center">name</span>
                  <span className="w-[100px]">description</span>
                  <span className="w-[100px]">default value</span>
                </div>
              </div>
              <div className="space-y-2">
                {parameters.map((param, i) => (
                  <div key={param.name} className="flex gap-2 items-center p-2.5 rounded-lg bg-gray-50 dark:bg-dark-bg border border-gray-200 dark:border-dark-border">
                    <span className="flex-shrink-0 font-mono text-xs text-primary bg-primary/10 px-2 py-0.5 rounded-md border border-primary/20 min-w-[80px] text-center">
                      {"{{"}{param.name}{"}}"}
                    </span>
                    <input value={param.description}
                      onChange={(e) => updateParam(i, "description", e.target.value)}
                      placeholder="What this param is"
                      className="flex-1 h-7 px-2 rounded-md bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border
                        text-xs text-gray-900 dark:text-white placeholder:text-gray-400
                        outline-none focus:border-gray-300 dark:focus:border-gray-600" />
                    <input value={param.defaultValue}
                      onChange={(e) => updateParam(i, "defaultValue", e.target.value)}
                      placeholder="default value"
                      className="flex-1 h-7 px-2 rounded-md bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border
                        text-xs text-gray-900 dark:text-white placeholder:text-gray-400
                        outline-none focus:border-gray-300 dark:focus:border-gray-600" />
                  </div>
                ))}
              </div>
              {/* Hint: how params relate to actions */}
              <p className="text-[10px] text-gray-400 dark:text-gray-500 leading-relaxed">
                Use <span className="font-mono text-primary">{"{{param_name}}"}</span> in action args below to reference these parameters. The default value is used when running the skill without overrides.
              </p>
            </div>
          )}

          {/* Actions — collapsible, editable args */}
          {actions.length > 0 && (
            <div className="space-y-2">
              <label className="text-xs font-medium text-gray-600 dark:text-gray-400 uppercase tracking-wide">
                Actions ({actions.length})
              </label>
              <div className="space-y-1.5">
                {actions.map((action, ai) => {
                  const argEntries = Object.entries(action.args);
                  const isExpanded = expandedActions.has(ai);
                  // Show a compact args summary when collapsed
                  const argSummary = argEntries
                    .map(([, v]) => applyParams(v, parameters))
                    .filter(Boolean)
                    .join(", ");

                  return (
                    <div key={ai} className="group/action rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg overflow-hidden">
                      {/* Collapsible header */}
                      <div className="flex items-center">
                        <button
                          type="button"
                          onClick={() => toggleAction(ai)}
                          className="flex-1 flex items-center gap-2 px-3 py-2 hover:bg-gray-100 dark:hover:bg-dark-surface/60 transition-colors text-left min-w-0"
                        >
                          <FontAwesomeIcon
                            icon={isExpanded ? faChevronDown : faChevronRight}
                            className="text-[9px] text-gray-400 flex-shrink-0"
                          />
                          <span className="text-[10px] text-gray-400 font-mono w-4 text-right flex-shrink-0">{ai + 1}.</span>
                          <span className="text-xs font-mono font-semibold text-primary flex-shrink-0">{action.action}</span>
                          {!isExpanded && argSummary && (
                            <span className="text-xs text-gray-400 dark:text-gray-500 truncate ml-1">{argSummary}</span>
                          )}
                        </button>
                        <button
                          type="button"
                          onClick={() => deleteAction(ai)}
                          className="flex items-center justify-center w-7 h-7 mr-1 rounded flex-shrink-0
                            opacity-0 group-hover/action:opacity-100 text-gray-400 hover:text-red-500
                            hover:bg-red-50 dark:hover:bg-red-500/10 transition-all duration-150"
                          title="Remove action"
                        >
                          <FontAwesomeIcon icon={faTrash} className="text-[10px]" />
                        </button>
                      </div>

                      {/* Expanded args */}
                      {isExpanded && argEntries.length > 0 && (
                        <div className="px-3 pb-2.5 pt-1 space-y-1.5 border-t border-gray-200 dark:border-dark-border">
                          {argEntries.map(([key, rawVal]) => {
                            const resolved = applyParams(rawVal, parameters);
                            const hasChange = hasPlaceholder(rawVal) && resolved !== rawVal;
                            return (
                              <div key={key} className="flex items-center gap-2">
                                <span className="text-[10px] text-gray-400 dark:text-gray-500 font-mono flex-shrink-0 w-16 text-right truncate">
                                  {key}
                                </span>
                                <input
                                  value={rawVal}
                                  onChange={(e) => updateActionArg(ai, key, e.target.value)}
                                  className="flex-1 h-6 px-2 rounded bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border
                                    text-xs font-mono text-gray-800 dark:text-gray-200
                                    outline-none focus:border-primary/50 transition-colors"
                                />
                                {hasChange && (
                                  <>
                                    <FontAwesomeIcon icon={faArrowRight} className="text-[10px] text-gray-300 dark:text-gray-600 flex-shrink-0" />
                                    <span className="text-xs font-mono text-emerald-600 dark:text-emerald-400 truncate max-w-[120px]">
                                      {resolved}
                                    </span>
                                  </>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-200 dark:border-dark-border flex-shrink-0">
          <button onClick={onClose}
            className="px-4 h-9 rounded-lg text-sm font-medium text-gray-600 dark:text-gray-300
              border border-gray-200 dark:border-dark-border hover:bg-gray-50 dark:hover:bg-dark-bg
              transition-colors duration-200">
            Cancel
          </button>
          <button onClick={handleSave}
            disabled={saving || !name.trim() || !instructions.trim()}
            className={`flex items-center gap-2 px-4 h-9 rounded-lg text-sm font-medium transition-all duration-200
              ${name.trim() && instructions.trim() && !saving
                ? "bg-gradient-primary text-white shadow-glow hover:shadow-glow-lg cursor-pointer"
                : "bg-gray-100 dark:bg-dark-border text-gray-400 cursor-not-allowed"
              }`}>
            {saving && <FontAwesomeIcon icon={faSpinner} className="text-xs animate-spin" />}
            {isEditMode ? "Update Skill" : "Save Skill"}
          </button>
        </div>
      </div>
    </div>
  );
}
