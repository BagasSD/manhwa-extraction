/** Domain types for Manhwa Context Extractor */

export type TextRegionType =
  | "speech"
  | "thought"
  | "narration"
  | "caption"
  | "system"
  | "sfx"
  | "sign"
  | "unknown"
  | "sp"
  | "th"
  | "na"
  | "ca"
  | "ui"
  | "sx"
  | "uk";

export interface Character {
  id: string;
  description: string | null;
  bbox: number[] | null;
  expression: string | null;
  emotion: string | null;
  action: string | null;
}

export interface KnownCharacter {
  id: string;
  name: string | null;
  description: string | null;
  first_seen_page: number;
  occurrences: number;
  pages: number[];
}

export interface TextRegion {
  id: string;
  text: string;
  speaker: string | null;
  target: string | null;
  type: TextRegionType | string;
  bbox: number[] | null;
  order: number;
  confidence?: number | null;
}

export interface Scene {
  location: string | null;
  situation: string | null;
  actions: string[];
  mood: string | null;
}

export interface PageContext {
  page: number;
  characters: Character[];
  texts: TextRegion[];
  scene: Scene;
  visual_summary?: string | null;
  /** Model's claim that the page shows text (null = not reported). */
  has_text?: boolean | null;
  /** Model-reported legibility of the page text. */
  ocr_confidence?: "high" | "medium" | "low" | null;
  /** Suspicious-extraction warnings kept after all retries; cleared by saving a correction. */
  review_flags?: string[];
}

export interface PageInfo {
  page_number: number;
  filename: string;
  file_path: string;
  status: "pending" | "processing" | "done" | "failed" | "manual_review" | string;
  has_raw_result: boolean;
  has_normalized_result: boolean;
  error_message?: string | null;
}

export interface PageDetail extends PageInfo {
  raw_result?: Record<string, unknown> | null;
  context?: PageContext | null;
}

export interface ChapterSummary {
  id: string;
  title: string;
  source_path: string;
  total_pages: number;
  completed_pages: number;
  failed_pages: number;
  created_at: string;
  updated_at: string;
}

export interface Chapter extends ChapterSummary {
  pages: PageInfo[];
}

export interface ChapterDownloadRequest {
  url: string;
  title?: string;
  id?: string;
  custom_headers?: Record<string, string>;
}


export interface SelectedRegion {
  kind: "character" | "text";
  index: number;
}

export interface BatchExtractRequest {
  skip_completed?: boolean;
  force_all?: boolean;
  retry_failed_only?: boolean;
  max_retries_per_page?: number;
}

export interface BatchJobStatus {
  chapter_id: string;
  status: "idle" | "running" | "completed" | "cancelled" | "failed";
  current_page: number | null;
  total_pages: number;
  processed_pages: number;
  completed_pages: number;
  failed_pages: number;
  manual_review_pages: number;
  message: string | null;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
}

export interface ChapterCharacterContext {
  id: string;
  name?: string | null;
  description?: string | null;
  role?: string | null;
  actions: string[];
}

export interface ChapterEvent {
  pages: number[];
  event: string;
  characters_involved: string[];
}

export interface ChapterTransition {
  pages: number[];
  description: string;
  from_location?: string | null;
  to_location?: string | null;
}

export interface ChapterDialogue {
  page: number;
  speaker?: string | null;
  target?: string | null;
  text: string;
}

export interface ChapterContext {
  chapter_id: string;
  title?: string | null;
  summary?: string | null;
  characters: ChapterCharacterContext[];
  events: ChapterEvent[];
  transitions: ChapterTransition[];
  important_dialogue: ChapterDialogue[];
}

export type PreprocessMode =
  | "original"
  | "upscale"
  | "enhanced"
  | "grayscale"
  | "contrast"
  | "sharpen"
  | "tiled";

export interface BenchmarkRunRequest {
  modes?: PreprocessMode[];
  fixture_dir?: string | null;
  max_pages?: number | null;
}

export interface PageBenchmarkResult {
  page_path: string;
  mode: PreprocessMode;
  success: boolean;
  processing_time_ms: number;
  attempts: number;
  character_count: number;
  text_count: number;
  has_scene: boolean;
  error?: string | null;
  raw_response_size: number;
  expected_text_count?: number | null;
  matched_text_count?: number | null;
  text_recall?: number | null;
  flagged?: boolean;
}

export interface ModeSummary {
  mode: PreprocessMode;
  total_pages: number;
  success_count: number;
  failure_count: number;
  json_validity_rate: number;
  avg_processing_time_ms: number;
  total_processing_time_ms: number;
  avg_attempts: number;
  avg_character_count: number;
  avg_text_count: number;
  retry_rate: number;
  avg_text_recall?: number | null;
  missed_text_pages?: number;
  hallucinated_text_pages?: number;
  flagged_pages?: number;
}

export interface BenchmarkRunResult {
  run_id: string;
  status: "pending" | "running" | "done" | "failed";
  started_at: string;
  finished_at?: string | null;
  modes_tested: PreprocessMode[];
  fixture_dir: string;
  total_fixtures: number;
  page_results: PageBenchmarkResult[];
  mode_summaries: ModeSummary[];
  recommended_mode?: PreprocessMode | null;
  errors: string[];
  extra?: Record<string, unknown>;
}

