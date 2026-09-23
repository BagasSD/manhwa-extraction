import React from "react";

interface ReviewToolbarProps {
  chapterTitle: string;
  currentPageNumber: number;
  totalPages: number;
  pageStatus: string;
  saving?: boolean;
  saveSuccess?: boolean;
  extracting?: boolean;
  onSave?: () => void;
  onExtractPage?: () => void;
  onRetryPage?: () => void;
  onOpenRoster?: () => void;
  onOpenContext?: () => void;
  onExportJson?: () => void;
  onExportTxt?: () => void;
  onDeletePage?: () => void;
  onBack: () => void;
  onPrevPage: () => void;
  onNextPage: () => void;
}


export const ReviewToolbar: React.FC<ReviewToolbarProps> = ({
  chapterTitle,
  currentPageNumber,
  totalPages,
  pageStatus,
  saving = false,
  saveSuccess = false,
  extracting = false,
  onSave,
  onExtractPage,
  onRetryPage,
  onOpenRoster,
  onOpenContext,
  onExportJson,
  onExportTxt,
  onDeletePage,
  onBack,
  onPrevPage,
  onNextPage,
}) => {

  return (
    <header
      style={{
        height: "50px",
        backgroundColor: "#1e293b",
        color: "#fff",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 1rem",
        borderBottom: "1px solid #334155",
        boxSizing: "border-box",
        zIndex: 100,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
        <button
          type="button"
          onClick={onBack}
          style={{
            backgroundColor: "#334155",
            color: "#fff",
            border: "none",
            borderRadius: "4px",
            padding: "4px 8px",
            fontSize: "0.85rem",
            cursor: "pointer",
            fontWeight: 500,
          }}
        >
          ← Chapters
        </button>
        <span style={{ fontWeight: 600, fontSize: "1rem", color: "#f8fafc" }}>
          {chapterTitle}
        </span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        {onOpenRoster && (
          <button
            type="button"
            onClick={onOpenRoster}
            style={{
              backgroundColor: "#334155",
              color: "#e2e8f0",
              border: "1px solid #475569",
              borderRadius: "4px",
              padding: "4px 8px",
              fontSize: "0.82rem",
              fontWeight: 500,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "4px",
            }}
            title="View and manage known characters"
          >
            👥 Characters
          </button>
        )}

        {onOpenContext && (
          <button
            type="button"
            onClick={onOpenContext}
            style={{
              backgroundColor: "#334155",
              color: "#e2e8f0",
              border: "1px solid #475569",
              borderRadius: "4px",
              padding: "4px 8px",
              fontSize: "0.82rem",
              fontWeight: 500,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "4px",
            }}
            title="View and generate aggregated chapter context"
          >
            📖 Context
          </button>
        )}

        {onExportTxt && (
          <button
            type="button"
            onClick={onExportTxt}
            style={{
              backgroundColor: "#334155",
              color: "#38bdf8",
              border: "1px solid #0284c7",
              borderRadius: "4px",
              padding: "4px 8px",
              fontSize: "0.82rem",
              fontWeight: 600,
              cursor: "pointer",
            }}
            title="Download AI-optimized TXT export"
          >
            ⬇ TXT
          </button>
        )}

        {onExportJson && (
          <button
            type="button"
            onClick={onExportJson}
            style={{
              backgroundColor: "#334155",
              color: "#38bdf8",
              border: "1px solid #0284c7",
              borderRadius: "4px",
              padding: "4px 8px",
              fontSize: "0.82rem",
              fontWeight: 600,
              cursor: "pointer",
            }}
            title="Download structured JSON export"
          >
            ⬇ JSON
          </button>
        )}

        {pageStatus === "pending" && onExtractPage && (
          <button
            type="button"
            onClick={onExtractPage}
            disabled={extracting}
            style={{
              backgroundColor: "#4f46e5",
              color: "#fff",
              border: "none",
              borderRadius: "4px",
              padding: "4px 9px",
              fontSize: "0.82rem",
              fontWeight: 600,
              cursor: extracting ? "not-allowed" : "pointer",
              opacity: extracting ? 0.7 : 1,
            }}
            title="Run Gemma model on this page"
          >
            {extracting ? "Extracting..." : "⚡ Extract"}
          </button>
        )}

        {(pageStatus === "failed" || pageStatus === "manual_review" || pageStatus === "done") && onRetryPage && (
          <button
            type="button"
            onClick={onRetryPage}
            disabled={extracting}
            style={{
              backgroundColor: pageStatus === "done" ? "#475569" : "#ea580c",
              color: "#fff",
              border: "none",
              borderRadius: "4px",
              padding: "4px 9px",
              fontSize: "0.82rem",
              fontWeight: 600,
              cursor: extracting ? "not-allowed" : "pointer",
              opacity: extracting ? 0.7 : 1,
            }}
            title={pageStatus === "done" ? "Re-run extraction" : "Retry extraction with enhancements"}
          >
            {extracting ? "Extracting..." : pageStatus === "done" ? "🔄 Re-extract" : "⚡ Retry"}
          </button>
        )}

        {onSave && (
          <button
            type="button"
            onClick={onSave}
            disabled={saving}
            style={{
              backgroundColor: saveSuccess ? "#16a34a" : "#2563eb",
              color: "#fff",
              border: "none",
              borderRadius: "4px",
              padding: "4px 10px",
              fontSize: "0.82rem",
              fontWeight: 600,
              cursor: saving ? "not-allowed" : "pointer",
              display: "flex",
              alignItems: "center",
              gap: "4px",
              transition: "background-color 0.2s ease",
            }}
            title="Save changes (Ctrl+S / Cmd+S)"
          >
            {saving ? "Saving..." : saveSuccess ? "✓ Saved!" : "Save"}
          </button>
        )}

        {onDeletePage && (
          <button
            type="button"
            onClick={onDeletePage}
            style={{
              backgroundColor: "#ef4444",
              color: "#fff",
              border: "none",
              borderRadius: "4px",
              padding: "4px 8px",
              fontSize: "0.82rem",
              fontWeight: 600,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "3px",
            }}
            title="Delete this page from chapter"
          >
            🗑 Hapus Page
          </button>
        )}


        <span
          style={{
            fontSize: "0.78rem",
            padding: "2px 6px",
            borderRadius: "12px",
            backgroundColor:
              pageStatus === "done"
                ? "rgba(34, 197, 94, 0.2)"
                : pageStatus === "failed" || pageStatus === "manual_review"
                ? "rgba(239, 68, 68, 0.2)"
                : "rgba(148, 163, 184, 0.2)",
            color:
              pageStatus === "done"
                ? "#4ade80"
                : pageStatus === "failed" || pageStatus === "manual_review"
                ? "#f87171"
                : "#cbd5e1",
            textTransform: "capitalize",
          }}
        >
          {pageStatus.replace("_", " ")}
        </span>

        <button
          type="button"
          onClick={onPrevPage}
          disabled={currentPageNumber <= 1}
          style={{
            backgroundColor: "#334155",
            color: "#fff",
            border: "none",
            borderRadius: "4px",
            padding: "4px 8px",
            cursor: currentPageNumber <= 1 ? "not-allowed" : "pointer",
            opacity: currentPageNumber <= 1 ? 0.4 : 1,
            fontWeight: "bold",
            fontSize: "0.82rem",
          }}
          title="Previous Page (←)"
        >
          ‹
        </button>

        <span style={{ fontSize: "0.85rem", color: "#e2e8f0", minWidth: "75px", textAlign: "center" }}>
          {currentPageNumber} / {totalPages}
        </span>

        <button
          type="button"
          onClick={onNextPage}
          disabled={currentPageNumber >= totalPages}
          style={{
            backgroundColor: "#334155",
            color: "#fff",
            border: "none",
            borderRadius: "4px",
            padding: "4px 8px",
            cursor: currentPageNumber >= totalPages ? "not-allowed" : "pointer",
            opacity: currentPageNumber >= totalPages ? 0.4 : 1,
            fontWeight: "bold",
            fontSize: "0.82rem",
          }}
          title="Next Page (→)"
        >
          ›
        </button>
      </div>
    </header>
  );
};
