import React, { useEffect, useState } from "react";
import type { ChapterSummary } from "../types/context";
import { createChapter, downloadChapterFromUrl, listChapters } from "../services/api";
import { ChapterList } from "../components/ChapterList/ChapterList";

interface HomeProps {
  onSelectChapter: (id: string) => void;
}

export const Home: React.FC<HomeProps> = ({ onSelectChapter }) => {
  const [chapters, setChapters] = useState<ChapterSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchChapters = async () => {
    setLoading(true);
    try {
      const data = await listChapters();
      setChapters(data);
    } catch (err) {
      console.error("Failed to load chapters:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchChapters();
  }, []);

  const handleCreateChapter = async (payload: { title: string; source_path: string }) => {
    const newChapter = await createChapter(payload);
    await fetchChapters();
    onSelectChapter(newChapter.id);
  };

  const handleDownloadChapter = async (payload: { url: string; title?: string; id?: string }) => {
    const newChapter = await downloadChapterFromUrl(payload);
    await fetchChapters();
    onSelectChapter(newChapter.id);
  };

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "#f8fafc" }}>
      <ChapterList
        chapters={chapters}
        onSelectChapter={onSelectChapter}
        onCreateChapter={handleCreateChapter}
        onDownloadChapter={handleDownloadChapter}
        loading={loading}
      />
    </div>
  );
};

export default Home;

