import { useCallback, useEffect, useState } from "react";
import { getHealth, listChapters, type HealthResponse } from "./services/api";
import type { ChapterSummary } from "./types/context";
import Home from "./pages/Home";
import ChapterPage from "./pages/Chapter";
import PanelReviewView from "./pages/PanelReviewView";

type BackendStatus =
  | { state: "checking" }
  | { state: "ok"; data: HealthResponse }
  | { state: "error"; message: string };

function App() {
  const [backend, setBackend] = useState<BackendStatus>({ state: "checking" });
  const [selectedChapterId, setSelectedChapterId] = useState<string | null>(null);
  const [chapters, setChapters] = useState<ChapterSummary[]>([]);
  // Chapter screens: text/context review or the separate panel (Extract Image) review
  const [chapterView, setChapterView] = useState<"context" | "panels">("context");
  const openPanelReview = useCallback(() => setChapterView("panels"), []);

  useEffect(() => {
    getHealth()
      .then((data) => setBackend({ state: "ok", data }))
      .catch((err) =>
        setBackend({ state: "error", message: (err as Error).message }),
      );
  }, []);

  // Keep chapters list fresh so prev/next chapter nav works everywhere
  const refreshChapters = useCallback(async () => {
    try {
      const data = await listChapters();
      setChapters(data);
    } catch {
      // silently ignore; chapter list is best-effort for nav purposes
    }
  }, []);

  useEffect(() => {
    refreshChapters();
  }, [refreshChapters]);

  // Derive prev/next chapter ids from the sorted chapters list
  const currentChapterIndex = chapters.findIndex((c) => c.id === selectedChapterId);
  const prevChapterId = currentChapterIndex > 0 ? chapters[currentChapterIndex - 1].id : null;
  const nextChapterId =
    currentChapterIndex >= 0 && currentChapterIndex < chapters.length - 1
      ? chapters[currentChapterIndex + 1].id
      : null;

  const navigateToChapter = useCallback(
    (id: string) => {
      setChapterView("context");
      setSelectedChapterId(id);
    },
    [],
  );

  if (selectedChapterId && chapterView === "panels") {
    return (
      <PanelReviewView
        chapterId={selectedChapterId}
        onBack={() => setChapterView("context")}
      />
    );
  }

  if (selectedChapterId) {
    return (
      <ChapterPage
        chapterId={selectedChapterId}
        onBack={() => setSelectedChapterId(null)}
        onOpenPanelReview={openPanelReview}
        onPrevChapter={prevChapterId ? () => navigateToChapter(prevChapterId) : undefined}
        onNextChapter={nextChapterId ? () => navigateToChapter(nextChapterId) : undefined}
        hasPrevChapter={prevChapterId !== null}
        hasNextChapter={nextChapterId !== null}
      />
    );
  }

  return (
    <div style={{ fontFamily: "sans-serif", margin: 0, padding: 0 }}>
      {/* Backend connection banner */}
      <div
        style={{
          padding: "0.5rem 1.5rem",
          backgroundColor: backend.state === "ok" ? "#f0fdf4" : "#fef2f2",
          borderBottom: "1px solid #e2e8f0",
          fontSize: "0.85rem",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          color: backend.state === "ok" ? "#166534" : "#991b1b",
        }}
      >
        <span>
          Backend{" "}
          {backend.state === "checking" && "connecting..."}
          {backend.state === "ok" &&
            `connected (${backend.data.app}, env=${backend.data.env})`}
          {backend.state === "error" && `unreachable (${backend.message})`}
        </span>
      </div>

      <Home
        onSelectChapter={(id) => {
          setChapterView("context");
          setSelectedChapterId(id);
          refreshChapters();
        }}
      />
    </div>
  );
}

export default App;
