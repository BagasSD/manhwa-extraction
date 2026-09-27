import React, { useCallback, useEffect, useState } from "react";
import type { ChapterSummary, MultiChapterJobStatus } from "../../types/context";
import {
  cancelMultiExtraction,
  getMultiExtractStatus,
  startMultiChapterExtraction,
} from "../../services/api";

interface ChapterListProps {
  chapters: ChapterSummary[];
  onSelectChapter: (id: string) => void;
  onCreateChapter: (data: { title: string; source_path: string }) => Promise<void>;
  onDownloadChapter?: (data: { url: string; title?: string; id?: string }) => Promise<void>;
  onRefresh?: () => void;
  loading: boolean;
}

interface UrlRow {
  id: string;
  chapterNum: string;
  url: string;
  status: "idle" | "downloading" | "done" | "error";
  error?: string;
}

const makeRow = (): UrlRow => ({
  id: Math.random().toString(36).slice(2),
  chapterNum: "",
  url: "",
  status: "idle",
});

export const ChapterList: React.FC<ChapterListProps> = ({
  chapters,
  onSelectChapter,
  onCreateChapter,
  onDownloadChapter,
  onRefresh,
  loading,
}) => {
  const [showModal, setShowModal] = useState(false);
  const [showDownloadModal, setShowDownloadModal] = useState(false);
  const [showBulkModal, setShowBulkModal] = useState(false);

  // Multi-chapter selection state
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [skipCompleted, setSkipCompleted] = useState(true);
  const [forceAll, setForceAll] = useState(false);
  const [bulkStarting, setBulkStarting] = useState(false);
  const [bulkError, setBulkError] = useState<string | null>(null);

  // Multi-chapter running status
  const [multiJob, setMultiJob] = useState<MultiChapterJobStatus | null>(null);
  const [cancellingJob, setCancellingJob] = useState(false);

  // Local folder registration state
  const [title, setTitle] = useState("");
  const [sourcePath, setSourcePath] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Bulk URL download state
  const [downloadTitle, setDownloadTitle] = useState("");
  const [urlRows, setUrlRows] = useState<UrlRow[]>([makeRow()]);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  // Check multi-extract status on mount and poll when running
  const fetchJobStatus = useCallback(async () => {
    try {
      const status = await getMultiExtractStatus();
      setMultiJob(status);
      return status;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    fetchJobStatus();
  }, [fetchJobStatus]);

  useEffect(() => {
    if (!multiJob || multiJob.status !== "running") return;
    const interval = setInterval(async () => {
      const status = await fetchJobStatus();
      if (status && status.status !== "running") {
        clearInterval(interval);
        if (onRefresh) onRefresh();
      }
    }, 1500);
    return () => clearInterval(interval);
  }, [multiJob, fetchJobStatus, onRefresh]);

  const handleCancelMultiJob = async () => {
    try {
      setCancellingJob(true);
      const res = await cancelMultiExtraction();
      setMultiJob(res);
      if (onRefresh) onRefresh();
    } catch (err) {
      console.error("Failed to cancel multi-extract:", err);
    } finally {
      setCancellingJob(false);
    }
  };

  const toggleSelectChapter = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleSelectAll = () => {
    setSelectedIds(new Set(chapters.map((c) => c.id)));
  };

  const handleDeselectAll = () => {
    setSelectedIds(new Set());
  };

  const handleStartBulkOcr = async () => {
    if (selectedIds.size === 0) return;
    // Keep chapters in their listed order
    const orderedIds = chapters.filter((c) => selectedIds.has(c.id)).map((c) => c.id);

    try {
      setBulkStarting(true);
      setBulkError(null);
      const status = await startMultiChapterExtraction({
        chapter_ids: orderedIds,
        skip_completed: skipCompleted,
        force_all: forceAll,
      });
      setMultiJob(status);
      setShowBulkModal(false);
      setSelectMode(false);
      setSelectedIds(new Set());
    } catch (err) {
      setBulkError((err as Error).message);
    } finally {
      setBulkStarting(false);
    }
  };

  const addRow = () => setUrlRows((prev) => [...prev, makeRow()]);
  const removeRow = (id: string) =>
    setUrlRows((prev) => (prev.length > 1 ? prev.filter((r) => r.id !== id) : prev));
  const updateRow = (id: string, patch: Partial<UrlRow>) =>
    setUrlRows((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !sourcePath.trim()) return;
    try {
      setSubmitting(true);
      setError(null);
      await onCreateChapter({ title: title.trim(), source_path: sourcePath.trim() });
      setTitle("");
      setSourcePath("");
      setShowModal(false);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleBulkDownload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!onDownloadChapter) return;

    const validRows = urlRows.filter((r) => r.url.trim());
    if (validRows.length === 0) return;

    setDownloading(true);
    setDownloadError(null);

    for (const row of validRows) {
      updateRow(row.id, { status: "downloading", error: undefined });
      const chNum = row.chapterNum.trim();
      const titleSuffix = chNum ? ` - ${chNum.padStart(2, "0")}` : "";
      const fullTitle = downloadTitle.trim()
        ? `${downloadTitle.trim()}${titleSuffix}`
        : undefined;
      try {
        await onDownloadChapter({ url: row.url.trim(), title: fullTitle });
        updateRow(row.id, { status: "done" });
      } catch (err) {
        updateRow(row.id, { status: "error", error: (err as Error).message });
      }
    }

    setDownloading(false);
  };

  const resetDownloadModal = () => {
    setDownloadTitle("");
    setUrlRows([makeRow()]);
    setDownloadError(null);
    setShowDownloadModal(false);
  };

  const selectedChaptersList = chapters.filter((c) => selectedIds.has(c.id));
  const isMultiJobActive = multiJob && multiJob.status === "running";

  return (
    <div style={{ maxWidth: "900px", margin: "0 auto", padding: "1.5rem" }}>
      {/* ── Active / Recent Bulk OCR Banner ────────────────────────────────── */}
      {multiJob && multiJob.status !== "idle" && (
        <div
          style={{
            marginBottom: "1.5rem",
            padding: "1rem 1.25rem",
            borderRadius: "8px",
            border: `1px solid ${
              multiJob.status === "running"
                ? "#818cf8"
                : multiJob.status === "completed"
                ? "#86efac"
                : multiJob.status === "cancelled"
                ? "#cbd5e1"
                : "#fca5a5"
            }`,
            backgroundColor:
              multiJob.status === "running"
                ? "#eef2ff"
                : multiJob.status === "completed"
                ? "#f0fdf4"
                : multiJob.status === "cancelled"
                ? "#f8fafc"
                : "#fef2f2",
            boxShadow: "0 2px 4px rgba(0,0,0,0.05)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem" }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <span style={{ fontSize: "1.1rem" }}>
                  {multiJob.status === "running"
                    ? "⚡"
                    : multiJob.status === "completed"
                    ? "✅"
                    : multiJob.status === "cancelled"
                    ? "⏹️"
                    : "⚠️"}
                </span>
                <strong style={{ fontSize: "0.95rem", color: "#1e1b4b" }}>
                  {multiJob.status === "running"
                    ? `Bulk OCR Running (${multiJob.current_chapter_index + 1} / ${multiJob.total_chapters} chapters)`
                    : multiJob.status === "completed"
                    ? "Bulk OCR Completed"
                    : multiJob.status === "cancelled"
                    ? "Bulk OCR Cancelled"
                    : "Bulk OCR Failed"}
                </strong>
                <span
                  style={{
                    fontSize: "0.75rem",
                    fontWeight: 600,
                    padding: "2px 6px",
                    borderRadius: "10px",
                    textTransform: "uppercase",
                    backgroundColor:
                      multiJob.status === "running"
                        ? "#c7d2fe"
                        : multiJob.status === "completed"
                        ? "#bbf7d0"
                        : "#e2e8f0",
                    color:
                      multiJob.status === "running"
                        ? "#3730a3"
                        : multiJob.status === "completed"
                        ? "#166534"
                        : "#475569",
                  }}
                >
                  {multiJob.status}
                </span>
              </div>
              <p style={{ margin: "0.35rem 0 0", fontSize: "0.85rem", color: "#334155" }}>
                {multiJob.message || "Processing chapters sequentially with shared character roster..."}
              </p>
              {multiJob.status === "running" && (
                <div style={{ margin: "0.25rem 0 0", fontSize: "0.8rem", color: "#64748b" }}>
                  Extracted {multiJob.total_pages_completed} pages total • Current chapter: page{" "}
                  {multiJob.current_page || 0} / {multiJob.total_pages_current_chapter}
                </div>
              )}
            </div>

            <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
              {multiJob.status === "running" ? (
                <button
                  type="button"
                  onClick={handleCancelMultiJob}
                  disabled={cancellingJob}
                  style={{
                    backgroundColor: "#ef4444",
                    color: "#fff",
                    border: "none",
                    borderRadius: "4px",
                    padding: "4px 10px",
                    fontSize: "0.8rem",
                    fontWeight: 600,
                    cursor: cancellingJob ? "not-allowed" : "pointer",
                    opacity: cancellingJob ? 0.6 : 1,
                  }}
                >
                  {cancellingJob ? "Stopping..." : "Cancel"}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => setMultiJob(null)}
                  style={{
                    backgroundColor: "#e2e8f0",
                    color: "#475569",
                    border: "none",
                    borderRadius: "4px",
                    padding: "4px 8px",
                    fontSize: "0.8rem",
                    cursor: "pointer",
                  }}
                >
                  Dismiss
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Main Top Bar ───────────────────────────────────────────────────── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: "1.5rem", fontWeight: 700 }}>Chapters</h2>
          <p style={{ margin: "0.25rem 0 0", color: "#666", fontSize: "0.9rem" }}>
            Select chapters to review, bulk OCR with shared character context, or download from web.
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
          <button
            type="button"
            onClick={() => {
              setSelectMode(!selectMode);
              if (selectMode) setSelectedIds(new Set());
            }}
            style={{
              backgroundColor: selectMode ? "#475569" : "#f1f5f9",
              color: selectMode ? "#fff" : "#334155",
              border: "1px solid #cbd5e1",
              borderRadius: "6px",
              padding: "0.6rem 1rem",
              fontSize: "0.95rem",
              fontWeight: 600,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "0.4rem",
            }}
          >
            <span>{selectMode ? "✕ Exit Select" : "☑️ Select Chapters"}</span>
          </button>

          <button
            type="button"
            onClick={() => setShowDownloadModal(true)}
            style={{
              backgroundColor: "#059669",
              color: "#fff",
              border: "none",
              borderRadius: "6px",
              padding: "0.6rem 1.2rem",
              fontSize: "0.95rem",
              fontWeight: 600,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "0.4rem",
            }}
          >
            <span>📥</span> Download from URL
          </button>
          <button
            type="button"
            onClick={() => setShowModal(true)}
            style={{
              backgroundColor: "#2563eb",
              color: "#fff",
              border: "none",
              borderRadius: "6px",
              padding: "0.6rem 1.2rem",
              fontSize: "0.95rem",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            + Add Local Folder
          </button>
        </div>
      </div>

      {/* ── Selection Action Bar ───────────────────────────────────────────── */}
      {selectMode && (
        <div
          style={{
            backgroundColor: "#f8fafc",
            border: "1px solid #cbd5e1",
            borderRadius: "8px",
            padding: "0.75rem 1.25rem",
            marginBottom: "1rem",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
            <span style={{ fontWeight: 600, fontSize: "0.9rem", color: "#1e293b" }}>
              {selectedIds.size} of {chapters.length} selected
            </span>
            <button
              type="button"
              onClick={handleSelectAll}
              style={{
                background: "none",
                border: "none",
                color: "#2563eb",
                cursor: "pointer",
                fontSize: "0.85rem",
                textDecoration: "underline",
                padding: 0,
              }}
            >
              Select All
            </button>
            <button
              type="button"
              onClick={handleDeselectAll}
              style={{
                background: "none",
                border: "none",
                color: "#64748b",
                cursor: "pointer",
                fontSize: "0.85rem",
                textDecoration: "underline",
                padding: 0,
              }}
            >
              Deselect All
            </button>
          </div>

          <button
            type="button"
            onClick={() => setShowBulkModal(true)}
            disabled={selectedIds.size === 0 || isMultiJobActive}
            style={{
              backgroundColor: selectedIds.size > 0 && !isMultiJobActive ? "#4f46e5" : "#94a3b8",
              color: "#fff",
              border: "none",
              borderRadius: "6px",
              padding: "0.55rem 1.25rem",
              fontWeight: 600,
              fontSize: "0.9rem",
              cursor: selectedIds.size > 0 && !isMultiJobActive ? "pointer" : "not-allowed",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
            }}
          >
            <span>⚡</span> Bulk OCR ({selectedIds.size})
          </button>
        </div>
      )}

      {loading && <p style={{ color: "#666" }}>Loading chapters...</p>}

      {!loading && chapters.length === 0 && (
        <div
          style={{
            border: "2px dashed #e2e8f0",
            borderRadius: "8px",
            padding: "3rem 1.5rem",
            textAlign: "center",
            color: "#64748b",
          }}
        >
          <p style={{ fontSize: "1.1rem", margin: "0 0 1rem" }}>No chapters created yet.</p>
          <button
            type="button"
            onClick={() => setShowModal(true)}
            style={{
              backgroundColor: "#2563eb",
              color: "#fff",
              border: "none",
              borderRadius: "6px",
              padding: "0.5rem 1rem",
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            Create Your First Chapter
          </button>
        </div>
      )}

      <div style={{ display: "grid", gap: "1rem" }}>
        {chapters.map((ch) => {
          const progressPercent =
            ch.total_pages > 0 ? Math.round((ch.completed_pages / ch.total_pages) * 100) : 0;
          const isSelected = selectedIds.has(ch.id);

          return (
            <div
              key={ch.id}
              onClick={() => {
                if (selectMode) {
                  toggleSelectChapter(ch.id);
                } else {
                  onSelectChapter(ch.id);
                }
              }}
              style={{
                border: isSelected ? "2px solid #4f46e5" : "1px solid #e2e8f0",
                borderRadius: "8px",
                padding: "1.25rem",
                backgroundColor: isSelected ? "#f5f3ff" : "#fff",
                boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
                cursor: "pointer",
                transition: "border-color 0.15s, box-shadow 0.15s, background-color 0.15s",
                display: "flex",
                gap: "1rem",
                alignItems: "flex-start",
              }}
            >
              {selectMode && (
                <div style={{ marginTop: "0.25rem" }}>
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => toggleSelectChapter(ch.id)}
                    style={{ width: "18px", height: "18px", cursor: "pointer" }}
                  />
                </div>
              )}

              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div>
                    <h3 style={{ margin: "0 0 0.25rem", fontSize: "1.2rem" }}>{ch.title}</h3>
                    <div style={{ fontSize: "0.85rem", color: "#64748b", fontFamily: "monospace" }}>
                      {ch.source_path}
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <span
                      style={{
                        display: "inline-block",
                        padding: "0.25rem 0.6rem",
                        borderRadius: "12px",
                        fontSize: "0.8rem",
                        fontWeight: 600,
                        backgroundColor: progressPercent === 100 ? "#dcfce7" : "#eff6ff",
                        color: progressPercent === 100 ? "#166534" : "#1e40af",
                      }}
                    >
                      {ch.completed_pages} / {ch.total_pages} pages ({progressPercent}%)
                    </span>
                  </div>
                </div>

                {/* Progress bar */}
                <div
                  style={{
                    height: "6px",
                    backgroundColor: "#f1f5f9",
                    borderRadius: "3px",
                    marginTop: "1rem",
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      height: "100%",
                      width: `${progressPercent}%`,
                      backgroundColor: progressPercent === 100 ? "#22c55e" : "#3b82f6",
                      transition: "width 0.3s ease",
                    }}
                  />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Modal: Register local chapter ─────────────────────────────── */}
      {showModal && (
        <div
          style={{
            position: "fixed",
            top: 0, left: 0, right: 0, bottom: 0,
            backgroundColor: "rgba(0,0,0,0.5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            style={{
              backgroundColor: "#fff",
              color: "#0f172a",
              borderRadius: "8px",
              padding: "2rem",
              width: "100%",
              maxWidth: "500px",
              boxShadow: "0 10px 25px rgba(0,0,0,0.15)",
            }}
          >
            <h3 style={{ margin: "0 0 1.25rem", fontSize: "1.25rem", color: "#0f172a" }}>Register New Chapter</h3>

            {error && (
              <div
                style={{
                  padding: "0.75rem",
                  marginBottom: "1rem",
                  backgroundColor: "#fee2e2",
                  color: "#991b1b",
                  borderRadius: "6px",
                  fontSize: "0.85rem",
                }}
              >
                {error}
              </div>
            )}
            <form onSubmit={handleSubmit}>
              <div style={{ marginBottom: "1rem" }}>
                <label style={{ display: "block", marginBottom: "0.35rem", fontWeight: 600, fontSize: "0.9rem" }}>
                  Chapter Title
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Chapter 01 - The Awakening"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "0.6rem",
                    borderRadius: "6px",
                    border: "1px solid #cbd5e1",
                    boxSizing: "border-box",
                  }}
                />
              </div>

              <div style={{ marginBottom: "1.5rem" }}>
                <label style={{ display: "block", marginBottom: "0.35rem", fontWeight: 600, fontSize: "0.9rem" }}>
                  Source Folder Path
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. /path/to/manhwa/images/chapter_01"
                  value={sourcePath}
                  onChange={(e) => setSourcePath(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "0.6rem",
                    borderRadius: "6px",
                    border: "1px solid #cbd5e1",
                    boxSizing: "border-box",
                  }}
                />
                <span style={{ fontSize: "0.8rem", color: "#64748b" }}>
                  Folder containing page image files (.png, .jpg, .webp).
                </span>
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  disabled={submitting}
                  style={{
                    padding: "0.6rem 1rem",
                    borderRadius: "6px",
                    border: "1px solid #cbd5e1",
                    backgroundColor: "#fff",
                    cursor: "pointer",
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  style={{
                    padding: "0.6rem 1.25rem",
                    borderRadius: "6px",
                    border: "none",
                    backgroundColor: "#2563eb",
                    color: "#fff",
                    fontWeight: 600,
                    cursor: submitting ? "not-allowed" : "pointer",
                  }}
                >
                  {submitting ? "Scanning & Registering..." : "Create Chapter"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Modal: Bulk download chapters from URLs ────────────────────── */}
      {showDownloadModal && (
        <div
          style={{
            position: "fixed",
            top: 0, left: 0, right: 0, bottom: 0,
            backgroundColor: "rgba(0,0,0,0.5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            style={{
              backgroundColor: "#fff",
              color: "#0f172a",
              borderRadius: "8px",
              padding: "2rem",
              width: "100%",
              maxWidth: "640px",
              maxHeight: "90vh",
              overflowY: "auto",
              boxShadow: "0 10px 25px rgba(0,0,0,0.15)",
            }}
          >
            {/* Header */}
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
              <span style={{ fontSize: "1.4rem" }}>📥</span>
              <h3 style={{ margin: 0, fontSize: "1.25rem", color: "#0f172a" }}>Bulk Download Chapters</h3>
            </div>
            <p style={{ margin: "0 0 1.25rem", color: "#64748b", fontSize: "0.85rem" }}>
              Add one row per chapter. Titles will be formed as{" "}
              <code>Title - 01</code>, <code>Title - 02</code>, etc.
              Images are stored into <code>data/chapters/</code>.
            </p>

            {downloadError && (
              <div
                style={{
                  padding: "0.75rem",
                  marginBottom: "1rem",
                  backgroundColor: "#fee2e2",
                  color: "#991b1b",
                  borderRadius: "6px",
                  fontSize: "0.85rem",
                }}
              >
                {downloadError}
              </div>
            )}

            <form onSubmit={handleBulkDownload}>
              {/* Shared title prefix */}
              <div style={{ marginBottom: "1.25rem" }}>
                <label style={{ display: "block", marginBottom: "0.35rem", fontWeight: 600, fontSize: "0.9rem" }}>
                  Chapter Title{" "}
                  <span style={{ fontSize: "0.8rem", color: "#94a3b8" }}>(prefix, e.g. "Solo Leveling")</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g. Solo Leveling"
                  value={downloadTitle}
                  onChange={(e) => setDownloadTitle(e.target.value)}
                  disabled={downloading}
                  style={{
                    width: "100%",
                    padding: "0.6rem",
                    borderRadius: "6px",
                    border: "1px solid #cbd5e1",
                    boxSizing: "border-box",
                  }}
                />
              </div>

              {/* Column headers */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "90px 1fr 32px",
                  gap: "0.5rem",
                  marginBottom: "0.35rem",
                }}
              >
                <span style={{ fontSize: "0.8rem", fontWeight: 600, color: "#475569" }}>Chapter #</span>
                <span style={{ fontSize: "0.8rem", fontWeight: 600, color: "#475569" }}>URL</span>
                <span />
              </div>

              {/* URL rows */}
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginBottom: "1rem" }}>
                {urlRows.map((row) => {
                  const statusIcon =
                    row.status === "downloading" ? "⏳"
                    : row.status === "done" ? "✅"
                    : row.status === "error" ? "❌"
                    : null;

                  return (
                    <div key={row.id}>
                      <div
                        style={{
                          display: "grid",
                          gridTemplateColumns: "90px 1fr 32px",
                          gap: "0.5rem",
                          alignItems: "center",
                        }}
                      >
                        {/* Chapter number */}
                        <input
                          type="text"
                          placeholder="01"
                          value={row.chapterNum}
                          onChange={(e) => updateRow(row.id, { chapterNum: e.target.value })}
                          disabled={downloading}
                          style={{
                            padding: "0.55rem 0.5rem",
                            borderRadius: "6px",
                            border: "1px solid #cbd5e1",
                            fontSize: "0.9rem",
                            textAlign: "center",
                          }}
                        />

                        {/* Status icon + URL */}
                        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                          {statusIcon && (
                            <span style={{ fontSize: "1rem", flexShrink: 0 }}>{statusIcon}</span>
                          )}
                          <input
                            type="url"
                            placeholder="https://example.com/read/chapter-1"
                            value={row.url}
                            onChange={(e) => updateRow(row.id, { url: e.target.value })}
                            disabled={downloading}
                            style={{
                              flex: 1,
                              padding: "0.55rem 0.6rem",
                              borderRadius: "6px",
                              border: `1px solid ${
                                row.status === "error" ? "#fca5a5"
                                : row.status === "done" ? "#86efac"
                                : "#cbd5e1"
                              }`,
                              fontSize: "0.9rem",
                            }}
                          />
                        </div>

                        {/* Remove row */}
                        <button
                          type="button"
                          onClick={() => removeRow(row.id)}
                          disabled={downloading || urlRows.length === 1}
                          title="Remove row"
                          style={{
                            width: "32px",
                            height: "32px",
                            borderRadius: "6px",
                            border: "1px solid #e2e8f0",
                            backgroundColor: "#fff",
                            cursor: urlRows.length === 1 || downloading ? "not-allowed" : "pointer",
                            color: "#94a3b8",
                            fontSize: "1rem",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            flexShrink: 0,
                          }}
                        >
                          ✕
                        </button>
                      </div>

                      {/* Inline error message */}
                      {row.status === "error" && row.error && (
                        <p style={{ margin: "0.2rem 0 0 96px", fontSize: "0.75rem", color: "#dc2626" }}>
                          {row.error}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* Add row */}
              <button
                type="button"
                onClick={addRow}
                disabled={downloading}
                style={{
                  width: "100%",
                  padding: "0.5rem",
                  borderRadius: "6px",
                  border: "1px dashed #94a3b8",
                  backgroundColor: "#f8fafc",
                  color: "#475569",
                  fontSize: "0.9rem",
                  cursor: downloading ? "not-allowed" : "pointer",
                  marginBottom: "1.5rem",
                }}
              >
                + Add Chapter URL
              </button>

              {/* Actions */}
              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
                <button
                  type="button"
                  onClick={resetDownloadModal}
                  disabled={downloading}
                  style={{
                    padding: "0.6rem 1rem",
                    borderRadius: "6px",
                    border: "1px solid #cbd5e1",
                    backgroundColor: "#fff",
                    cursor: downloading ? "not-allowed" : "pointer",
                  }}
                >
                  {urlRows.some((r) => r.status === "done") ? "Close" : "Cancel"}
                </button>
                <button
                  type="submit"
                  disabled={downloading || urlRows.every((r) => !r.url.trim())}
                  style={{
                    padding: "0.6rem 1.25rem",
                    borderRadius: "6px",
                    border: "none",
                    backgroundColor: "#059669",
                    color: "#fff",
                    fontWeight: 600,
                    cursor: downloading ? "not-allowed" : "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                  }}
                >
                  {downloading
                    ? `Downloading… (${urlRows.filter((r) => r.status === "done").length}/${urlRows.filter((r) => r.url.trim()).length})`
                    : "Start Download"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Modal: Bulk OCR Configuration ─────────────────────────────────── */}
      {showBulkModal && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: "rgba(0,0,0,0.5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            style={{
              backgroundColor: "#fff",
              color: "#0f172a",
              borderRadius: "8px",
              padding: "2rem",
              width: "100%",
              maxWidth: "580px",
              maxHeight: "90vh",
              overflowY: "auto",
              boxShadow: "0 10px 25px rgba(0,0,0,0.15)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
              <span style={{ fontSize: "1.4rem" }}>⚡</span>
              <h3 style={{ margin: 0, fontSize: "1.25rem", color: "#0f172a" }}>
                Bulk OCR ({selectedChaptersList.length} Chapters)
              </h3>
            </div>
            <p style={{ margin: "0 0 1.25rem", color: "#64748b", fontSize: "0.85rem", lineHeight: 1.4 }}>
              Selected chapters will be processed sequentially in reading order. Character context is shared and accumulated across all chapters.
            </p>

            {bulkError && (
              <div
                style={{
                  padding: "0.75rem",
                  marginBottom: "1rem",
                  backgroundColor: "#fee2e2",
                  color: "#991b1b",
                  borderRadius: "6px",
                  fontSize: "0.85rem",
                }}
              >
                {bulkError}
              </div>
            )}

            {/* Selected chapters list */}
            <div style={{ marginBottom: "1.25rem" }}>
              <label style={{ display: "block", marginBottom: "0.4rem", fontWeight: 600, fontSize: "0.85rem", color: "#334155" }}>
                Chapters to process (in order):
              </label>
              <div
                style={{
                  border: "1px solid #e2e8f0",
                  borderRadius: "6px",
                  maxHeight: "150px",
                  overflowY: "auto",
                  padding: "0.5rem 0.75rem",
                  backgroundColor: "#f8fafc",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.35rem",
                }}
              >
                {selectedChaptersList.map((ch, idx) => (
                  <div
                    key={ch.id}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      fontSize: "0.85rem",
                      color: "#1e293b",
                      paddingBottom: "0.25rem",
                      borderBottom: idx < selectedChaptersList.length - 1 ? "1px solid #f1f5f9" : "none",
                    }}
                  >
                    <span>
                      <strong style={{ color: "#6366f1" }}>{idx + 1}.</strong> {ch.title}
                    </span>
                    <span style={{ color: "#64748b", fontSize: "0.8rem" }}>
                      {ch.completed_pages}/{ch.total_pages} pages
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Options */}
            <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", marginBottom: "1.25rem" }}>
              <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem", cursor: "pointer", color: "#1e293b" }}>
                <input
                  type="checkbox"
                  checked={skipCompleted && !forceAll}
                  disabled={forceAll}
                  onChange={(e) => setSkipCompleted(e.target.checked)}
                />
                <span>Skip already completed pages (recommended)</span>
              </label>

              <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem", cursor: "pointer", color: "#1e293b" }}>
                <input
                  type="checkbox"
                  checked={forceAll}
                  onChange={(e) => {
                    setForceAll(e.target.checked);
                    if (e.target.checked) setSkipCompleted(false);
                  }}
                />
                <span>Force re-extract all pages (overwrite existing)</span>
              </label>
            </div>

            {/* Shared character info callout */}
            <div
              style={{
                backgroundColor: "#eef2ff",
                border: "1px solid #c7d2fe",
                borderRadius: "6px",
                padding: "0.75rem 1rem",
                marginBottom: "1.5rem",
                fontSize: "0.8rem",
                color: "#3730a3",
                lineHeight: 1.4,
              }}
            >
              👥 <strong>Shared Character Roster:</strong> Characters discovered in earlier chapters are automatically supplied to the model in subsequent chapters, keeping character naming and IDs consistent across the series.
            </div>

            {/* Actions */}
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
              <button
                type="button"
                onClick={() => setShowBulkModal(false)}
                disabled={bulkStarting}
                style={{
                  padding: "0.6rem 1rem",
                  borderRadius: "6px",
                  border: "1px solid #cbd5e1",
                  backgroundColor: "#fff",
                  cursor: bulkStarting ? "not-allowed" : "pointer",
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleStartBulkOcr}
                disabled={bulkStarting || selectedChaptersList.length === 0}
                style={{
                  padding: "0.6rem 1.25rem",
                  borderRadius: "6px",
                  border: "none",
                  backgroundColor: "#4f46e5",
                  color: "#fff",
                  fontWeight: 600,
                  cursor: bulkStarting ? "not-allowed" : "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.5rem",
                  opacity: bulkStarting ? 0.7 : 1,
                }}
              >
                {bulkStarting ? "Starting..." : `⚡ Start Bulk OCR (${selectedChaptersList.length} Ch)`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
