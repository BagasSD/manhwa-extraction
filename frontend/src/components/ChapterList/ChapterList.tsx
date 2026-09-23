import React, { useState } from "react";
import type { ChapterSummary } from "../../types/context";

interface ChapterListProps {
  chapters: ChapterSummary[];
  onSelectChapter: (id: string) => void;
  onCreateChapter: (data: { title: string; source_path: string }) => Promise<void>;
  onDownloadChapter?: (data: { url: string; title?: string; id?: string }) => Promise<void>;
  loading: boolean;
}

export const ChapterList: React.FC<ChapterListProps> = ({
  chapters,
  onSelectChapter,
  onCreateChapter,
  onDownloadChapter,
  loading,
}) => {
  const [showModal, setShowModal] = useState(false);
  const [showDownloadModal, setShowDownloadModal] = useState(false);
  
  // Local folder registration state
  const [title, setTitle] = useState("");
  const [sourcePath, setSourcePath] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // URL download state
  const [downloadUrl, setDownloadUrl] = useState("");
  const [downloadTitle, setDownloadTitle] = useState("");
  const [downloadId, setDownloadId] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

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

  const handleDownloadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!downloadUrl.trim()) return;
    if (!onDownloadChapter) return;
    try {
      setDownloading(true);
      setDownloadError(null);
      await onDownloadChapter({
        url: downloadUrl.trim(),
        title: downloadTitle.trim() || undefined,
        id: downloadId.trim() || undefined,
      });
      setDownloadUrl("");
      setDownloadTitle("");
      setDownloadId("");
      setShowDownloadModal(false);
    } catch (err) {
      setDownloadError((err as Error).message);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div style={{ maxWidth: "900px", margin: "0 auto", padding: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: "1.5rem", fontWeight: 700 }}>Chapters</h2>
          <p style={{ margin: "0.25rem 0 0", color: "#666", fontSize: "0.9rem" }}>
            Select a chapter to review, download from web URL, or register a local folder.
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.75rem" }}>
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

          return (
            <div
              key={ch.id}
              onClick={() => onSelectChapter(ch.id)}
              style={{
                border: "1px solid #e2e8f0",
                borderRadius: "8px",
                padding: "1.25rem",
                backgroundColor: "#fff",
                boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
                cursor: "pointer",
                transition: "border-color 0.15s, box-shadow 0.15s",
              }}
            >
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
          );
        })}
      </div>

      {/* Modal create chapter */}
      {showModal && (
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
      {/* Modal download chapter from URL */}
      {showDownloadModal && (
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
              maxWidth: "520px",
              boxShadow: "0 10px 25px rgba(0,0,0,0.15)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
              <span style={{ fontSize: "1.4rem" }}>📥</span>
              <h3 style={{ margin: 0, fontSize: "1.25rem", color: "#0f172a" }}>Download Chapter from URL</h3>
            </div>

            <p style={{ margin: "0 0 1.25rem", color: "#64748b", fontSize: "0.85rem" }}>
              Provide a manhwa chapter web URL or ZIP link. Images will be automatically downloaded and stored into <code>data/chapters/</code>.
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

            <form onSubmit={handleDownloadSubmit}>
              <div style={{ marginBottom: "1rem" }}>
                <label style={{ display: "block", marginBottom: "0.35rem", fontWeight: 600, fontSize: "0.9rem" }}>
                  Chapter URL <span style={{ color: "#ef4444" }}>*</span>
                </label>
                <input
                  type="url"
                  required
                  placeholder="https://example.com/read/chapter-1 or .zip"
                  value={downloadUrl}
                  onChange={(e) => setDownloadUrl(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "0.6rem",
                    borderRadius: "6px",
                    border: "1px solid #cbd5e1",
                    boxSizing: "border-box",
                  }}
                />
              </div>

              <div style={{ marginBottom: "1rem" }}>
                <label style={{ display: "block", marginBottom: "0.35rem", fontWeight: 600, fontSize: "0.9rem" }}>
                  Chapter Title <span style={{ fontSize: "0.8rem", color: "#94a3b8" }}>(optional, auto-extracted if empty)</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g. Solo Leveling - Chapter 01"
                  value={downloadTitle}
                  onChange={(e) => setDownloadTitle(e.target.value)}
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
                  Custom Chapter ID <span style={{ fontSize: "0.8rem", color: "#94a3b8" }}>(optional)</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g. chapter-01"
                  value={downloadId}
                  onChange={(e) => setDownloadId(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "0.6rem",
                    borderRadius: "6px",
                    border: "1px solid #cbd5e1",
                    boxSizing: "border-box",
                  }}
                />
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
                <button
                  type="button"
                  onClick={() => setShowDownloadModal(false)}
                  disabled={downloading}
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
                  disabled={downloading}
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
                  {downloading ? "Downloading Images..." : "Start Download"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
