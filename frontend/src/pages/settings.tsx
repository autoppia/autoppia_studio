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
  faArrowUp,
  faCheckCircle,
  faTimesCircle,
  faClock,
  faReceipt,
} from "@fortawesome/free-solid-svg-icons";
import BrowserTabs from "../components/session/browser-tabs";
import ConfirmModal from "../components/common/confirm-modal";
import type { BrowserTab } from "../redux/socketSlice";

const apiUrl = process.env.REACT_APP_API_URL;

// UI-only placeholder until the wallet backend ships.
const WALLET_PLACEHOLDER = { balance: "0.00", currency: "EUR", loading: false };

interface TransactionData {
  id: string;
  type: string;
  amount: string;
  currency: string;
  status: string;
  provider: string;
  provider_payment_id: string | null;
  created_at: string;
  metadata: Record<string, unknown>;
}

const TABS = [
  { id: "profiles", label: "Profiles", icon: faUserCircle },
  { id: "api-keys", label: "API Keys", icon: faKey },
  { id: "credit", label: "Credit", icon: faCreditCard },
  { id: "invoices", label: "Invoices", icon: faReceipt },
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
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
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
    tabPollRef.current = setInterval(() => refreshTabs(profileId), 2000);
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
                    onClick={() => setConfirmDeleteId(profile.id)}
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

      {confirmDeleteId && (
        <ConfirmModal
          title="Delete Profile"
          message="Are you sure you want to delete this profile? All saved browser state will be lost."
          onConfirm={() => { handleDelete(confirmDeleteId); setConfirmDeleteId(null); }}
          onCancel={() => setConfirmDeleteId(null)}
        />
      )}

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
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
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
                    onClick={() => setConfirmDeleteId(apiKey.id)}
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

      {confirmDeleteId && (
        <ConfirmModal
          title="Delete API Key"
          message="Are you sure you want to delete this API key? Any integrations using it will stop working."
          onConfirm={() => { handleDelete(confirmDeleteId); setConfirmDeleteId(null); }}
          onCancel={() => setConfirmDeleteId(null)}
        />
      )}
    </div>
  );
}

// ── Credit Tab ──────────────────────────────────────────────────────

const QUICK_AMOUNTS = [10, 25, 50, 100];

function AddFundsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [amount, setAmount] = useState("");
  const [amountError, setAmountError] = useState("");
  const [showComingSoon, setShowComingSoon] = useState(false);

  useEffect(() => {
    if (open) { setAmount(""); setAmountError(""); setShowComingSoon(false); }
  }, [open]);

  if (!open) return null;

  const handleQuick = (val: number) => {
    setAmount(String(val));
    setAmountError("");
    setShowComingSoon(false);
  };

  const handlePayClick = () => {
    const parsed = parseFloat(amount);
    if (isNaN(parsed) || parsed < 1 || parsed > 1000) {
      setAmountError("Enter an amount between €1.00 and €1,000.00");
      setShowComingSoon(false);
      return;
    }
    setShowComingSoon(true);
  };

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />

      <div className="relative w-full max-w-sm mx-4 bg-white dark:bg-dark-surface rounded-2xl
        shadow-xl border border-gray-200 dark:border-dark-border p-6 flex flex-col gap-5">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-primary flex items-center justify-center">
              <FontAwesomeIcon icon={faArrowUp} className="text-white text-xs" />
            </div>
            <h3 className="text-base font-semibold text-gray-800 dark:text-gray-100">Add funds</h3>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded-lg flex items-center justify-center
              text-gray-400 hover:text-gray-600 hover:bg-gray-100
              dark:hover:text-gray-200 dark:hover:bg-dark-border transition-colors"
          >
            <FontAwesomeIcon icon={faTimes} className="text-xs" />
          </button>
        </div>

        {/* Quick amounts */}
        <div>
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">Quick select</p>
          <div className="grid grid-cols-4 gap-2">
            {QUICK_AMOUNTS.map((val) => (
              <button
                key={val}
                onClick={() => handleQuick(val)}
                className={`py-2 rounded-xl text-sm font-semibold border transition-all duration-150
                  ${amount === String(val)
                    ? "bg-gradient-primary text-white border-transparent shadow-glow"
                    : "border-gray-200 dark:border-dark-border text-gray-700 dark:text-gray-300 hover:border-[#FF7E5F] hover:text-[#FF7E5F]"
                  }`}
              >
                €{val}
              </button>
            ))}
          </div>
        </div>

        {/* Custom amount input */}
        <div>
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">
            Or enter a custom amount
          </p>
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm font-medium">€</span>
            <input
              type="number"
              min="1"
              max="1000"
              step="0.01"
              placeholder="0.00"
              value={amount}
              onChange={(e) => { setAmount(e.target.value); setAmountError(""); setShowComingSoon(false); }}
              className="w-full pl-7 pr-4 py-2.5 rounded-xl border border-gray-200 dark:border-dark-border
                bg-gray-50 dark:bg-dark-bg text-sm text-gray-800 dark:text-gray-100
                outline-none focus:border-[#FF7E5F] focus:ring-1 focus:ring-[#FF7E5F]/30 transition-all"
            />
          </div>
          {amountError
            ? <p className="text-xs text-red-500 mt-1.5">{amountError}</p>
            : <p className="text-xs text-gray-400 dark:text-gray-500 mt-1.5">Min €1.00 · Max €1,000.00</p>
          }
        </div>

        {/* Coming soon notice */}
        {showComingSoon && (
          <div className="rounded-xl border border-[#FF7E5F]/30 bg-[#FF7E5F]/10 px-4 py-3 flex items-start gap-2.5">
            <FontAwesomeIcon icon={faClock} className="text-[#FF7E5F] mt-0.5 text-sm flex-shrink-0" />
            <div>
              <p className="text-sm font-medium text-gray-800 dark:text-gray-100">
                Card payments are not available yet
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 leading-relaxed">
                This feature is coming soon. We'll enable it shortly — stay tuned!
              </p>
            </div>
          </div>
        )}

        {/* Pay button */}
        <button
          onClick={handlePayClick}
          className="w-full flex items-center justify-center gap-2.5 py-3 rounded-xl
            text-sm font-semibold text-white bg-gradient-primary shadow-glow
            hover:shadow-glow-lg transition-all duration-200"
        >
          <FontAwesomeIcon icon={faCreditCard} className="text-sm" />
          Pay with card
          {amount && !isNaN(parseFloat(amount)) && parseFloat(amount) > 0 && (
            <span className="opacity-80">· €{parseFloat(amount).toFixed(2)}</span>
          )}
        </button>

        <p className="text-center text-xs text-gray-400 dark:text-gray-500">
          Payments powered by Stripe · Coming soon
        </p>
      </div>
    </div>,
    document.body
  );
}

