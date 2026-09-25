import React, { useCallback, useEffect, useState } from "react";
import type {
  BatchJobStatus,
  Chapter,
  KnownCharacter,
  PageContext,
  PageDetail,
  SelectedRegion,
} from "../types/context";
import {
  cancelBatchExtraction,
  deletePage,
  extractSinglePage,
  getBatchStatus,
  getChapter,
  getExportJsonUrl,
  getExportTxtUrl,
  getKnownCharacters,
  getPage,
  getPageImageUrl,
  mergeCharacters,
  renameCharacter,
  retrySinglePage,
  savePageCorrection,
  startBatchExtraction,
} from "../services/api";

import { PageList } from "../components/PageList/PageList";
import { ImageViewer } from "../components/ImageViewer/ImageViewer";
import { CharacterPanel } from "../components/CharacterPanel/CharacterPanel";
import { CharacterRosterModal } from "../components/CharacterPanel/CharacterRosterModal";
import { ChapterContextModal } from "../components/ChapterContext/ChapterContextModal";
import { TextPanel } from "../components/TextPanel/TextPanel";
import { ScenePanel } from "../components/ScenePanel/ScenePanel";
import { ReviewToolbar } from "../components/ReviewToolbar/ReviewToolbar";
import { ExtractImageBar } from "../components/ExtractImageBar/ExtractImageBar";

interface ChapterProps {
  chapterId: string;
  onBack: () => void;
  onOpenPanelReview: () => void;
}

