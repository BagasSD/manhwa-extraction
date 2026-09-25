import React, { useCallback, useEffect, useRef, useState } from "react";
import type {
  Chapter,
  CropAllResult,
  ExtractedImage,
  PagePanels,
  PanelDetectionStatus,
  PanelPageStatus,
} from "../types/context";
import {
  cropAllPanels,
  getChapter,
  getExtractedImageUrl,
  getPageImageUrl,
  getPagePanels,
  getPanelDetectionStatus,
  listExtractedImages,
  PanelsNotReviewedError,
  savePagePanels,
  startPanelDetection,
} from "../services/api";
import { PanelOverlay, type EditablePanel } from "../components/PanelOverlay/PanelOverlay";

interface PanelReviewViewProps {
  chapterId: string;
  onBack: () => void;
}

const STATUS_BADGE: Record<PanelPageStatus, { icon: string; color: string; label: string }> = {
  none: { icon: "○", color: "#94a3b8", label: "Not detected" },
  auto_detected: { icon: "◐", color: "#ea580c", label: "Auto-detected, needs review" },
  reviewed: { icon: "✓", color: "#2563eb", label: "Reviewed" },
  cropped: { icon: "✓", color: "#16a34a", label: "Reviewed and cropped" },
};

const buttonStyle = (background: string, disabled = false): React.CSSProperties => ({
  padding: "4px 10px",
  backgroundColor: disabled ? "#475569" : background,
  color: disabled ? "#cbd5e1" : "#fff",
  border: "none",
  borderRadius: "4px",
  fontWeight: 600,
  fontSize: "0.8rem",
  cursor: disabled ? "not-allowed" : "pointer",
  whiteSpace: "nowrap",
});

/**
 * Panel Review View for the "Extract Image" pipeline: check the auto-detected
 * boxes page by page, fix them (move, resize, add, delete), save each page as
 * reviewed, then crop every reviewed panel into data/extractedImage/.
 * Separate from the text review in Chapter.tsx; nothing here calls the model.
 */
