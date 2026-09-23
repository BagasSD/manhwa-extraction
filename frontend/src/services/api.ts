import type {
  BatchExtractRequest,
  BatchJobStatus,
  BenchmarkRunRequest,
  BenchmarkRunResult,
  Chapter,
  ChapterContext,
  ChapterSummary,
  KnownCharacter,
  PageContext,
  PageDetail,
  PageInfo,
} from "../types/context";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface HealthResponse {
  status: string;
  app: string;
  env: string;
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/health`);
  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status}`);
  }
  return response.json();
}

export async function listChapters(): Promise<ChapterSummary[]> {
  const response = await fetch(`${API_BASE_URL}/chapters`);
  if (!response.ok) {
    throw new Error(`Failed to list chapters: ${response.statusText}`);
  }
  return response.json();
}

export async function getChapter(id: string): Promise<Chapter> {
  const response = await fetch(`${API_BASE_URL}/chapters/${id}`);
  if (!response.ok) {
    throw new Error(`Failed to get chapter ${id}: ${response.statusText}`);
  }
  return response.json();
}

export async function createChapter(payload: {
  id?: string;
  title: string;
  source_path: string;
}): Promise<Chapter> {
  const response = await fetch(`${API_BASE_URL}/chapters`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to create chapter: ${response.statusText}`);
  }
  return response.json();
}

export async function downloadChapterFromUrl(payload: {
  url: string;
  title?: string;
  id?: string;
  custom_headers?: Record<string, string>;
}): Promise<Chapter> {
  const response = await fetch(`${API_BASE_URL}/chapters/download`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to download chapter: ${response.statusText}`);
  }
  return response.json();
}


export async function deleteChapter(id: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/chapters/${id}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`Failed to delete chapter: ${response.statusText}`);
  }
}

export async function listPages(chapterId: string): Promise<PageInfo[]> {
  const response = await fetch(`${API_BASE_URL}/chapters/${chapterId}/pages`);
  if (!response.ok) {
    throw new Error(`Failed to list pages: ${response.statusText}`);
  }
  return response.json();
}

export async function getPage(chapterId: string, pageNum: number): Promise<PageDetail> {
  const response = await fetch(`${API_BASE_URL}/chapters/${chapterId}/pages/${pageNum}`);
  if (!response.ok) {
    throw new Error(`Failed to get page ${pageNum}: ${response.statusText}`);
  }
  return response.json();
}

export function getPageImageUrl(chapterId: string, pageNum: number): string {
  return `${API_BASE_URL}/chapters/${chapterId}/pages/${pageNum}/image`;
}

export async function deletePage(
  chapterId: string,
  pageNum: number,
  deleteFile = false
): Promise<Chapter> {
  const response = await fetch(
    `${API_BASE_URL}/chapters/${chapterId}/pages/${pageNum}?delete_file=${deleteFile}`,
    {
      method: "DELETE",
    }
  );
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to delete page ${pageNum}: ${response.statusText}`);
  }
  return response.json();
}


export async function savePageCorrection(
  chapterId: string,
  pageNum: number,
  context: PageContext
): Promise<PageDetail> {
  const response = await fetch(`${API_BASE_URL}/chapters/${chapterId}/pages/${pageNum}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(context),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to save page correction: ${response.statusText}`);
  }
  return response.json();
}

export async function getKnownCharacters(chapterId: string): Promise<KnownCharacter[]> {
  const response = await fetch(`${API_BASE_URL}/chapters/${chapterId}/characters`);
  if (!response.ok) {
    throw new Error(`Failed to get characters: ${response.statusText}`);
  }
  return response.json();
}

export async function renameCharacter(
  chapterId: string,
  oldId: string,
  newId: string,
  name?: string,
  description?: string
): Promise<KnownCharacter[]> {
  const response = await fetch(`${API_BASE_URL}/chapters/${chapterId}/characters/rename`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ old_id: oldId, new_id: newId, name, description }),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to rename character: ${response.statusText}`);
  }
  return response.json();
}