export const ChapterPage: React.FC<ChapterProps> = ({ chapterId, onBack, onOpenPanelReview }) => {
  const [chapter, setChapter] = useState<Chapter | null>(null);
  const [currentPageNumber, setCurrentPageNumber] = useState<number>(1);
  const [pageDetail, setPageDetail] = useState<PageDetail | null>(null);
  const [knownCharacters, setKnownCharacters] = useState<KnownCharacter[]>([]);
  const [showRosterModal, setShowRosterModal] = useState<boolean>(false);
  const [showContextModal, setShowContextModal] = useState<boolean>(false);

  const [context, setContext] = useState<PageContext>({
    page: 1,
    characters: [],
    texts: [],
    scene: { location: null, situation: null, actions: [], mood: null },
  });
  const [selectedRegion, setSelectedRegion] = useState<SelectedRegion | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [saveSuccess, setSaveSuccess] = useState<boolean>(false);
  const [extractingSingle, setExtractingSingle] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Batch extraction states
  const [batchStatus, setBatchStatus] = useState<BatchJobStatus | null>(null);
  const isBatchRunning = batchStatus?.status === "running";

  // 1. Fetch chapter and known characters
  const fetchChapterData = useCallback(async () => {
    try {
      const data = await getChapter(chapterId);
      setChapter(data);
    } catch (err) {
      console.error("Failed to load chapter:", err);
    }
  }, [chapterId]);

  const fetchRoster = useCallback(async () => {
    try {
      const chars = await getKnownCharacters(chapterId);
      setKnownCharacters(chars);
    } catch (err) {
      console.error("Failed to load character roster:", err);
    }
  }, [chapterId]);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    getChapter(chapterId)
      .then((data) => {
        if (!isMounted) return;
        setChapter(data);
        if (data.pages.length > 0) {
          setCurrentPageNumber(data.pages[0].page_number);
        }
      })
      .catch((err) => {
        if (!isMounted) return;
        setError((err as Error).message);
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    fetchRoster();

    // Check batch status on load
    getBatchStatus(chapterId)
      .then((status) => {
        if (isMounted) setBatchStatus(status);
      })
      .catch(() => {});

    return () => {
      isMounted = false;
    };
  }, [chapterId, fetchRoster]);

  // 2. Fetch specific page whenever currentPageNumber changes
  const loadCurrentPage = useCallback(async (pageNum: number) => {
    if (!chapterId || pageNum < 1) return;
    setSelectedRegion(null);
    setSaveSuccess(false);

    try {
      const data = await getPage(chapterId, pageNum);
      setPageDetail(data);
      if (data.context) {
        setContext(data.context);
      } else {
        setContext({
          page: pageNum,
          characters: [],
          texts: [],
          scene: { location: null, situation: null, actions: [], mood: null },
        });
      }
    } catch (err) {
      console.error("Failed to load page data:", err);
    }
  }, [chapterId]);

  useEffect(() => {
    loadCurrentPage(currentPageNumber);
  }, [currentPageNumber, loadCurrentPage]);

  // 3. Polling for batch extraction progress
  useEffect(() => {
    if (!isBatchRunning) return;

    const interval = setInterval(async () => {
      try {
        const status = await getBatchStatus(chapterId);
        setBatchStatus(status);
        await fetchChapterData();
        await fetchRoster();

        // If batch finished, reload current page
        if (status.status !== "running") {
          await loadCurrentPage(currentPageNumber);
        }
      } catch (err) {
        console.error("Error polling batch status:", err);
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [isBatchRunning, chapterId, fetchChapterData, fetchRoster, loadCurrentPage, currentPageNumber]);

  // 4. Batch Processing Actions
  const handleStartBatch = async (skipCompleted = true, retryFailedOnly = false) => {
    try {
      const status = await startBatchExtraction(chapterId, {
        skip_completed: skipCompleted,
        retry_failed_only: retryFailedOnly,
        max_retries_per_page: 2,
      });
      setBatchStatus(status);
    } catch (err) {
      alert(`Failed to start batch extraction: ${(err as Error).message}`);
    }
  };

  const handleCancelBatch = async () => {
    try {
      const status = await cancelBatchExtraction(chapterId);
      setBatchStatus(status);
    } catch (err) {
      alert(`Failed to cancel batch: ${(err as Error).message}`);
    }
  };

  // 5. Single Page Extraction & Retry Actions
  const handleExtractSinglePage = async () => {
    if (!chapterId || extractingSingle) return;
    setExtractingSingle(true);
    try {
      const updatedPage = await extractSinglePage(chapterId, currentPageNumber);
      setPageDetail(updatedPage);
      if (updatedPage.context) setContext(updatedPage.context);
      await fetchChapterData();
      await fetchRoster();
    } catch (err) {
      alert(`Single page extraction failed: ${(err as Error).message}`);
      await loadCurrentPage(currentPageNumber);
      await fetchChapterData();
    } finally {
      setExtractingSingle(false);
    }
  };

  const handleRetrySinglePage = async () => {
    if (!chapterId || extractingSingle) return;
    setExtractingSingle(true);
    try {
      const updatedPage = await retrySinglePage(chapterId, currentPageNumber);
      setPageDetail(updatedPage);
      if (updatedPage.context) setContext(updatedPage.context);
      await fetchChapterData();
      await fetchRoster();
    } catch (err) {
      alert(`Single page retry failed: ${(err as Error).message}`);
      await loadCurrentPage(currentPageNumber);
      await fetchChapterData();
    } finally {
      setExtractingSingle(false);
    }
  };

  // 6. Save corrections callback
  const handleSave = useCallback(async () => {
    if (!chapterId || saving) return;
    try {
      setSaving(true);
      const updatedDetail = await savePageCorrection(chapterId, currentPageNumber, {
        ...context,
        page: currentPageNumber,
      });
      setPageDetail(updatedDetail);
      setSaveSuccess(true);

      if (chapter) {
        setChapter({
          ...chapter,
          pages: chapter.pages.map((p) =>
            p.page_number === currentPageNumber
              ? { ...p, status: "done", has_normalized_result: true, error_message: null }
              : p
          ),
        });
      }

      fetchRoster();
      setTimeout(() => setSaveSuccess(false), 2500);
    } catch (err) {
      alert(`Failed to save changes: ${(err as Error).message}`);
    } finally {
      setSaving(false);
    }
  }, [chapterId, currentPageNumber, context, saving, chapter, fetchRoster]);

  // 7. Character Rename & Merge actions
  const handleRenameCharacter = async (oldId: string, newId: string, name?: string, desc?: string) => {
    const updatedList = await renameCharacter(chapterId, oldId, newId, name, desc);
    setKnownCharacters(updatedList);
    await loadCurrentPage(currentPageNumber);
  };

  const handleMergeCharacters = async (sourceId: string, targetId: string, desc?: string) => {
    const updatedList = await mergeCharacters(chapterId, sourceId, targetId, desc);
    setKnownCharacters(updatedList);
    await loadCurrentPage(currentPageNumber);
  };

  // 8. Delete Page Action
  const handleDeletePage = async (pageNum: number) => {
    if (!chapterId) return;
    const confirmDelete = window.confirm(
      `Hapus Halaman ${pageNum.toString().padStart(3, "0")} dari chapter ini? Hasil ekstraksi halaman ini akan dihapus.`
    );
    if (!confirmDelete) return;

    try {
      setLoading(true);
      const updatedChapter = await deletePage(chapterId, pageNum, false);
      setChapter(updatedChapter);

      if (updatedChapter.pages.length === 0) {
        setCurrentPageNumber(1);
        setPageDetail(null);
        setContext({
          page: 1,
          characters: [],
          texts: [],
          scene: { location: null, situation: null, actions: [], mood: null },
        });
      } else {
        const nextPage = Math.min(pageNum, updatedChapter.pages.length);
        setCurrentPageNumber(nextPage);
        await loadCurrentPage(nextPage);
      }
      await fetchRoster();
    } catch (err) {
      alert(`Gagal menghapus halaman: ${(err as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  // 9. Export Actions
  const handleExportJson = () => {
    const url = getExportJsonUrl(chapterId, true);
    window.open(url, "_blank");
  };

  const handleExportTxt = () => {
    const url = getExportTxtUrl(chapterId, true);
    window.open(url, "_blank");
  };


  // 9. Keyboard shortcut listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        handleSave();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleSave]);

  if (loading) {
    return (
      <div style={{ padding: "3rem", textAlign: "center", color: "#64748b" }}>
        Loading chapter data...
      </div>
    );
  }

  if (error || !chapter) {
    return (
      <div style={{ padding: "3rem", textAlign: "center" }}>
        <p style={{ color: "#dc2626", marginBottom: "1rem" }}>{error || "Chapter not found."}</p>
        <button
          type="button"
          onClick={onBack}
          style={{
            padding: "0.5rem 1rem",
            backgroundColor: "#2563eb",
            color: "#fff",
            border: "none",
            borderRadius: "6px",
            cursor: "pointer",
          }}
        >
          Return to Chapters
        </button>
      </div>
    );
  }

  const imageUrl = getPageImageUrl(chapterId, currentPageNumber);
  const completedCount = chapter.pages.filter((p) => p.status === "done").length;
  const failedCount = chapter.pages.filter((p) => p.status === "failed" || p.status === "manual_review").length;
  const progressPercent = chapter.total_pages > 0 ? Math.round((completedCount / chapter.total_pages) * 100) : 0;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        width: "100vw",
        overflow: "hidden",
        backgroundColor: "#f8fafc",
      }}
    >
      {/* Top Review Toolbar */}
      <ReviewToolbar
        chapterTitle={chapter.title}
        currentPageNumber={currentPageNumber}
        totalPages={chapter.total_pages}
        pageStatus={pageDetail?.status || "pending"}
        saving={saving}
        saveSuccess={saveSuccess}
        extracting={extractingSingle}
        onSave={handleSave}
        onExtractPage={handleExtractSinglePage}
        onRetryPage={handleRetrySinglePage}
        onOpenRoster={() => setShowRosterModal(true)}
        onOpenContext={() => setShowContextModal(true)}
        onExportJson={handleExportJson}
        onExportTxt={handleExportTxt}
        onDeletePage={() => handleDeletePage(currentPageNumber)}
        onBack={onBack}
        onPrevPage={() => setCurrentPageNumber((p) => Math.max(p - 1, 1))}
        onNextPage={() => setCurrentPageNumber((p) => Math.min(p + 1, chapter.total_pages))}
      />


      {/* Batch Processing Control Banner */}
      <div
        style={{
          backgroundColor: isBatchRunning ? "#eff6ff" : "#f1f5f9",
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
            Extract Context <span style={{ fontWeight: 400, color: "#64748b" }}>(Gemma, cloud)</span>:{" "}
            {completedCount}/{chapter.total_pages} pages ({progressPercent}%)
            {failedCount > 0 && (
              <span style={{ color: "#ea580c", marginLeft: "0.5rem" }}>
                ({failedCount} review needed)
              </span>
            )}
          </div>

          {/* Progress Bar */}
          <div
            style={{
              flex: 1,
              height: "8px",
              backgroundColor: "#e2e8f0",
              borderRadius: "4px",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                height: "100%",
                width: `${progressPercent}%`,
                backgroundColor: isBatchRunning ? "#2563eb" : "#16a34a",
                transition: "width 0.3s ease",
              }}
            />
          </div>

          {isBatchRunning && (
            <span style={{ color: "#2563eb", fontWeight: 500, fontSize: "0.8rem", whiteSpace: "nowrap" }}>
              {batchStatus?.message || "Running batch extraction..."}
            </span>
          )}
        </div>

        {/* Action Buttons */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          {isBatchRunning ? (
            <button
              type="button"
              onClick={handleCancelBatch}
              style={{
                padding: "4px 12px",
                backgroundColor: "#dc2626",
                color: "#fff",
                border: "none",
                borderRadius: "4px",
                fontWeight: 600,
                fontSize: "0.8rem",
                cursor: "pointer",
              }}
            >
              ⏹ Cancel Batch
            </button>
          ) : (
            <>
              {completedCount < chapter.total_pages && (
                <button
                  type="button"
                  onClick={() => handleStartBatch(true, false)}
                  style={{
                    padding: "4px 12px",
                    backgroundColor: "#2563eb",
                    color: "#fff",
                    border: "none",
                    borderRadius: "4px",
                    fontWeight: 600,
                    fontSize: "0.8rem",
                    cursor: "pointer",
                  }}
                  title="Extract all pending pages"
                >
                  {completedCount === 0 ? "⚡ Extract Context" : "▶ Resume Context"}
                </button>
              )}

              {failedCount > 0 && (
                <button
                  type="button"
                  onClick={() => handleStartBatch(false, true)}
                  style={{
                    padding: "4px 10px",
                    backgroundColor: "#ea580c",
                    color: "#fff",
                    border: "none",
                    borderRadius: "4px",
                    fontWeight: 600,
                    fontSize: "0.8rem",
                    cursor: "pointer",
                  }}
                  title="Retry failed and manual review pages only"
                >
                  🔄 Retry Failed ({failedCount})
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {/* Second, independent pipeline: panel detection + crop (local) */}
      <ExtractImageBar chapter={chapter} onOpenReview={onOpenPanelReview} onRefreshChapter={fetchChapterData} />

      {/* Main 3-Column Review Layout */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        {/* Column 1: Page list */}
        <PageList
          pages={chapter.pages}
          currentPageNumber={currentPageNumber}
          onSelectPage={(pageNum) => setCurrentPageNumber(pageNum)}
          onDeletePage={(pageNum) => handleDeletePage(pageNum)}
        />


        {/* Column 2: Image Viewer with Overlays */}
        <ImageViewer
          imageUrl={imageUrl}
          characters={context.characters}
          texts={context.texts}
          selectedRegion={selectedRegion}
          onSelectRegion={setSelectedRegion}
        />

        {/* Column 3: Review / Editable Context Panel */}
        <div
          style={{
            width: "380px",
            borderLeft: "1px solid #e2e8f0",
            backgroundColor: "#f8fafc",
            height: "100%",
            overflowY: "auto",
            padding: "1rem",
            boxSizing: "border-box",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div
            style={{
              marginBottom: "1rem",
              borderBottom: "1px solid #e2e8f0",
              paddingBottom: "0.5rem",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "flex-start",
            }}
          >
            <div>
              <h3 style={{ margin: "0 0 0.25rem", fontSize: "1.1rem", color: "#0f172a" }}>
                Page {currentPageNumber.toString().padStart(3, "0")} Context
              </h3>
              <span style={{ fontSize: "0.8rem", color: "#64748b" }}>
                Inspect and edit detected characters, dialogue, and scene context.
              </span>
            </div>
          </div>

          {/* Manual review notice if extraction encountered error */}
          {(pageDetail?.status === "manual_review" || pageDetail?.status === "failed") && (
            <div
              style={{
                backgroundColor: "#fff7ed",
                border: "1px solid #fed7aa",
                borderRadius: "6px",
                padding: "0.75rem",
                marginBottom: "1rem",
                fontSize: "0.85rem",
                color: "#9a3412",
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: "0.25rem" }}>
                ⚠ Extraction Needs Manual Review
              </div>
              {pageDetail.context?.review_flags?.length ? (
                <>
                  <ul style={{ margin: 0, paddingLeft: "1.1rem" }}>
                    {pageDetail.context.review_flags.map((flag) => (
                      <li key={flag}>{flag}</li>
                    ))}
                  </ul>
                  <div style={{ marginTop: "0.4rem", fontSize: "0.8rem" }}>
                    Check the text against the image. Saving corrections marks this page as reviewed.
                  </div>
                </>
              ) : (
                <div>{pageDetail.error_message || "Model output could not be automatically parsed."}</div>
              )}
              <div style={{ marginTop: "0.5rem" }}>
                <button
                  type="button"
                  onClick={handleRetrySinglePage}
                  disabled={extractingSingle}
                  style={{
                    backgroundColor: "#ea580c",
                    color: "#fff",
                    border: "none",
                    borderRadius: "4px",
                    padding: "3px 8px",
                    fontSize: "0.8rem",
                    fontWeight: 600,
                    cursor: extractingSingle ? "not-allowed" : "pointer",
                  }}
                >
                  {extractingSingle ? "Retrying..." : "⚡ Retry This Page"}
                </button>
              </div>
            </div>
          )}

          <CharacterPanel
            characters={context.characters}
            onChange={(chars) => setContext((c) => ({ ...c, characters: chars }))}
            selectedRegion={selectedRegion}
            onSelectRegion={setSelectedRegion}
          />

          <TextPanel
            texts={context.texts}
            hasText={context.has_text}
            ocrConfidence={context.ocr_confidence}
            onChange={(texts) => setContext((c) => ({ ...c, texts }))}
            selectedRegion={selectedRegion}
            onSelectRegion={setSelectedRegion}
          />

          <ScenePanel
            scene={context.scene}
            onChange={(scene) => setContext((c) => ({ ...c, scene }))}
            visualSummary={context.visual_summary}
            onVisualSummaryChange={(visual_summary) => setContext((c) => ({ ...c, visual_summary }))}
          />

          <div style={{ marginTop: "1rem", paddingTop: "0.5rem", borderTop: "1px solid #e2e8f0" }}>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              style={{
                width: "100%",
                padding: "0.75rem",
                backgroundColor: saveSuccess ? "#16a34a" : "#2563eb",
                color: "#fff",
                border: "none",
                borderRadius: "6px",
                fontWeight: 600,
                fontSize: "0.95rem",
                cursor: saving ? "not-allowed" : "pointer",
                transition: "background-color 0.2s ease",
              }}
            >
              {saving ? "Saving..." : saveSuccess ? "✓ Changes Saved!" : "Save Corrections (Ctrl+S)"}
            </button>
          </div>
        </div>
      </div>

      {/* Character Roster Modal */}
      {showRosterModal && (
        <CharacterRosterModal
          characters={knownCharacters}
          onClose={() => setShowRosterModal(false)}
          onRename={handleRenameCharacter}
          onMerge={handleMergeCharacters}
          onSelectPage={(pageNum) => setCurrentPageNumber(pageNum)}
        />
      )}

      {/* Chapter Context Modal */}
      {showContextModal && (
        <ChapterContextModal
          chapterId={chapterId}
          chapterTitle={chapter.title}
          onClose={() => setShowContextModal(false)}
        />
      )}
    </div>
  );
};

export default ChapterPage;