function CreditTab() {
  const wallet = WALLET_PLACEHOLDER;
  const [modalOpen, setModalOpen] = useState(false);

  const currencySymbol = wallet.currency === "EUR" ? "€" : "$";

  return (
    <div className="space-y-6">
      {/* Balance card */}
      <div className="relative overflow-hidden rounded-xl bg-gradient-primary p-6 text-white">
        <div className="absolute top-0 right-0 w-32 h-32 -mr-8 -mt-8 rounded-full bg-white/10" />
        <div className="absolute bottom-0 left-0 w-24 h-24 -ml-6 -mb-6 rounded-full bg-white/10" />
        <div className="relative flex items-end justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <FontAwesomeIcon icon={faWallet} className="text-sm opacity-80" />
              <span className="text-sm font-medium opacity-80">Available Balance</span>
            </div>
            {wallet.loading ? (
              <div className="h-10 w-28 bg-white/20 rounded-lg animate-pulse mt-1" />
            ) : (
              <p className="text-4xl font-bold tracking-tight">
                {currencySymbol}{parseFloat(wallet.balance).toFixed(2)}
              </p>
            )}
            <p className="text-sm mt-1 opacity-70">{wallet.currency}</p>
          </div>
          <button
            onClick={() => setModalOpen(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white/20 hover:bg-white/30
              text-white text-sm font-semibold transition-colors backdrop-blur-sm"
          >
            <FontAwesomeIcon icon={faArrowUp} className="text-xs" />
            Add funds
          </button>
        </div>
      </div>

      {/* Info notice */}
      <div className="rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-4
        flex items-start gap-3">
        <FontAwesomeIcon icon={faCreditCard} className="text-gray-400 mt-0.5 text-sm flex-shrink-0" />
        <div>
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Card payments coming soon</p>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 leading-relaxed">
            Top-up via card will be available shortly. Your balance will be used to run automations
            once usage-based billing is live.
          </p>
        </div>
      </div>

      <AddFundsModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </div>
  );
}

// ── Invoices Tab ─────────────────────────────────────────────────────

function txStatusIcon(status: string) {
  if (status === "completed")
    return <FontAwesomeIcon icon={faCheckCircle} className="text-green-500 text-xs" />;
  if (status === "failed" || status === "refunded")
    return <FontAwesomeIcon icon={faTimesCircle} className="text-red-500 text-xs" />;
  return <FontAwesomeIcon icon={faClock} className="text-yellow-500 text-xs" />;
}

function txLabel(type: string) {
  if (type === "topup_credit") return "Top-up";
  if (type === "topup_refund") return "Refund";
  if (type === "adjustment") return "Adjustment";
  return type;
}

function InvoicesTab() {
  const wallet = WALLET_PLACEHOLDER;
  const transactions: TransactionData[] = [];
  const txTotal = 0;
  const loading = false;
  const [page, setPage] = useState(1);
  const LIMIT = 10;

  const currencySymbol = wallet.currency === "EUR" ? "€" : "$";
  const totalPages = Math.ceil(txTotal / LIMIT);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200">
          Transaction history
          {txTotal > 0 && (
            <span className="ml-1.5 text-xs font-normal text-gray-400">({txTotal})</span>
          )}
        </h3>
      </div>

      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-14 rounded-xl bg-gray-100 dark:bg-dark-bg animate-pulse" />
          ))}
        </div>
      ) : transactions.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-14 gap-3 text-gray-400 dark:text-gray-500">
          <FontAwesomeIcon icon={faReceipt} className="text-3xl opacity-30" />
          <p className="text-sm">No invoices yet.</p>
          <p className="text-xs text-center max-w-xs">
            Your payment history will appear here once you add funds to your wallet.
          </p>
        </div>
      ) : (
        <>
          <div className="divide-y divide-gray-100 dark:divide-dark-border rounded-xl border
            border-gray-200 dark:border-dark-border overflow-hidden">
            {transactions.map((tx) => (
              <div
                key={tx.id}
                className="flex items-center justify-between px-4 py-3.5
                  bg-white dark:bg-dark-surface hover:bg-gray-50 dark:hover:bg-dark-bg transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className="w-7 h-7 rounded-lg bg-gray-100 dark:bg-dark-border flex items-center justify-center flex-shrink-0">
                    {txStatusIcon(tx.status)}
                  </div>
                  <div>
                    <p className="text-sm font-medium text-gray-800 dark:text-gray-200">
                      {txLabel(tx.type)}
                    </p>
                    <p className="text-xs text-gray-400 dark:text-gray-500">
                      {new Date(tx.created_at).toLocaleDateString(undefined, {
                        month: "short", day: "numeric", year: "numeric",
                      })}
                      <span className="mx-1.5">·</span>
                      <span className="capitalize">{tx.status}</span>
                    </p>
                  </div>
                </div>
                <span className="text-sm font-semibold text-gray-800 dark:text-gray-200 tabular-nums">
                  +{currencySymbol}{parseFloat(tx.amount).toFixed(2)}
                </span>
              </div>
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between pt-1">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1.5 rounded-lg text-xs font-medium text-gray-600 dark:text-gray-300
                  border border-gray-200 dark:border-dark-border hover:bg-gray-100 dark:hover:bg-dark-border
                  disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Previous
              </button>
              <span className="text-xs text-gray-400">
                Page {page} of {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="px-3 py-1.5 rounded-lg text-xs font-medium text-gray-600 dark:text-gray-300
                  border border-gray-200 dark:border-dark-border hover:bg-gray-100 dark:hover:bg-dark-border
                  disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── Tab Content Router ──────────────────────────────────────────────

function TabContent({ tab }: { tab: TabId }) {
  if (tab === "profiles") return <ProfilesTab />;
  if (tab === "api-keys") return <APIKeysTab />;
  if (tab === "credit") return <CreditTab />;
  if (tab === "invoices") return <InvoicesTab />;
  return null;
}

// ── Settings Page ───────────────────────────────────────────────────

export default function Settings(): React.ReactElement {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = (searchParams.get("tab") as TabId) || "profiles";
  const wallet = WALLET_PLACEHOLDER;

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
            <span>
              {wallet.currency === "EUR" ? "€" : "$"}
              {parseFloat(wallet.balance).toFixed(2)}
            </span>
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
