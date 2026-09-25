import React, { useEffect, useState } from "react";
import type { Chapter, PanelDetectionStatus } from "../../types/context";
import { getPanelDetectionStatus, startPanelDetection } from "../../services/api";

interface ExtractImageBarProps {
  chapter: Chapter;
  onOpenReview: () => void;
  onRefreshChapter: () => Promise<void>;
}

/**
 * Second CTA of the chapter page: "Extract Image" (local panel detection +
 * crop, zero tokens). Kept visually and functionally separate from "Extract
 * Context" (Gemma, cloud) so it is always clear which process runs.
 */
export const ExtractImageBar: React.FC<ExtractImageBarProps> = ({ chapter, onOpenReview, onRefreshChapter }) => {
  const [detection, setDetection] = useState<PanelDetectionStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const running = detection?.status === "running";

  useEffect(() => {
    getPanelDetectionStatus(chapter.id).then(setDetection).catch(() => {});
  }, [chapter.id]);

  // Poll the detection job; open the review view when it finishes
  useEffect(() => {
    if (!running) return;
    const interval = setInterval(async () => {
      try {
        const status = await getPanelDetectionStatus(chapter.id);
        setDetection(status);
        if (status.status !== "running") {
          await onRefreshChapter();
          if (status.status === "completed") onOpenReview();
        }
      } catch (err) {
        console.error("Failed to poll panel detection:", err);
      }
    }, 800);
    return () => clearInterval(interval);
  }, [running, chapter.id, onRefreshChapter, onOpenReview]);

  const handleExtract = async () => {
    setError(null);
    try {
      setDetection(await startPanelDetection(chapter.id));
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const total = chapter.total_pages;
  const reviewed = chapter.panel_reviewed_pages ?? 0;
  const detected = chapter.panel_detected_pages ?? 0;
  const imageStatus = chapter.image_status ?? "not_started";

  let statusText: string;
  let percent: number;
  if (running && detection) {
    statusText = `Mendeteksi panel... ${detection.processed_pages}/${detection.total_pages} halaman`;
    percent = detection.total_pages ? (detection.processed_pages / detection.total_pages) * 100 : 0;
  } else if (imageStatus === "cropped") {
    statusText = `✅ Done: ${total}/${total} halaman direview & di-crop`;
    percent = 100;
  } else if (imageStatus === "reviewing") {
    statusText = `⏳ ${reviewed}/${total} halaman direview`;
    percent = total ? (reviewed / total) * 100 : 0;
  } else if (imageStatus === "detecting") {
    statusText = `${detected}/${total} halaman terdeteksi`;
    percent = total ? (detected / total) * 100 : 0;
  } else {
    statusText = "Belum dimulai";
    percent = 0;
  }

  const canReview = imageStatus !== "not_started" && !running;

  return (
    <div
      style={{
        backgroundColor: running ? "#f0fdf4" : "#f8fafc",
        borderBottom: "1px solid #cbd5e1",
        padding: "0.5rem 1rem",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        fontSize: "0.85rem",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "1rem", flex: 1, maxWidth: "60%" }}>
        <div style={{ fontWeight: 600, color: "#1e293b", whiteSpace: "nowrap" }}>
          Extract Image <span style={{ fontWeight: 400, color: "#64748b" }}>(lokal, 0 token)</span>: {statusText}
        </div>
        <div style={{ flex: 1, height: "8px", backgroundColor: "#e2e8f0", borderRadius: "4px", overflow: "hidden" }}>
          <div
            style={{
              height: "100%",
              width: `${percent}%`,
              backgroundColor: running ? "#16a34a" : "#0d9488",
              transition: "width 0.3s ease",
            }}
          />
        </div>
        {error && <span style={{ color: "#dc2626" }}>{error}</span>}
        {detection?.status === "failed" && <span style={{ color: "#dc2626" }}>{detection.message}</span>}
      </div>

      <div style={{ display: "flex", gap: "0.5rem" }}>
        {(imageStatus === "not_started" || imageStatus === "detecting") && (
          <button
            type="button"
            onClick={handleExtract}
            disabled={running}
            title="Detect panels on every page locally (OpenCV), then review them"
            style={{
              padding: "4px 12px",
              backgroundColor: running ? "#94a3b8" : "#0d9488",
              color: "#fff",
              border: "none",
              borderRadius: "4px",
              fontWeight: 600,
              fontSize: "0.8rem",
              cursor: running ? "not-allowed" : "pointer",
            }}
          >
            {running ? "Detecting..." : "🖼 Extract Image"}
          </button>
        )}
        {canReview && (
          <button
            type="button"
            onClick={onOpenReview}
            style={{
              padding: "4px 12px",
              backgroundColor: "#0f766e",
              color: "#fff",
              border: "none",
              borderRadius: "4px",
              fontWeight: 600,
              fontSize: "0.8rem",
              cursor: "pointer",
            }}
          >
            {imageStatus === "cropped" ? "🖼 View Panels & Crops" : "🖼 Review Panels"}
          </button>
        )}
      </div>
    </div>
  );
};
