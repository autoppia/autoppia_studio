import React, { useState, useEffect, useCallback, useRef } from "react";
import { createPortal } from "react-dom";
import { useSearchParams } from "react-router-dom";
import { useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCreditCard,
  faKey,
  faUserCircle,
  faWallet,
  faCoins,
  faPlus,
  faTrash,
  faSpinner,
  faPlay,
  faStop,
  faPen,
  faCheck,
  faTimes,
  faCopy,
} from "@fortawesome/free-solid-svg-icons";
import BrowserTabs from "../components/session/browser-tabs";
import type { BrowserTab } from "../redux/socketSlice";

const apiUrl = process.env.REACT_APP_API_URL;

const TABS = [
  { id: "profiles", label: "Profiles", icon: faUserCircle },
  { id: "api-keys", label: "API Keys", icon: faKey },
  { id: "credit", label: "Credit", icon: faCreditCard },
] as const;

type TabId = (typeof TABS)[number]["id"];

interface Profile {
  id: string;
  name: string;
  contextId: string;
  createdAt: string;
}

// ── Profiles Tab ────────────────────────────────────────────────────

function CreateProfileModal({
  open,
  onClose,
  onCreate,
  creating,
}: {
  open: boolean;
  onClose: () => void;
  onCreate: (name: string) => void;
  creating: boolean;
}) {
  const [name, setName] = useState("");

  useEffect(() => {
    if (open) setName("");
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-md mx-4 bg-white dark:bg-dark-surface rounded-2xl shadow-xl border border-gray-200 dark:border-dark-border p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold text-gray-800 dark:text-gray-100">New Profile</h3>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-dark-border transition-colors"
          >
            <FontAwesomeIcon icon={faTimes} className="text-sm" />
          </button>
        </div>

        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          A profile saves your browser state (cookies, logins) so you can reuse it across sessions.
          After creating, click <strong>Run</strong> to open a live browser and log in to your accounts.
        </p>

        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
          Profile Name
        </label>
        <input
          type="text"
          placeholder="e.g. Work Account, Personal..."
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && name.trim() && onCreate(name.trim())}
          autoFocus
          className="w-full px-4 py-2.5 rounded-xl border border-gray-200 dark:border-dark-border
            bg-gray-50 dark:bg-dark-bg text-sm text-gray-800 dark:text-gray-100
            placeholder-gray-400 dark:placeholder-gray-500 outline-none
            focus:border-[#FF7E5F] focus:ring-1 focus:ring-[#FF7E5F]/30 transition-all duration-200"
        />

        <div className="flex justify-end gap-3 mt-5">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-sm font-medium text-gray-600 dark:text-gray-300
              hover:bg-gray-100 dark:hover:bg-dark-border transition-colors duration-200"
          >
            Cancel
          </button>
          <button
            onClick={() => name.trim() && onCreate(name.trim())}
            disabled={!name.trim() || creating}
            className="flex items-center gap-2 px-5 py-2 rounded-xl text-sm font-semibold text-white
              bg-gradient-primary shadow-glow hover:shadow-glow-lg transition-all duration-200
              disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none"
          >
            {creating ? (
              <FontAwesomeIcon icon={faSpinner} className="animate-spin text-xs" />
            ) : (
              <FontAwesomeIcon icon={faPlus} className="text-xs" />
            )}
            <span>Create</span>
          </button>
        </div>
      </div>
    </div>
  );
}

function ProfilesTab() {
  const user = useSelector((state: any) => state.user);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);

  // Rename state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");
  const [savingName, setSavingName] = useState(false);

  // Run state
  const [runningId, setRunningId] = useState<string | null>(null);
  const [activeProfileId, setActiveProfileId] = useState<string | null>(null);
  const [liveUrl, setLiveUrl] = useState<string | null>(null);
  const [stoppingId, setStoppingId] = useState<string | null>(null);

  // Tab state for profile browser
  const [profileTabs, setProfileTabs] = useState<BrowserTab[]>([]);
  const [profileActiveTabIndex, setProfileActiveTabIndex] = useState(0);
  const tabPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadProfiles = useCallback(async () => {
    if (!user.email) return;
    try {
      const res = await fetch(`${apiUrl}/profiles?email=${user.email}`);
      const data = await res.json();
      setProfiles(data.profiles || []);
    } catch (err) {
      console.error("Failed to load profiles:", err);
    } finally {
      setLoading(false);
    }
  }, [user.email]);

  useEffect(() => {
    loadProfiles();
  }, [loadProfiles]);

  const handleCreate = async (name: string) => {
    if (!name || creating) return;
    setCreating(true);
    try {
      const res = await fetch(`${apiUrl}/profiles`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: user.email, name }),
      });
      const data = await res.json();
      if (data.profile) {
        setProfiles((prev) => [data.profile, ...prev]);
        setShowCreateModal(false);
      }
    } catch (err) {
      console.error("Failed to create profile:", err);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: string) => {
    setDeletingId(id);
    try {
      await fetch(`${apiUrl}/profiles/${id}`, { method: "DELETE" });
      setProfiles((prev) => prev.filter((p) => p.id !== id));
      if (activeProfileId === id) {
        stopTabPolling();
        setActiveProfileId(null);
        setLiveUrl(null);
        setProfileTabs([]);
        setProfileActiveTabIndex(0);
      }
    } catch (err) {
      console.error("Failed to delete profile:", err);
    } finally {
      setDeletingId(null);
    }
  };

  const handleStartEdit = (profile: Profile) => {
    setEditingId(profile.id);
    setEditingName(profile.name);
  };

  const handleCancelEdit = () => {
    setEditingId(null);
    setEditingName("");
  };

  const handleSaveName = async (id: string) => {
    if (!editingName.trim() || savingName) return;
    setSavingName(true);
    try {
      await fetch(`${apiUrl}/profiles/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: editingName.trim() }),
      });
      setProfiles((prev) =>
        prev.map((p) => (p.id === id ? { ...p, name: editingName.trim() } : p))
      );
      setEditingId(null);
      setEditingName("");
    } catch (err) {
      console.error("Failed to update profile:", err);
    } finally {
      setSavingName(false);
    }
  };

  const refreshTabs = useCallback(async (profileId: string) => {
    try {
      const res = await fetch(`${apiUrl}/profiles/${profileId}/tabs`);
      if (res.ok) {
        const data = await res.json();
        if (data.tabs) {
          setProfileTabs(data.tabs);
        }
      }
    } catch {
      // ignore polling errors
    }
  }, []);

  const startTabPolling = useCallback((profileId: string) => {
    if (tabPollRef.current) clearInterval(tabPollRef.current);
    tabPollRef.current = setInterval(() => refreshTabs(profileId), 5000);
  }, [refreshTabs]);

  const stopTabPolling = useCallback(() => {
    if (tabPollRef.current) {
      clearInterval(tabPollRef.current);
      tabPollRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => stopTabPolling();
  }, [stopTabPolling]);

  const handleRun = async (id: string) => {
    setRunningId(id);
    try {
      const res = await fetch(`${apiUrl}/profiles/${id}/run`, { method: "POST" });
      const data = await res.json();
      if (data.liveUrl) {
        setActiveProfileId(id);
        setLiveUrl(data.liveUrl);
        if (data.tabs && data.tabs.length > 0) {
          setProfileTabs(data.tabs);
          setProfileActiveTabIndex(0);
        }
        startTabPolling(id);
      }
    } catch (err) {
      console.error("Failed to run profile:", err);
    } finally {
      setRunningId(null);
    }
  };

  const handleSelectProfileTab = (index: number) => {
    setProfileActiveTabIndex(index);
    if (profileTabs[index]?.debugger_fullscreen_url) {
      setLiveUrl(profileTabs[index].debugger_fullscreen_url);
    }
  };

  const handleCloseProfileTab = async (index: number) => {
    if (!activeProfileId) return;
    try {
      const res = await fetch(`${apiUrl}/profiles/${activeProfileId}/close-tab`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tab_index: index }),
      });
      const data = await res.json();
      if (data.tabs) {
        setProfileTabs(data.tabs);
        const newIndex = data.activeIndex ?? 0;
        setProfileActiveTabIndex(newIndex);
        if (data.tabs[newIndex]?.debugger_fullscreen_url) {
          setLiveUrl(data.tabs[newIndex].debugger_fullscreen_url);
        }
      }
    } catch (err) {
      console.error("Failed to close tab:", err);
    }
  };

  const handleNewProfileTab = async () => {
    if (!activeProfileId) return;
    try {
      const res = await fetch(`${apiUrl}/profiles/${activeProfileId}/new-tab`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await res.json();
      if (data.tabs) {
        setProfileTabs(data.tabs);
        const newIndex = data.activeIndex ?? data.tabs.length - 1;
        setProfileActiveTabIndex(newIndex);
        if (data.tabs[newIndex]?.debugger_fullscreen_url) {
          setLiveUrl(data.tabs[newIndex].debugger_fullscreen_url);
        }
      }
    } catch (err) {
      console.error("Failed to open new tab:", err);
    }
  };

  const handleStop = async (id: string) => {
    setStoppingId(id);
    stopTabPolling();
    try {
      await fetch(`${apiUrl}/profiles/${id}/stop`, { method: "POST" });
      setActiveProfileId(null);
      setLiveUrl(null);
      setProfileTabs([]);
      setProfileActiveTabIndex(0);
    } catch (err) {
      console.error("Failed to stop profile:", err);
    } finally {
      setStoppingId(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48 text-gray-400 dark:text-gray-500">
        <FontAwesomeIcon icon={faSpinner} className="animate-spin text-lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Profiles persist browser state (cookies, logins) across sessions.
        </p>
        <button
          onClick={() => setShowCreateModal(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold text-white
            bg-gradient-primary shadow-glow hover:shadow-glow-lg transition-all duration-200 flex-shrink-0"
        >
          <FontAwesomeIcon icon={faPlus} className="text-xs" />
          <span>New Profile</span>
        </button>
      </div>

      <CreateProfileModal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onCreate={handleCreate}
        creating={creating}
      />

      {/* Profiles list */}
      <div className="space-y-3">
        {profiles.length === 0 ? (
          <div className="text-center py-10 text-gray-400 dark:text-gray-500">
            <FontAwesomeIcon icon={faUserCircle} className="text-3xl mb-2 block mx-auto opacity-40" />
            <p className="text-sm">No profiles yet</p>
          </div>
        ) : (
          profiles.map((profile) => (
            <div
              key={profile.id}
              className={`rounded-xl border transition-all duration-200 ${
                activeProfileId === profile.id
                  ? "border-[#FF7E5F] bg-[#FF7E5F]/5 dark:bg-[#FF7E5F]/10"
                  : "border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg hover:border-gray-300 dark:hover:border-gray-600"
              }`}
            >
              <div className="flex items-center justify-between px-5 py-4 group">
                <div className="min-w-0 flex-1">
                  {editingId === profile.id ? (
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        value={editingName}
                        onChange={(e) => setEditingName(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleSaveName(profile.id);
                          if (e.key === "Escape") handleCancelEdit();
                        }}
                        autoFocus
                        className="flex-1 px-3 py-1.5 rounded-lg border border-[#FF7E5F] bg-white dark:bg-dark-bg
                          text-sm text-gray-800 dark:text-gray-100 outline-none ring-1 ring-[#FF7E5F]/30"
                      />
                      <button
                        onClick={() => handleSaveName(profile.id)}
                        disabled={savingName || !editingName.trim()}
                        className="w-8 h-8 rounded-lg flex items-center justify-center text-green-600 hover:bg-green-50 dark:hover:bg-green-500/10 transition-colors"
                      >
                        {savingName ? (
                          <FontAwesomeIcon icon={faSpinner} className="animate-spin text-xs" />
                        ) : (
                          <FontAwesomeIcon icon={faCheck} className="text-xs" />
                        )}
                      </button>
                      <button
                        onClick={handleCancelEdit}
                        className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-dark-border transition-colors"
                      >
                        <FontAwesomeIcon icon={faTimes} className="text-xs" />
                      </button>
                    </div>
                  ) : (
                    <>
                      <p className="text-sm font-semibold text-gray-800 dark:text-gray-100 truncate">
                        {profile.name}
                      </p>
                      <p className="text-xs text-gray-400 dark:text-gray-500 truncate mt-1">
                        Context: {profile.contextId || "N/A"}
                      </p>
                    </>
                  )}
                </div>
                <div className="flex items-center gap-1.5 flex-shrink-0 ml-4">
                  {/* Run / Stop button */}
                  {activeProfileId === profile.id ? (
                    <button
                      onClick={() => handleStop(profile.id)}
                      disabled={stoppingId === profile.id}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                        text-red-600 bg-red-50 dark:bg-red-500/10 hover:bg-red-100 dark:hover:bg-red-500/20
                        transition-colors duration-200"
                    >
                      {stoppingId === profile.id ? (
                        <FontAwesomeIcon icon={faSpinner} className="animate-spin text-xs" />
                      ) : (
                        <FontAwesomeIcon icon={faStop} className="text-xs" />
                      )}
                      <span>Stop</span>
                    </button>
                  ) : (
                    <button
                      onClick={() => handleRun(profile.id)}
                      disabled={runningId === profile.id || !!activeProfileId}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                        text-white bg-gradient-primary shadow-soft hover:shadow-glow
                        transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none
                        opacity-0 group-hover:opacity-100"
                      title="Launch browser to log in"
                    >
                      {runningId === profile.id ? (
                        <FontAwesomeIcon icon={faSpinner} className="animate-spin text-xs" />
                      ) : (
                        <FontAwesomeIcon icon={faPlay} className="text-xs" />
                      )}
                      <span>Run</span>
                    </button>
                  )}

                  {/* Rename button */}
                  {editingId !== profile.id && (
                    <button
                      onClick={() => handleStartEdit(profile)}
                      className="flex items-center justify-center w-8 h-8 rounded-lg
                        text-gray-400 hover:text-[#FF7E5F] hover:bg-[#FF7E5F]/10
                        transition-all duration-200 opacity-0 group-hover:opacity-100"
                      title="Rename profile"
                    >
                      <FontAwesomeIcon icon={faPen} className="text-xs" />
                    </button>
                  )}

                  {/* Delete button */}
                  <button
                    onClick={() => handleDelete(profile.id)}
                    disabled={deletingId === profile.id || activeProfileId === profile.id}
                    className="flex items-center justify-center w-8 h-8 rounded-lg
                      text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10
                      transition-all duration-200 opacity-0 group-hover:opacity-100
                      disabled:opacity-20 disabled:cursor-not-allowed"
                    title="Delete profile"
                  >
                    {deletingId === profile.id ? (
                      <FontAwesomeIcon icon={faSpinner} className="animate-spin text-xs" />
                    ) : (
                      <FontAwesomeIcon icon={faTrash} className="text-xs" />
                    )}
                  </button>
                </div>
              </div>

            </div>
          ))
        )}
      </div>

      {/* Live browser modal - portaled to body so backdrop covers full page */}
      {activeProfileId && liveUrl && createPortal(
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
          <div className="relative w-full max-w-5xl mx-4 flex flex-col bg-dark-bg overflow-hidden rounded-xl"
            style={{ height: "90vh" }}>
            <div className="flex items-center justify-between px-4 py-2 flex-shrink-0 bg-gray-100 dark:bg-dark-surface">
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1.5 text-xs text-green-600">
                  <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                  Connected
                </span>
                <span className="text-sm font-semibold text-gray-800 dark:text-gray-100">
                  {profiles.find((p) => p.id === activeProfileId)?.name}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-gray-400 dark:text-gray-500">
                  Log in to your accounts, then close when done
                </span>
                <button
                  onClick={() => handleStop(activeProfileId)}
                  disabled={stoppingId === activeProfileId}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium
                    text-red-600 bg-red-50 dark:bg-red-500/10 hover:bg-red-100 dark:hover:bg-red-500/20
                    transition-colors duration-200"
                >
                  {stoppingId === activeProfileId ? (
                    <FontAwesomeIcon icon={faSpinner} className="animate-spin text-xs" />
                  ) : (
                    <FontAwesomeIcon icon={faStop} className="text-xs" />
                  )}
                  <span>Stop & Save</span>
                </button>
              </div>
            </div>
            <BrowserTabs
              tabs={profileTabs}
              activeIndex={profileActiveTabIndex}
              onSelectTab={handleSelectProfileTab}
              onNewTab={handleNewProfileTab}
              onCloseTab={handleCloseProfileTab}
              compact
            />
            <iframe
              src={liveUrl}
              sandbox="allow-same-origin allow-scripts"
              allow="clipboard-read; clipboard-write"
              className="flex-1 w-full border-0"
              title="Profile browser session"
            />
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}

// ── API Keys Tab ───────────────────────────────────────────────────

interface APIKeyItem {
  id: string;
  name: string;
  prefix: string;
  key?: string;
  createdAt: string;
}

function CreateAPIKeyModal({
  open,
  onClose,
  onCreate,
  creating,
}: {
  open: boolean;
  onClose: () => void;
  onCreate: (name: string) => void;
  creating: boolean;
}) {
  const [name, setName] = useState("");

  useEffect(() => {
    if (open) setName("");
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-md mx-4 bg-white dark:bg-dark-surface rounded-2xl shadow-xl border border-gray-200 dark:border-dark-border p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold text-gray-800 dark:text-gray-100">New API Key</h3>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-dark-border transition-colors"
          >
            <FontAwesomeIcon icon={faTimes} className="text-sm" />
          </button>
        </div>

        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          API keys allow you to access the Automata API programmatically.
          The full key will only be shown once after creation.
        </p>

        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
          Key Name
        </label>
        <input
          type="text"
          placeholder="e.g. Production, Development..."
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && name.trim() && onCreate(name.trim())}
          autoFocus
          className="w-full px-4 py-2.5 rounded-xl border border-gray-200 dark:border-dark-border
            bg-gray-50 dark:bg-dark-bg text-sm text-gray-800 dark:text-gray-100
            placeholder-gray-400 dark:placeholder-gray-500 outline-none
            focus:border-[#FF7E5F] focus:ring-1 focus:ring-[#FF7E5F]/30 transition-all duration-200"
        />

        <div className="flex justify-end gap-3 mt-5">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-sm font-medium text-gray-600 dark:text-gray-300
              hover:bg-gray-100 dark:hover:bg-dark-border transition-colors duration-200"
          >
            Cancel
          </button>
          <button
            onClick={() => name.trim() && onCreate(name.trim())}
            disabled={!name.trim() || creating}
            className="flex items-center gap-2 px-5 py-2 rounded-xl text-sm font-semibold text-white
              bg-gradient-primary shadow-glow hover:shadow-glow-lg transition-all duration-200
              disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none"
          >
            {creating ? (
              <FontAwesomeIcon icon={faSpinner} className="animate-spin text-xs" />
            ) : (
              <FontAwesomeIcon icon={faPlus} className="text-xs" />
            )}
            <span>Create</span>
          </button>
        </div>
      </div>
    </div>
  );
}

function APIKeysTab() {
  const user = useSelector((state: any) => state.user);
  const [apiKeys, setApiKeys] = useState<APIKeyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);

  // Newly created key (shown once)
  const [newlyCreatedKey, setNewlyCreatedKey] = useState<string | null>(null);
  const [newlyCreatedId, setNewlyCreatedId] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Rename state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");
  const [savingName, setSavingName] = useState(false);

  const loadAPIKeys = useCallback(async () => {
    if (!user.email) return;
    try {
      const res = await fetch(`${apiUrl}/api-keys?email=${user.email}`);
      const data = await res.json();
      setApiKeys(data.apiKeys || []);
    } catch (err) {
      console.error("Failed to load API keys:", err);
    } finally {
      setLoading(false);
    }
  }, [user.email]);

  useEffect(() => {
    loadAPIKeys();
  }, [loadAPIKeys]);

  const handleCreate = async (name: string) => {
    if (!name || creating) return;
    setCreating(true);
    try {
      const res = await fetch(`${apiUrl}/api-keys`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: user.email, name }),
      });
      const data = await res.json();
      if (data.apiKey) {
        setApiKeys((prev) => [data.apiKey, ...prev]);
        setNewlyCreatedKey(data.apiKey.key);
        setNewlyCreatedId(data.apiKey.id);
        setCopied(false);
        setShowCreateModal(false);
      }
    } catch (err) {
      console.error("Failed to create API key:", err);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: string) => {
    setDeletingId(id);
    try {
      await fetch(`${apiUrl}/api-keys/${id}`, { method: "DELETE" });
      setApiKeys((prev) => prev.filter((k) => k.id !== id));
      if (newlyCreatedId === id) {
        setNewlyCreatedKey(null);
        setNewlyCreatedId(null);
      }
    } catch (err) {
      console.error("Failed to delete API key:", err);
    } finally {
      setDeletingId(null);
    }
  };

  const handleStartEdit = (key: APIKeyItem) => {
    setEditingId(key.id);
    setEditingName(key.name);
  };

  const handleCancelEdit = () => {
    setEditingId(null);
    setEditingName("");
  };

  const handleSaveName = async (id: string) => {
    if (!editingName.trim() || savingName) return;
    setSavingName(true);
    try {
      await fetch(`${apiUrl}/api-keys/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: editingName.trim() }),
      });
      setApiKeys((prev) =>
        prev.map((k) => (k.id === id ? { ...k, name: editingName.trim() } : k))
      );
      setEditingId(null);
      setEditingName("");
    } catch (err) {
      console.error("Failed to update API key:", err);
    } finally {
      setSavingName(false);
    }
  };

  const handleCopy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      console.error("Failed to copy to clipboard");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48 text-gray-400 dark:text-gray-500">
        <FontAwesomeIcon icon={faSpinner} className="animate-spin text-lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Manage API keys for programmatic access to Automata.
        </p>
        <button
          onClick={() => setShowCreateModal(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold text-white
            bg-gradient-primary shadow-glow hover:shadow-glow-lg transition-all duration-200 flex-shrink-0"
        >
          <FontAwesomeIcon icon={faPlus} className="text-xs" />
          <span>New Key</span>
        </button>
      </div>

      <CreateAPIKeyModal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onCreate={handleCreate}
        creating={creating}
      />

      {/* Newly created key banner */}
      {newlyCreatedKey && (
        <div className="rounded-xl border border-[#FF7E5F]/30 bg-[#FF7E5F]/5 dark:bg-[#FF7E5F]/10 p-4">
          <p className="text-xs font-medium text-gray-600 dark:text-gray-300 mb-2">
            Copy your API key now. It won't be shown again.
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 px-3 py-2 rounded-lg bg-white dark:bg-dark-bg border border-gray-200 dark:border-dark-border
              text-sm text-gray-800 dark:text-gray-100 font-mono truncate select-all">
              {newlyCreatedKey}
            </code>
            <button
              onClick={() => handleCopy(newlyCreatedKey)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all duration-200
                ${copied
                  ? "text-green-600 bg-green-50 dark:bg-green-500/10"
                  : "text-gray-600 dark:text-gray-300 bg-gray-100 dark:bg-dark-border hover:bg-gray-200 dark:hover:bg-gray-600"
                }`}
            >
              <FontAwesomeIcon icon={copied ? faCheck : faCopy} className="text-xs" />
              <span>{copied ? "Copied" : "Copy"}</span>
            </button>
          </div>
        </div>
      )}

      {/* API keys list */}
      <div className="space-y-3">
        {apiKeys.length === 0 ? (
          <div className="text-center py-10 text-gray-400 dark:text-gray-500">
            <FontAwesomeIcon icon={faKey} className="text-3xl mb-2 block mx-auto opacity-40" />
            <p className="text-sm">No API keys yet</p>
          </div>
        ) : (
          apiKeys.map((apiKey) => (
            <div
              key={apiKey.id}
              className="rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg
                hover:border-gray-300 dark:hover:border-gray-600 transition-all duration-200"
            >
              <div className="flex items-center justify-between px-5 py-4 group">
                <div className="min-w-0 flex-1">
                  {editingId === apiKey.id ? (
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        value={editingName}
                        onChange={(e) => setEditingName(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleSaveName(apiKey.id);
                          if (e.key === "Escape") handleCancelEdit();
                        }}
                        autoFocus
                        className="flex-1 px-3 py-1.5 rounded-lg border border-[#FF7E5F] bg-white dark:bg-dark-bg
                          text-sm text-gray-800 dark:text-gray-100 outline-none ring-1 ring-[#FF7E5F]/30"
                      />
                      <button
                        onClick={() => handleSaveName(apiKey.id)}
                        disabled={savingName || !editingName.trim()}
                        className="w-8 h-8 rounded-lg flex items-center justify-center text-green-600 hover:bg-green-50 dark:hover:bg-green-500/10 transition-colors"
                      >
                        {savingName ? (
                          <FontAwesomeIcon icon={faSpinner} className="animate-spin text-xs" />
                        ) : (
                          <FontAwesomeIcon icon={faCheck} className="text-xs" />
                        )}
                      </button>
                      <button
                        onClick={handleCancelEdit}
                        className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-dark-border transition-colors"
                      >
                        <FontAwesomeIcon icon={faTimes} className="text-xs" />
                      </button>
                    </div>
                  ) : (
                    <>
                      <p className="text-sm font-semibold text-gray-800 dark:text-gray-100 truncate">
                        {apiKey.name}
                      </p>
                      <p className="text-xs text-gray-400 dark:text-gray-500 font-mono truncate mt-1">
                        {apiKey.prefix}
                      </p>
                    </>
                  )}
                </div>
                <div className="flex items-center gap-1.5 flex-shrink-0 ml-4">
                  {/* Rename button */}
                  {editingId !== apiKey.id && (
                    <button
                      onClick={() => handleStartEdit(apiKey)}
                      className="flex items-center justify-center w-8 h-8 rounded-lg
                        text-gray-400 hover:text-[#FF7E5F] hover:bg-[#FF7E5F]/10
                        transition-all duration-200 opacity-0 group-hover:opacity-100"
                      title="Rename key"
                    >
                      <FontAwesomeIcon icon={faPen} className="text-xs" />
                    </button>
                  )}

                  {/* Delete button */}
                  <button
                    onClick={() => handleDelete(apiKey.id)}
                    disabled={deletingId === apiKey.id}
                    className="flex items-center justify-center w-8 h-8 rounded-lg
                      text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10
                      transition-all duration-200 opacity-0 group-hover:opacity-100
                      disabled:opacity-20 disabled:cursor-not-allowed"
                    title="Delete key"
                  >
                    {deletingId === apiKey.id ? (
                      <FontAwesomeIcon icon={faSpinner} className="animate-spin text-xs" />
                    ) : (
                      <FontAwesomeIcon icon={faTrash} className="text-xs" />
                    )}
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

// ── Credit Tab ──────────────────────────────────────────────────────

function CreditTab() {
  return (
    <div className="space-y-6">
      {/* Credit balance card */}
      <div className="relative overflow-hidden rounded-xl bg-gradient-primary p-6 text-white">
        <div className="absolute top-0 right-0 w-32 h-32 -mr-8 -mt-8 rounded-full bg-white/10" />
        <div className="absolute bottom-0 left-0 w-24 h-24 -ml-6 -mb-6 rounded-full bg-white/10" />
        <div className="relative">
          <div className="flex items-center gap-2 mb-1">
            <FontAwesomeIcon icon={faWallet} className="text-sm opacity-80" />
            <span className="text-sm font-medium opacity-80">Available Balance</span>
          </div>
          <p className="text-4xl font-bold tracking-tight">
            $0.00
          </p>
          <p className="text-sm mt-1 opacity-70">USD</p>
        </div>
      </div>

      {/* Free beta notice */}
      <div className="rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-5">
        <div className="flex items-center gap-2 mb-2">
          <span className="w-2 h-2 rounded-full bg-gray-400 dark:bg-gray-500 animate-pulse" />
          <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200">Free Beta</h3>
        </div>
        <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
          Automata is currently in free beta. All features are available at no cost during this period.
          No top-up is required.
        </p>
      </div>
    </div>
  );
}

// ── Tab Content Router ──────────────────────────────────────────────

function TabContent({ tab }: { tab: TabId }) {
  if (tab === "profiles") return <ProfilesTab />;
  if (tab === "api-keys") return <APIKeysTab />;
  if (tab === "credit") return <CreditTab />;
  return null;
}

// ── Settings Page ───────────────────────────────────────────────────

export default function Settings(): React.ReactElement {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = (searchParams.get("tab") as TabId) || "profiles";

  const handleTabChange = (tab: TabId) => {
    setSearchParams({ tab });
  };

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
        <div className="flex items-center justify-between h-14 px-6 border-b border-gray-200 dark:border-dark-border
          bg-white/80 dark:bg-dark-bg/80 backdrop-blur-sm flex-shrink-0">
          <h1 className="text-lg font-semibold text-gray-800 dark:text-gray-100">
            Settings
          </h1>
          <div
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg
            border border-gray-200 dark:border-dark-border text-gray-600 dark:text-gray-300 text-sm font-medium"
          >
            <FontAwesomeIcon icon={faCoins} className="text-xs" />
            <span>0.00 Credits</span>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto px-6 py-6">
          <div className="max-w-3xl mx-auto">
            {/* Tabs */}
            <div className="flex gap-1 p-1 bg-gray-200/60 dark:bg-dark-surface rounded-lg mb-6">
              {TABS.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => handleTabChange(tab.id)}
                  className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all duration-200 flex-1 justify-center
                    ${
                      activeTab === tab.id
                        ? "bg-white dark:bg-dark-border text-gray-900 dark:text-white shadow-sm"
                        : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
                    }`}
                >
                  <FontAwesomeIcon icon={tab.icon} className="text-xs" />
                  <span>{tab.label}</span>
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-6 shadow-soft">
              <TabContent tab={activeTab} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
