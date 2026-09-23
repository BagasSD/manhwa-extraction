import React, { useState } from "react";
import type { KnownCharacter } from "../../types/context";

interface CharacterRosterModalProps {
  characters: KnownCharacter[];
  onClose: () => void;
  onRename: (oldId: string, newId: string, name?: string, description?: string) => Promise<void>;
  onMerge: (sourceId: string, targetId: string, description?: string) => Promise<void>;
  onSelectPage: (pageNum: number) => void;
}

export const CharacterRosterModal: React.FC<CharacterRosterModalProps> = ({
  characters,
  onClose,
  onRename,
  onMerge,
  onSelectPage,
}) => {
  const [activeTab, setActiveTab] = useState<"list" | "rename" | "merge">("list");

  // Rename form state
  const [oldId, setOldId] = useState("");
  const [newId, setNewId] = useState("");
  const [nameOverride, setNameOverride] = useState("");
  const [descOverride, setDescOverride] = useState("");

  // Merge form state
  const [sourceId, setSourceId] = useState("");
  const [targetId, setTargetId] = useState("");
  const [mergedDesc, setMergedDesc] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const startRename = (char: KnownCharacter) => {
    setOldId(char.id);
    setNewId(char.id);
    setNameOverride(char.name || "");
    setDescOverride(char.description || "");
    setActiveTab("rename");
    setError(null);
    setSuccessMsg(null);
  };

  const startMerge = (char: KnownCharacter) => {
    setSourceId(char.id);
    setTargetId("");
    setMergedDesc(char.description || "");
    setActiveTab("merge");
    setError(null);
    setSuccessMsg(null);
  };

  const handleRenameSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!oldId || !newId) return;
    try {
      setLoading(true);
      setError(null);
      await onRename(oldId, newId, nameOverride || undefined, descOverride || undefined);
      setSuccessMsg(`Character '${oldId}' successfully renamed to '${newId}' across chapter.`);
      setTimeout(() => {
        setActiveTab("list");
        setSuccessMsg(null);
      }, 1500);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleMergeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sourceId || !targetId) return;
    try {
      setLoading(true);
      setError(null);
      await onMerge(sourceId, targetId, mergedDesc || undefined);
      setSuccessMsg(`Merged '${sourceId}' into '${targetId}' across all pages.`);
      setTimeout(() => {
        setActiveTab("list");
        setSuccessMsg(null);
      }, 1500);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: "rgba(0,0,0,0.6)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div
        style={{
          backgroundColor: "#fff",
          borderRadius: "8px",
          width: "650px",
          maxWidth: "90vw",
          maxHeight: "85vh",
          display: "flex",
          flexDirection: "column",
          boxShadow: "0 20px 25px -5px rgba(0,0,0,0.2)",
          overflow: "hidden",
        }}
      >
        {/* Modal Header */}
        <div
          style={{
            padding: "1rem 1.5rem",
            backgroundColor: "#1e293b",
            color: "#fff",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
            <h3 style={{ margin: 0, fontSize: "1.15rem" }}>Character Roster & Tracking</h3>
            <div style={{ display: "flex", gap: "0.25rem" }}>
              <button
                type="button"
                onClick={() => setActiveTab("list")}
                style={{
                  padding: "3px 8px",
                  fontSize: "0.8rem",
                  backgroundColor: activeTab === "list" ? "#3b82f6" : "#334155",
                  color: "#fff",
                  border: "none",
                  borderRadius: "4px",
                  cursor: "pointer",
                }}
              >
                Roster ({characters.length})
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("merge")}
                style={{
                  padding: "3px 8px",
                  fontSize: "0.8rem",
                  backgroundColor: activeTab === "merge" ? "#3b82f6" : "#334155",
                  color: "#fff",
                  border: "none",
                  borderRadius: "4px",
                  cursor: "pointer",
                }}
              >
                Merge
              </button>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              color: "#cbd5e1",
              fontSize: "1.2rem",
              cursor: "pointer",
            }}
          >
            ✕
          </button>
        </div>

        {/* Feedback Alerts */}
        {error && (
          <div style={{ padding: "0.75rem 1.5rem", backgroundColor: "#fee2e2", color: "#991b1b", fontSize: "0.85rem" }}>
            {error}
          </div>
        )}
        {successMsg && (
          <div style={{ padding: "0.75rem 1.5rem", backgroundColor: "#dcfce7", color: "#166534", fontSize: "0.85rem" }}>
            ✓ {successMsg}
          </div>
        )}

        {/* Modal Body */}
        <div style={{ flex: 1, overflowY: "auto", padding: "1.5rem" }}>
          {activeTab === "list" && (
            <div>
              {characters.length === 0 ? (
                <div style={{ textAlign: "center", color: "#64748b", padding: "2rem 0" }}>
                  No characters recorded in this chapter yet.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                  {characters.map((char) => (
                    <div
                      key={char.id}
                      style={{
                        border: "1px solid #e2e8f0",
                        borderRadius: "6px",
                        padding: "0.75rem 1rem",
                        backgroundColor: "#f8fafc",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                      }}
                    >
                      <div>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                          <span
                            style={{
                              backgroundColor: "#0284c7",
                              color: "#fff",
                              fontWeight: 700,
                              fontSize: "0.85rem",
                              padding: "2px 6px",
                              borderRadius: "4px",
                            }}
                          >
                            {char.id}
                          </span>
                          {char.name && (
                            <span style={{ fontWeight: 600, fontSize: "0.95rem", color: "#0f172a" }}>
                              {char.name}
                            </span>
                          )}
                          <span style={{ fontSize: "0.8rem", color: "#64748b" }}>
                            ({char.occurrences} {char.occurrences === 1 ? "page" : "pages"})
                          </span>
                        </div>

                        <div style={{ fontSize: "0.85rem", color: "#334155", marginTop: "0.3rem" }}>
                          {char.description || <span style={{ color: "#94a3b8" }}>No description</span>}
                        </div>

                        <div style={{ fontSize: "0.75rem", color: "#64748b", marginTop: "0.3rem" }}>
                          Appears on:{" "}
                          {char.pages.slice(0, 10).map((p) => (
                            <button
                              key={`jump-${p}`}
                              type="button"
                              onClick={() => {
                                onSelectPage(p);
                                onClose();
                              }}
                              style={{
                                background: "none",
                                border: "none",
                                color: "#2563eb",
                                textDecoration: "underline",
                                cursor: "pointer",
                                padding: "0 3px",
                                fontSize: "0.75rem",
                              }}
                            >
                              p{p}
                            </button>
                          ))}
                          {char.pages.length > 10 && ` +${char.pages.length - 10} more`}
                        </div>
                      </div>

                      <div style={{ display: "flex", gap: "0.4rem" }}>
                        <button
                          type="button"
                          onClick={() => startRename(char)}
                          style={{
                            padding: "4px 8px",
                            fontSize: "0.8rem",
                            backgroundColor: "#e2e8f0",
                            border: "none",
                            borderRadius: "4px",
                            cursor: "pointer",
                            fontWeight: 500,
                          }}
                        >
                          Rename
                        </button>
                        <button
                          type="button"
                          onClick={() => startMerge(char)}
                          style={{
                            padding: "4px 8px",
                            fontSize: "0.8rem",
                            backgroundColor: "#e2e8f0",
                            border: "none",
                            borderRadius: "4px",
                            cursor: "pointer",
                            fontWeight: 500,
                          }}
                        >
                          Merge
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Tab: Rename Character */}
          {activeTab === "rename" && (
            <form onSubmit={handleRenameSubmit} style={{ display: "grid", gap: "1rem" }}>
              <h4>Rename Character Across Chapter</h4>
              <div>
                <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.25rem" }}>
                  Current ID
                </label>
                <input
                  type="text"
                  disabled
                  value={oldId}
                  style={{ width: "100%", padding: "0.5rem", borderRadius: "4px", border: "1px solid #cbd5e1", backgroundColor: "#f1f5f9" }}
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.25rem" }}>
                  New ID
                </label>
                <input
                  type="text"
                  required
                  value={newId}
                  onChange={(e) => setNewId(e.target.value)}
                  placeholder="e.g. c1 or jinwoo"
                  style={{ width: "100%", padding: "0.5rem", borderRadius: "4px", border: "1px solid #cbd5e1", boxSizing: "border-box" }}
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.25rem" }}>
                  Canonical Name (Optional)
                </label>
                <input
                  type="text"
                  value={nameOverride}
                  onChange={(e) => setNameOverride(e.target.value)}
                  placeholder="e.g. Sung Jin-Woo"
                  style={{ width: "100%", padding: "0.5rem", borderRadius: "4px", border: "1px solid #cbd5e1", boxSizing: "border-box" }}
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.25rem" }}>
                  Description (Optional)
                </label>
                <input
                  type="text"
                  value={descOverride}
                  onChange={(e) => setDescOverride(e.target.value)}
                  placeholder="e.g. black-haired protagonist"
                  style={{ width: "100%", padding: "0.5rem", borderRadius: "4px", border: "1px solid #cbd5e1", boxSizing: "border-box" }}
                />
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
                <button
                  type="button"
                  onClick={() => setActiveTab("list")}
                  style={{ padding: "0.5rem 1rem", border: "1px solid #cbd5e1", borderRadius: "4px", background: "#fff", cursor: "pointer" }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  style={{ padding: "0.5rem 1.25rem", backgroundColor: "#2563eb", color: "#fff", border: "none", borderRadius: "4px", fontWeight: 600, cursor: "pointer" }}
                >
                  {loading ? "Renaming..." : "Apply Rename"}
                </button>
              </div>
            </form>
          )}

          {/* Tab: Merge Characters */}
          {activeTab === "merge" && (
            <form onSubmit={handleMergeSubmit} style={{ display: "grid", gap: "1rem" }}>
              <h4>Merge Characters Across Chapter</h4>
              <p style={{ fontSize: "0.85rem", color: "#64748b", margin: 0 }}>
                This will replace all instances of the source character with the target character across all pages.
              </p>

              <div>
                <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.25rem" }}>
                  Source ID (to be merged away)
                </label>
                <select
                  value={sourceId}
                  onChange={(e) => setSourceId(e.target.value)}
                  required
                  style={{ width: "100%", padding: "0.5rem", borderRadius: "4px", border: "1px solid #cbd5e1" }}
                >
                  <option value="">-- Select Source Character --</option>
                  {characters.map((c) => (
                    <option key={`src-${c.id}`} value={c.id}>
                      {c.id} {c.description ? `(${c.description})` : ""}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.25rem" }}>
                  Target ID (to keep)
                </label>
                <select
                  value={targetId}
                  onChange={(e) => setTargetId(e.target.value)}
                  required
                  style={{ width: "100%", padding: "0.5rem", borderRadius: "4px", border: "1px solid #cbd5e1" }}
                >
                  <option value="">-- Select Target Character --</option>
                  {characters
                    .filter((c) => c.id !== sourceId)
                    .map((c) => (
                      <option key={`tgt-${c.id}`} value={c.id}>
                        {c.id} {c.description ? `(${c.description})` : ""}
                      </option>
                    ))}
                </select>
              </div>

              <div>
                <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.25rem" }}>
                  Merged Description (Optional)
                </label>
                <input
                  type="text"
                  value={mergedDesc}
                  onChange={(e) => setMergedDesc(e.target.value)}
                  placeholder="Unified visual description"
                  style={{ width: "100%", padding: "0.5rem", borderRadius: "4px", border: "1px solid #cbd5e1", boxSizing: "border-box" }}
                />
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
                <button
                  type="button"
                  onClick={() => setActiveTab("list")}
                  style={{ padding: "0.5rem 1rem", border: "1px solid #cbd5e1", borderRadius: "4px", background: "#fff", cursor: "pointer" }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading || !sourceId || !targetId}
                  style={{
                    padding: "0.5rem 1.25rem",
                    backgroundColor: "#dc2626",
                    color: "#fff",
                    border: "none",
                    borderRadius: "4px",
                    fontWeight: 600,
                    cursor: loading ? "not-allowed" : "pointer",
                  }}
                >
                  {loading ? "Merging..." : "Merge Characters"}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
};