export async function mergeCharacters(
  chapterId: string,
  sourceId: string,
  targetId: string,
  description?: string
): Promise<KnownCharacter[]> {
  const response = await fetch(`${API_BASE_URL}/chapters/${chapterId}/characters/merge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_id: sourceId, target_id: targetId, description }),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to merge characters: ${response.statusText}`);
  }
  return response.json();
}

export async function startBatchExtraction(
  chapterId: string,
  payload?: BatchExtractRequest
): Promise<BatchJobStatus> {
  const response = await fetch(`${API_BASE_URL}/chapters/${chapterId}/extract`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to start batch extraction: ${response.statusText}`);
  }
  return response.json();
}

export async function cancelBatchExtraction(chapterId: string): Promise<BatchJobStatus> {
  const response = await fetch(`${API_BASE_URL}/chapters/${chapterId}/extract/cancel`, {
    method: "POST",
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to cancel batch extraction: ${response.statusText}`);
  }
  return response.json();
}

export async function getBatchStatus(chapterId: string): Promise<BatchJobStatus> {
  const response = await fetch(`${API_BASE_URL}/chapters/${chapterId}/extract/status`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to get batch status: ${response.statusText}`);
  }
  return response.json();
}

export async function extractSinglePage(chapterId: string, pageNum: number): Promise<PageDetail> {
  const response = await fetch(`${API_BASE_URL}/chapters/${chapterId}/pages/${pageNum}/extract`, {
    method: "POST",
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to extract page ${pageNum}: ${response.statusText}`);
  }
  return response.json();
}

export async function retrySinglePage(chapterId: string, pageNum: number): Promise<PageDetail> {
  const response = await fetch(`${API_BASE_URL}/chapters/${chapterId}/pages/${pageNum}/retry`, {
    method: "POST",
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to retry page ${pageNum}: ${response.statusText}`);
  }
  return response.json();
}

export async function generateChapterContext(
  chapterId: string,
  force = false
): Promise<ChapterContext> {
  const url = `${API_BASE_URL}/chapters/${chapterId}/context${force ? "?force=true" : ""}`;
  const response = await fetch(url, { method: "POST" });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to generate chapter context: ${response.statusText}`);
  }
  return response.json();
}

export async function getChapterContext(chapterId: string): Promise<ChapterContext> {
  const response = await fetch(`${API_BASE_URL}/chapters/${chapterId}/context`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to get chapter context: ${response.statusText}`);
  }
  return response.json();
}

export async function saveChapterContext(
  chapterId: string,
  context: ChapterContext
): Promise<ChapterContext> {
  const response = await fetch(`${API_BASE_URL}/chapters/${chapterId}/context`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(context),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to save chapter context: ${response.statusText}`);
  }
  return response.json();
}

export function getExportJsonUrl(chapterId: string, download = true): string {
  return `${API_BASE_URL}/chapters/${chapterId}/export/json${download ? "?download=true" : ""}`;
}

export function getExportTxtUrl(chapterId: string, download = true): string {
  return `${API_BASE_URL}/chapters/${chapterId}/export/txt${download ? "?download=true" : ""}`;
}

export async function runBenchmark(payload: BenchmarkRunRequest = {}): Promise<BenchmarkRunResult> {
  const response = await fetch(`${API_BASE_URL}/benchmark/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to run benchmark: ${response.statusText}`);
  }
  return response.json();
}

export async function listBenchmarkResults(): Promise<BenchmarkRunResult[]> {
  const response = await fetch(`${API_BASE_URL}/benchmark/results`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to list benchmark results: ${response.statusText}`);
  }
  return response.json();
}

export async function getBenchmarkResult(runId: string): Promise<BenchmarkRunResult> {
  const response = await fetch(`${API_BASE_URL}/benchmark/results/${runId}`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to get benchmark result: ${response.statusText}`);
  }
  return response.json();
}

