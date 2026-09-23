import React from "react";
import type { PageInfo } from "../../types/context";

interface PageListProps {
  pages: PageInfo[];
  currentPageNumber: number;
  onSelectPage: (pageNum: number) => void;
  onDeletePage?: (pageNum: number) => void;
}

export const PageList: React.FC<PageListProps> = ({
  pages,
  currentPageNumber,
  onSelectPage,
  onDeletePage,
}) => {
  const getStatusBadge = (page: PageInfo) => {
    switch (page.status) {
      case "done":
        return <span style={{ color: "#16a34a", fontWeight: "bold" }} title="Extracted">✓</span>;
      case "failed":
      case "manual_review":
        return (
          <span
            style={{ color: "#ea580c", fontWeight: "bold" }}
            title={page.error_message || "Manual review needed"}
          >
            ⚠
          </span>
        );
      case "processing":
        return <span style={{ color: "#2563eb", fontWeight: "bold" }} title="Processing...">⟳</span>;
      default:
        return <span style={{ color: "#94a3b8" }} title="Pending extraction">○</span>;
    }
  };

  return (
    <div
      style={{
        width: "160px",
        borderRight: "1px solid #e2e8f0",
        height: "100%",
        overflowY: "auto",
        backgroundColor: "#f8fafc",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div
        style={{
          padding: "0.75rem 1rem",
          fontWeight: 700,
          fontSize: "0.85rem",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          color: "#475569",
          borderBottom: "1px solid #e2e8f0",
        }}
      >
        Pages ({pages.length})
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "0.5rem" }}>
        {pages.map((p) => {
          const isActive = p.page_number === currentPageNumber;
          return (
            <div
              key={p.page_number}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                width: "100%",
                padding: "0.35rem 0.5rem",
                marginBottom: "0.25rem",
                borderRadius: "6px",
                backgroundColor: isActive ? "#2563eb" : "transparent",
                color: isActive ? "#ffffff" : "#1e293b",
                transition: "background-color 0.15s",
                boxSizing: "border-box",
              }}
            >
              <button
                type="button"
                onClick={() => onSelectPage(p.page_number)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.4rem",
                  flex: 1,
                  background: "none",
                  border: "none",
                  padding: 0,
                  color: "inherit",
                  fontWeight: isActive ? 600 : 400,
                  fontSize: "0.85rem",
                  cursor: "pointer",
                  textAlign: "left",
                }}
              >
                <span>{getStatusBadge(p)}</span>
                <span>Page {p.page_number.toString().padStart(3, "0")}</span>
              </button>
              {onDeletePage && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeletePage(p.page_number);
                  }}
                  title={`Hapus Page ${p.page_number}`}
                  style={{
                    background: "none",
                    border: "none",
                    color: isActive ? "rgba(255,255,255,0.7)" : "#94a3b8",
                    cursor: "pointer",
                    padding: "2px 4px",
                    borderRadius: "3px",
                    fontSize: "0.75rem",
                    lineHeight: 1,
                  }}
                  onMouseEnter={(e) => {
                    (e.target as HTMLElement).style.color = "#ef4444";
                  }}
                  onMouseLeave={(e) => {
                    (e.target as HTMLElement).style.color = isActive ? "rgba(255,255,255,0.7)" : "#94a3b8";
                  }}
                >
                  ✕
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