export const PanelReviewView: React.FC<PanelReviewViewProps> = ({ chapterId, onBack }) => {
  const [chapter, setChapter] = useState<Chapter | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [pagePanels, setPagePanels] = useState<PagePanels | null>(null);
  const [panels, setPanels] = useState<EditablePanel[]>([]);
  const [dirty, setDirty] = useState(false);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [natural, setNatural] = useState({ width: 0, height: 0 });
  const [displayWidth, setDisplayWidth] = useState(0);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [detection, setDetection] = useState<PanelDetectionStatus | null>(null);
  const [cropping, setCropping] = useState(false);
  const [cropResult, setCropResult] = useState<CropAllResult | null>(null);
  const [extracted, setExtracted] = useState<ExtractedImage[]>([]);

  const keyCounter = useRef(0);
  const imgRef = useRef<HTMLImageElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const toEditable = useCallback((source: PagePanels | null): EditablePanel[] => {
    return (source?.panels ?? []).map((p) => ({ key: `p${keyCounter.current++}`, bbox: p.bbox }));
  }, []);

  const refreshChapter = useCallback(async () => {
    const data = await getChapter(chapterId);
    setChapter(data);
    return data;
  }, [chapterId]);

  const loadPage = useCallback(
    async (pageNum: number) => {
      const data = await getPagePanels(chapterId, pageNum);
      setPagePanels(data);
      setPanels(toEditable(data));
      setDirty(false);
      setSelectedKey(null);
    },
    [chapterId, toEditable],
  );

  // Initial load: chapter, detection job (if one is running) and existing crops
  useEffect(() => {
    refreshChapter()
      .then((data) => {
        const first = data.pages.find((p) => p.panel_status === "auto_detected") ?? data.pages[0];
        if (first) setCurrentPage(first.page_number);
      })
      .catch((err) => setNotice(`Failed to load chapter: ${(err as Error).message}`));
    getPanelDetectionStatus(chapterId).then(setDetection).catch(() => {});
    listExtractedImages(chapterId).then(setExtracted).catch(() => {});
  }, [chapterId, refreshChapter]);

  useEffect(() => {
    loadPage(currentPage).catch((err) => setNotice(`Failed to load panels: ${(err as Error).message}`));
  }, [currentPage, loadPage]);

  const showPage = (pageNum: number) => {
    setNatural({ width: 0, height: 0 }); // hide boxes until the new page image has loaded
    setCurrentPage(pageNum);
    scrollRef.current?.scrollTo({ top: 0 });
  };

  // Poll a running detection job, then refresh what it changed
  const detectionRunning = detection?.status === "running";
  useEffect(() => {
    if (!detectionRunning) return;
    const interval = setInterval(async () => {
      try {
        const status = await getPanelDetectionStatus(chapterId);
        setDetection(status);
        if (status.status !== "running") {
          await refreshChapter();
          await loadPage(currentPage);
        }
      } catch (err) {
        console.error("Failed to poll panel detection:", err);
      }
    }, 800);
    return () => clearInterval(interval);
  }, [detectionRunning, chapterId, refreshChapter, loadPage, currentPage]);

  // Keep the on-screen scale in sync with the rendered image width
  const chapterLoaded = chapter !== null;
  useEffect(() => {
    const img = imgRef.current;
    if (!img) return;
    const observer = new ResizeObserver(() => setDisplayWidth(img.clientWidth));
    observer.observe(img);
    return () => observer.disconnect();
  }, [chapterLoaded]);

  const scale = natural.width > 0 && displayWidth > 0 ? displayWidth / natural.width : 0;
  const pages = chapter?.pages ?? [];
  const unreviewedPages = pages.filter((p) => p.panel_status === "none" || p.panel_status === "auto_detected");
  const reviewedCount = pages.length - unreviewedPages.length;
  const missingPages = pages.filter((p) => !p.panel_status || p.panel_status === "none");
  const pageInfo = pages.find((p) => p.page_number === currentPage);
  const pageStatus: PanelPageStatus = pageInfo?.panel_status ?? "none";

  const confirmLeave = () => !dirty || window.confirm("Discard unsaved panel changes on this page?");

  const goToPage = (pageNum: number) => {
    if (pageNum < 1 || pageNum > pages.length || pageNum === currentPage || !confirmLeave()) return;
    showPage(pageNum);
  };

  const updatePanel = (key: string, bbox: number[]) => {
    setPanels((prev) => prev.map((p) => (p.key === key ? { ...p, bbox } : p)));
    setDirty(true);
  };

  const deletePanel = useCallback((key: string) => {
    setPanels((prev) => prev.filter((p) => p.key !== key));
    setSelectedKey(null);
    setDirty(true);
  }, []);

  const addPanel = () => {
    if (!natural.width || !scale) return;
    // New box in the middle of what is currently visible
    const scroller = scrollRef.current;
    const wrapperTop = wrapperRef.current?.offsetTop ?? 0;
    const visibleCenter = scroller ? scroller.scrollTop + scroller.clientHeight / 2 - wrapperTop : 0;
    const width = Math.round(natural.width * 0.8);
    const height = Math.min(Math.round(natural.width * 0.6), natural.height);
    const center = Math.max(height / 2, Math.min(natural.height - height / 2, visibleCenter / scale));
    const ymin = Math.round(center - height / 2);
    const xmin = Math.round((natural.width - width) / 2);
    const key = `p${keyCounter.current++}`;
    setPanels((prev) => [...prev, { key, bbox: [ymin, xmin, ymin + height, xmin + width] }]);
    setSelectedKey(key);
    setDirty(true);
  };

  const save = useCallback(
    async (next = false) => {
      if (saving) return;
      setSaving(true);
      try {
        const saved = await savePagePanels(chapterId, currentPage, panels.map((p) => p.bbox));
        setPagePanels(saved);
        setPanels(toEditable(saved));
        setDirty(false);
        setSelectedKey(null);
        setCropResult(null);
        const data = await refreshChapter();
        setNotice(`Page ${currentPage} saved as reviewed (${saved.panels.length} panel(s)).`);
        if (next && currentPage < data.pages.length) showPage(currentPage + 1);
      } catch (err) {
        setNotice(`Save failed: ${(err as Error).message}`);
      } finally {
        setSaving(false);
      }
    },
    [saving, chapterId, currentPage, panels, toEditable, refreshChapter],
  );

  const runDetection = async (pagesToDetect?: number[], overwrite = false) => {
    try {
      setNotice(null);
      setDetection(await startPanelDetection(chapterId, { pages: pagesToDetect, overwrite_reviewed: overwrite }));
    } catch (err) {
      setNotice(`Detection failed: ${(err as Error).message}`);
    }
  };

  const resetPage = () => {
    const message =
      pageStatus === "none"
        ? `Auto-detect panels on page ${currentPage}?`
        : `Replace the boxes on page ${currentPage} with a fresh auto-detection? Your edits on this page are lost.`;
    if (window.confirm(message)) runDetection([currentPage], true);
  };

  const cropAll = async () => {
    setCropping(true);
    setNotice(null);
    try {
      const result = await cropAllPanels(chapterId);
      setCropResult(result);
      setExtracted(await listExtractedImages(chapterId));
      await refreshChapter();
    } catch (err) {
      if (err instanceof PanelsNotReviewedError) {
        setNotice(`Crop blocked: page(s) ${err.unreviewedPages.join(", ")} are not reviewed yet.`);
      } else {
        setNotice(`Crop failed: ${(err as Error).message}`);
      }
    } finally {
      setCropping(false);
    }
  };

  // Keyboard: Ctrl+S saves, Delete removes the selected box
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        save(false);
      } else if (!typing && selectedKey && (e.key === "Delete" || e.key === "Backspace")) {
        e.preventDefault();
        deletePanel(selectedKey);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [save, deletePanel, selectedKey]);

  const cropDisabledReason =
    unreviewedPages.length > 0
      ? `${unreviewedPages.length} halaman belum direview`
      : dirty
        ? "Save this page first"
        : pages.length === 0
          ? "No pages"
          : null;

  if (!chapter) {
    return (
      <div style={{ padding: "3rem", textAlign: "center", color: "#64748b" }}>
        {notice ?? "Loading panel review..."}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", width: "100vw", overflow: "hidden" }}>
      {/* Header */}
      <header
        style={{
          minHeight: "50px",
          backgroundColor: "#1e293b",
          color: "#fff",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "1rem",
          padding: "0 1rem",
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <button type="button" onClick={() => confirmLeave() && onBack()} style={buttonStyle("#334155")}>
            ← Context Review
          </button>
          <span style={{ fontWeight: 600 }}>{chapter.title}</span>
          <span style={{ fontSize: "0.8rem", color: "#cbd5e1" }}>
            Extract Image · {reviewedCount}/{pages.length} halaman direview
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <button type="button" onClick={() => goToPage(currentPage - 1)} disabled={currentPage <= 1} style={buttonStyle("#334155", currentPage <= 1)}>
            ◀ Prev
          </button>
          <span style={{ fontSize: "0.85rem" }}>
            Page {currentPage} / {pages.length}
          </span>
          <button
            type="button"
            onClick={() => goToPage(currentPage + 1)}
            disabled={currentPage >= pages.length}
            style={buttonStyle("#334155", currentPage >= pages.length)}
          >
            Next ▶
          </button>
          <span title={cropDisabledReason ?? "Crop every reviewed panel into data/extractedImage/"}>
            <button
              type="button"
              onClick={cropAll}
              disabled={!!cropDisabledReason || cropping}
              style={buttonStyle("#16a34a", !!cropDisabledReason || cropping)}
            >
              {cropping ? "Cropping..." : "✂ Crop All"}
            </button>
          </span>
        </div>
      </header>

      {/* Detection progress / notices */}
      {(detectionRunning || missingPages.length > 0 || notice) && (
        <div
          style={{
            padding: "0.4rem 1rem",
            backgroundColor: detectionRunning ? "#eff6ff" : "#f8fafc",
            borderBottom: "1px solid #cbd5e1",
            fontSize: "0.85rem",
            display: "flex",
            alignItems: "center",
            gap: "1rem",
          }}
        >
          {detectionRunning && detection ? (
            <>
              <span style={{ fontWeight: 600, color: "#1d4ed8", whiteSpace: "nowrap" }}>
                Detecting panels: {detection.processed_pages}/{detection.total_pages}
              </span>
              <div style={{ flex: 1, maxWidth: 400, height: 8, backgroundColor: "#dbeafe", borderRadius: 4 }}>
                <div
                  style={{
                    height: "100%",
                    width: `${detection.total_pages ? (detection.processed_pages / detection.total_pages) * 100 : 0}%`,
                    backgroundColor: "#2563eb",
                    borderRadius: 4,
                    transition: "width 0.3s ease",
                  }}
                />
              </div>
            </>
          ) : (
            missingPages.length > 0 && (
              <>
                <span style={{ color: "#9a3412" }}>{missingPages.length} halaman belum dideteksi.</span>
                <button type="button" onClick={() => runDetection()} style={buttonStyle("#2563eb")}>
                  ⚡ Detect missing pages
                </button>
              </>
            )
          )}
          {notice && <span style={{ color: "#334155" }}>{notice}</span>}
        </div>
      )}

      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        {/* Page list */}
        <nav style={{ width: 170, borderRight: "1px solid #e2e8f0", overflowY: "auto", backgroundColor: "#fff" }}>
          {pages.map((p) => {
            const badge = STATUS_BADGE[p.panel_status ?? "none"];
            const active = p.page_number === currentPage;
            return (
              <button
                key={p.page_number}
                type="button"
                onClick={() => goToPage(p.page_number)}
                title={badge.label}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  width: "100%",
                  padding: "0.5rem 0.75rem",
                  border: "none",
                  borderBottom: "1px solid #f1f5f9",
                  backgroundColor: active ? "#eff6ff" : "transparent",
                  borderLeft: active ? "3px solid #2563eb" : "3px solid transparent",
                  cursor: "pointer",
                  fontSize: "0.85rem",
                  textAlign: "left",
                }}
              >
                <span>Page {p.page_number}</span>
                <span style={{ color: badge.color, fontWeight: 700 }}>
                  {p.panel_status && p.panel_status !== "none" ? `${p.panel_count ?? 0} ` : ""}
                  {badge.icon}
                </span>
              </button>
            );
          })}
        </nav>

        {/* Page image with editable boxes */}
        <div
          ref={scrollRef}
          style={{ flex: 1, overflow: "auto", backgroundColor: "#0f172a", padding: "1.5rem", textAlign: "center" }}
        >
          <div
            ref={wrapperRef}
            onMouseDown={() => setSelectedKey(null)}
            style={{ position: "relative", display: "inline-block", lineHeight: 0, maxWidth: "100%" }}
          >
            <img
              ref={imgRef}
              src={getPageImageUrl(chapterId, currentPage)}
              alt={`Page ${currentPage}`}
              draggable={false}
              onLoad={(e) => {
                setNatural({ width: e.currentTarget.naturalWidth, height: e.currentTarget.naturalHeight });
                setDisplayWidth(e.currentTarget.clientWidth);
              }}
              style={{ display: "block", maxWidth: "100%", width: natural.width || undefined, userSelect: "none" }}
            />
            {scale > 0 && (
              <PanelOverlay
                panels={panels}
                scale={scale}
                imageWidth={natural.width}
                imageHeight={natural.height}
                selectedKey={selectedKey}
                onSelect={setSelectedKey}
                onChange={updatePanel}
                onDelete={deletePanel}
              />
            )}
          </div>
        </div>

        {/* Side panel */}
        <aside
          style={{
            width: 300,
            borderLeft: "1px solid #e2e8f0",
            backgroundColor: "#f8fafc",
            padding: "1rem",
            overflowY: "auto",
            fontSize: "0.85rem",
            display: "flex",
            flexDirection: "column",
            gap: "0.75rem",
          }}
        >
          <div>
            <h3 style={{ margin: "0 0 0.25rem", fontSize: "1.05rem" }}>Page {currentPage} panels</h3>
            <span style={{ color: STATUS_BADGE[pageStatus].color, fontWeight: 600 }}>
              {STATUS_BADGE[pageStatus].icon} {STATUS_BADGE[pageStatus].label}
              {dirty && <span style={{ color: "#ea580c" }}> · unsaved changes</span>}
            </span>
          </div>

          <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
            <button type="button" onClick={addPanel} disabled={!scale} style={buttonStyle("#d97706", !scale)}>
              + Add panel
            </button>
            <button type="button" onClick={resetPage} disabled={detectionRunning} style={buttonStyle("#475569", detectionRunning)}>
              ↺ Auto-detect page
            </button>
          </div>

          <ol style={{ margin: 0, paddingLeft: "1.3rem", display: "flex", flexDirection: "column", gap: "0.25rem" }}>
            {panels.map((p, idx) => {
              const [ymin, xmin, ymax, xmax] = p.bbox;
              return (
                <li
                  key={p.key}
                  onClick={() => setSelectedKey(p.key)}
                  style={{
                    cursor: "pointer",
                    fontWeight: p.key === selectedKey ? 700 : 400,
                    color: p.key === selectedKey ? "#1d4ed8" : "#334155",
                  }}
                >
                  Panel {idx + 1}: {xmax - xmin}×{ymax - ymin}px @ y={ymin}
                </li>
              );
            })}
            {panels.length === 0 && (
              <span style={{ color: "#94a3b8", fontStyle: "italic" }}>
                {pagePanels || dirty ? "No panels on this page." : "Not detected yet — use Auto-detect page."}
              </span>
            )}
          </ol>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
            <button type="button" onClick={() => save(false)} disabled={saving} style={buttonStyle("#2563eb", saving)}>
              {saving ? "Saving..." : "✓ Save & mark reviewed (Ctrl+S)"}
            </button>
            <button
              type="button"
              onClick={() => save(true)}
              disabled={saving || currentPage >= pages.length}
              style={buttonStyle("#1d4ed8", saving || currentPage >= pages.length)}
            >
              ✓ Save & next page ▶
            </button>
          </div>

          <p style={{ margin: 0, color: "#64748b", lineHeight: 1.45 }}>
            Drag a box to move it, drag its edges or corners to resize, press Del to remove the selected box.
            A page counts as reviewed once saved, even without changes. Crop All unlocks when every page is
            reviewed.
          </p>

          {(cropResult || extracted.length > 0) && (
            <div style={{ borderTop: "1px solid #e2e8f0", paddingTop: "0.75rem" }}>
              <h4 style={{ margin: "0 0 0.4rem" }}>Extracted images</h4>
              {cropResult && (
                <p style={{ margin: "0 0 0.4rem", color: "#166534", fontWeight: 600 }}>
                  ✂ {cropResult.total_crops} panel(s) cropped from {cropResult.pages_cropped} page(s).
                </p>
              )}
              {cropResult && (
                <p style={{ margin: "0 0 0.4rem", wordBreak: "break-all" }}>
                  Folder: <code>{cropResult.output_dir}</code>{" "}
                  <button
                    type="button"
                    onClick={() => navigator.clipboard?.writeText(cropResult.output_dir)}
                    style={{ ...buttonStyle("#475569"), padding: "1px 6px" }}
                  >
                    Copy path
                  </button>
                </p>
              )}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.35rem" }}>
                {extracted.map((img) => (
                  <a
                    key={img.filename}
                    href={getExtractedImageUrl(chapterId, img.filename)}
                    target="_blank"
                    rel="noreferrer"
                    title={img.filename}
                  >
                    <img
                      src={getExtractedImageUrl(chapterId, img.filename)}
                      alt={img.filename}
                      loading="lazy"
                      style={{ width: "100%", height: 70, objectFit: "cover", borderRadius: 3, border: "1px solid #cbd5e1" }}
                    />
                  </a>
                ))}
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
};

export default PanelReviewView;
