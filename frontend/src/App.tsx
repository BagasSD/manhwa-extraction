import { useCallback, useEffect, useState } from "react";
import { getHealth, type HealthResponse } from "./services/api";
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
          Backend:{" "}
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
        }}
      />
    </div>
  );
}

export default App;
