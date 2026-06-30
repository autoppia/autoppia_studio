import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faWandMagicSparkles,
  faPlus,
  faMagnifyingGlass,
  faTrash,
  faPen,
  faSpinner,
} from "@fortawesome/free-solid-svg-icons";
import { Skill } from "../utils/types";
import SectionTitle from "../components/layout/section-title";
import ConvertToSkillModal from "../components/session/convert-to-skill-modal";
import ConfirmModal from "../components/common/confirm-modal";
import { getApiUrl } from "../utils/api-url";

const apiUrl = getApiUrl();

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export default function Skills() {
  const navigate = useNavigate();
  const user = useSelector((state: any) => state.user);

  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [editingSkill, setEditingSkill] = useState<Skill | null>(null);
  const [deletingSkillId, setDeletingSkillId] = useState<string | null>(null);

  useEffect(() => {
    if (!user.email) return;
    fetchSkills();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user.email]);

  const fetchSkills = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${apiUrl}/skills?email=${encodeURIComponent(user.email)}`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setSkills(data.skills || []);
    } catch (err) {
      console.error("Failed to fetch skills:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (skillId: string) => {
    try {
      const res = await fetch(`${apiUrl}/skills/${skillId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      setSkills((prev) => prev.filter((s) => s.skillId !== skillId));
    } catch (err) {
      console.error("Failed to delete skill:", err);
    }
  };

  const filtered = skills.filter(
    (s) =>
      s.name.toLowerCase().includes(search.toLowerCase()) ||
      s.goal.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="w-full h-full flex relative overflow-auto bg-gray-100 dark:bg-dark-bg">
      <div className="absolute inset-0 hidden dark:block pointer-events-none">
        <img
          src="/assets/images/bg/dark-bg.webp"
          alt=""
          className="w-full h-full object-cover"
        />
      </div>

      <div className="flex flex-col w-full h-full relative">
        {/* Header */}
        <div className="flex min-h-16 items-center justify-between gap-3 border-b border-gray-200 bg-white/80 px-8 py-3 backdrop-blur-sm dark:border-dark-border dark:bg-dark-bg/80 flex-shrink-0">
          <SectionTitle
            icon={faWandMagicSparkles}
            title="Skills"
            subtitle="Governed, reusable agent skills"
          />
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto px-6 py-6">
          {/* Search + Create */}
          <div className="flex items-center gap-3 mb-6">
            <div className="flex items-center gap-2 px-3 h-10 rounded-xl bg-white dark:bg-dark-surface
              border border-gray-200 dark:border-dark-border
              focus-within:border-gray-300 dark:focus-within:border-gray-600 transition-all duration-200 flex-1">
              <FontAwesomeIcon icon={faMagnifyingGlass} className="text-gray-400 text-sm" />
              <input
                type="text"
                placeholder="Search skills..."
                className="w-full outline-none bg-transparent text-sm text-gray-700 dark:text-gray-200 placeholder:text-gray-400"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <button
              onClick={() => navigate("/skills/create")}
              className="flex items-center gap-2 px-4 h-10 rounded-xl bg-gradient-primary text-white text-sm font-medium flex-shrink-0 ml-auto
                shadow-glow hover:shadow-glow-lg hover:scale-105 transition-all duration-200"
            >
              <FontAwesomeIcon icon={faPlus} className="text-xs" />
              <span>Create Skill</span>
            </button>
          </div>

          {/* Loading */}
          {loading ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3">
              <FontAwesomeIcon icon={faSpinner} className="text-primary text-2xl animate-spin" />
              <p className="text-sm text-gray-400 dark:text-gray-500">Loading skills…</p>
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-primary shadow-glow mb-4">
                <FontAwesomeIcon icon={faWandMagicSparkles} className="text-white text-xl" />
              </div>
              <p className="text-gray-500 dark:text-gray-400 text-sm">
                {search ? "No skills found." : "No skills yet. Create your first skill!"}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {filtered.map((skill) => (
                <div
                  key={skill.skillId}
                  onClick={() => navigate(`/skills/${skill.skillId}`)}
                  className="group relative flex flex-col bg-white dark:bg-dark-surface rounded-xl
                    border border-gray-200 dark:border-dark-border shadow-soft
                    hover:shadow-soft-lg hover:border-gray-300 dark:hover:border-gray-600
                    transition-all duration-200 p-5 cursor-pointer"
                >
                  {/* Action buttons */}
                  <div className="absolute top-3 right-3 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-all duration-200">
                    <button
                      onClick={(e) => { e.stopPropagation(); setEditingSkill(skill); }}
                      className="flex items-center justify-center w-7 h-7 rounded-lg
                        text-gray-300 dark:text-gray-600 hover:text-primary dark:hover:text-primary
                        hover:bg-primary/10 transition-all duration-200"
                      title="Edit"
                    >
                      <FontAwesomeIcon icon={faPen} className="text-xs" />
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); setDeletingSkillId(skill.skillId); }}
                      className="flex items-center justify-center w-7 h-7 rounded-lg
                        text-gray-300 dark:text-gray-600 hover:text-red-500 dark:hover:text-red-400
                        hover:bg-red-50 dark:hover:bg-red-500/10 transition-all duration-200"
                      title="Delete"
                    >
                      <FontAwesomeIcon icon={faTrash} className="text-xs" />
                    </button>
                  </div>

                  {/* Icon */}
                  <div className="flex items-center justify-center w-11 h-11 rounded-xl bg-gradient-primary shadow-glow mb-4 flex-shrink-0">
                    <FontAwesomeIcon icon={faWandMagicSparkles} className="text-white text-base" />
                  </div>

                  {/* Title */}
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-1 pr-6">
                    {skill.name}
                  </h3>

                  {/* Goal */}
                  <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed flex-1 line-clamp-3">
                    {skill.goal}
                  </p>

                  {/* Parameters badges */}
                  {skill.parameters && skill.parameters.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-3">
                      {skill.parameters.slice(0, 3).map((p) => (
                        <span
                          key={p.name}
                          className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-primary/10 text-primary border border-primary/20"
                        >
                          {`{{${p.name}}}`}
                        </span>
                      ))}
                      {skill.parameters.length > 3 && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] text-gray-400 border border-gray-200 dark:border-dark-border">
                          +{skill.parameters.length - 3}
                        </span>
                      )}
                    </div>
                  )}

                  {/* Creation date */}
                  {skill.createdAt && (
                    <p className="text-[11px] text-gray-400 dark:text-gray-600 mt-3">
                      {formatDate(skill.createdAt)}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {deletingSkillId && (
        <ConfirmModal
          title="Delete Skill"
          message="Are you sure you want to delete this skill? This action cannot be undone."
          onConfirm={() => { handleDelete(deletingSkillId); setDeletingSkillId(null); }}
          onCancel={() => setDeletingSkillId(null)}
        />
      )}

      {editingSkill && (
        <ConvertToSkillModal
          onClose={() => setEditingSkill(null)}
          userEmail={user.email || ""}
          skillId={editingSkill.skillId}
          skillName={editingSkill.name}
          skillGoal={editingSkill.goal}
          skillInstructions={editingSkill.instructions}
          initialActions={editingSkill.actions}
          onSaved={fetchSkills}
        />
      )}
    </div>
  );
}
