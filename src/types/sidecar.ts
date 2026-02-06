export interface HealthResponse {
  status: string;
}

export type PageType = "text" | "scanned" | "mixed";
export type InputMode = "pdf" | "text" | "image";

export interface PageDetection {
  page_number: number;
  page_type: PageType;
  char_count: number;
  confidence: number;
}

export interface DetectionResult {
  overall_type: PageType;
  total_pages: number;
  pages: PageDetection[];
}

export interface ExtractedTable {
  page_number: number;
  table_index: number;
  headers: string[];
  rows: string[][];
}

export interface PageExtractionResult {
  page_number: number;
  text: string;
  extraction_method: string;
  confidence: number;
  char_count: number;
}

export interface ExtractionResult {
  input_mode: InputMode;
  full_text: string;
  pages: PageExtractionResult[];
  tables: ExtractedTable[];
  detection: DetectionResult | null;
  total_pages: number;
  total_chars: number;
  filename: string | null;
  warnings: string[];
}

export interface ExtractionError {
  detail: string;
}

// --- Phase 3: Analysis Types ---

export type SeverityStatus =
  | "normal"
  | "mildly_abnormal"
  | "moderately_abnormal"
  | "severely_abnormal"
  | "undetermined";

export type AbnormalityDirection = "normal" | "above_normal" | "below_normal";

export interface PriorValue {
  value: number;
  time_label: string;
}

export interface ParsedMeasurement {
  name: string;
  abbreviation: string;
  value: number;
  unit: string;
  status: SeverityStatus;
  direction: AbnormalityDirection;
  reference_range: string | null;
  prior_values: PriorValue[];
  raw_text: string;
  page_number: number | null;
}

export interface ReportSection {
  name: string;
  content: string;
  page_number: number | null;
}

export interface ParsedReport {
  test_type: string;
  test_type_display: string;
  detection_confidence: number;
  measurements: ParsedMeasurement[];
  sections: ReportSection[];
  findings: string[];
  warnings: string[];
}

export interface TestTypeInfo {
  test_type_id: string;
  display_name: string;
  keywords: string[];
  category?: string;
}

export interface DetectTypeResponse {
  test_type: string | null;
  confidence: number;
  available_types: TestTypeInfo[];
  detection_method: "keyword" | "llm" | "none";
  llm_attempted: boolean;
}

export interface ParseRequest {
  extraction_result: ExtractionResult;
  test_type?: string;
}

// --- Phase 4: LLM Explanation Types ---

export type LLMProvider = "claude" | "openai";
export type LiteracyLevel = "grade_4" | "grade_6" | "grade_8" | "grade_12" | "clinical";
export type ExplanationVoice = "first_person" | "third_person";
export type PhysicianNameSource = "auto_extract" | "custom" | "generic";
export type FooterType = "explify_branding" | "ai_disclaimer" | "custom" | "none";

export interface MeasurementExplanation {
  abbreviation: string;
  value: number;
  unit: string;
  status: SeverityStatus;
  plain_language: string;
}

export interface FindingExplanation {
  finding: string;
  severity: "normal" | "mild" | "moderate" | "severe" | "informational";
  explanation: string;
}

export interface ExplanationResult {
  overall_summary: string;
  measurements: MeasurementExplanation[];
  key_findings: FindingExplanation[];
  questions_for_doctor: string[];
  disclaimer: string;
}

export interface ExplainRequest {
  extraction_result: ExtractionResult;
  test_type?: string;
  literacy_level?: LiteracyLevel;
  provider?: LLMProvider;
  api_key?: string;
  clinical_context?: string;
  template_id?: number;
  shared_template_sync_id?: string;
  refinement_instruction?: string;
  tone_preference?: number;
  detail_preference?: number;
  next_steps?: string[];
  short_comment?: boolean;
  sms_summary?: boolean;
  explanation_voice?: ExplanationVoice;
  name_drop?: boolean;
  physician_name_override?: string;
  include_key_findings?: boolean;
  include_measurements?: boolean;
  patient_age?: number;
  patient_gender?: string;
  deep_analysis?: boolean;
}

export interface ExplainResponse {
  explanation: ExplanationResult;
  parsed_report: ParsedReport;
  validation_warnings: string[];
  phi_categories_found: string[];
  physician_name?: string;
  model_used: string;
  input_tokens: number;
  output_tokens: number;
}

export interface GlossaryResponse {
  test_type: string;
  glossary: Record<string, string>;
}

export interface AppSettings {
  llm_provider: LLMProvider;
  claude_api_key: string | null;
  openai_api_key: string | null;
  claude_model: string | null;
  openai_model: string | null;
  literacy_level: LiteracyLevel;
  specialty: string | null;
  practice_name: string | null;
  include_key_findings: boolean;
  include_measurements: boolean;
  tone_preference: number;
  detail_preference: number;
  quick_reasons: string[];
  next_steps_options: string[];
  explanation_voice: ExplanationVoice;
  name_drop: boolean;
  physician_name_source: PhysicianNameSource;
  custom_physician_name: string | null;
  practice_providers: string[];
  short_comment_char_limit: number | null;
  sms_summary_enabled: boolean;
  sms_summary_char_limit: number;
  footer_type: FooterType;
  custom_footer_text: string | null;
}

export interface SettingsUpdate {
  llm_provider?: LLMProvider;
  claude_api_key?: string;
  openai_api_key?: string;
  claude_model?: string;
  openai_model?: string;
  literacy_level?: LiteracyLevel;
  specialty?: string;
  practice_name?: string;
  include_key_findings?: boolean;
  include_measurements?: boolean;
  tone_preference?: number;
  detail_preference?: number;
  quick_reasons?: string[];
  next_steps_options?: string[];
  explanation_voice?: ExplanationVoice;
  name_drop?: boolean;
  physician_name_source?: PhysicianNameSource;
  custom_physician_name?: string;
  practice_providers?: string[];
  short_comment_char_limit?: number | null;
  sms_summary_enabled?: boolean;
  sms_summary_char_limit?: number;
  footer_type?: FooterType;
  custom_footer_text?: string | null;
}

// --- Template Types ---

export interface Template {
  id: number;
  name: string;
  test_type: string | null;
  tone: string | null;
  structure_instructions: string | null;
  closing_text: string | null;
  created_at: string;
  updated_at: string;
  sync_id?: string;
  is_builtin?: boolean | number;
}

export interface TemplateCreateRequest {
  name: string;
  test_type?: string;
  tone?: string;
  structure_instructions?: string;
  closing_text?: string;
}

export interface TemplateUpdateRequest {
  name?: string;
  test_type?: string;
  tone?: string;
  structure_instructions?: string;
  closing_text?: string;
}

export interface TemplateListResponse {
  items: Template[];
  total: number;
}

// --- Phase 6: History Types ---

export interface HistoryListItem {
  id: number;
  created_at: string;
  test_type: string;
  test_type_display: string;
  filename: string | null;
  summary: string;
  liked: boolean;
  sync_id?: string;
  updated_at?: string;
}

export interface HistoryListResponse {
  items: HistoryListItem[];
  total: number;
  offset: number;
  limit: number;
}

export interface HistoryDetailResponse extends HistoryListItem {
  full_response: ExplainResponse;
  edited_text?: string;
}

export interface HistoryCreateRequest {
  test_type: string;
  test_type_display: string;
  filename: string | null;
  summary: string;
  full_response: ExplainResponse;
  tone_preference?: number;
  detail_preference?: number;
}

export interface HistoryDeleteResponse {
  deleted: boolean;
  id: number;
}

export interface HistoryLikeRequest {
  liked: boolean;
}

export interface HistoryLikeResponse {
  id: number;
  liked: boolean;
}

export interface ConsentStatusResponse {
  consent_given: boolean;
}

// --- Letter Types ---

export interface LetterGenerateRequest {
  prompt: string;
  letter_type?: string;
}

export interface LetterResponse {
  id: number;
  created_at: string;
  prompt: string;
  content: string;
  letter_type: string;
  liked: boolean;
  model_used?: string;
  input_tokens?: number;
  output_tokens?: number;
  sync_id?: string;
  updated_at?: string;
}

export interface LetterListResponse {
  items: LetterResponse[];
  total: number;
}

export interface LetterDeleteResponse {
  deleted: boolean;
  id: number;
}

// --- Teaching Points Types ---

export interface TeachingPoint {
  id: number;
  text: string;
  test_type: string | null;
  created_at: string;
  sync_id?: string;
  updated_at?: string;
}

// --- Shared Content Types ---

export interface SharedTeachingPoint {
  id: number;
  sync_id: string;
  text: string;
  test_type: string | null;
  sharer_user_id: string;
  sharer_email: string;
  created_at: string;
  updated_at: string;
}

export interface SharedTemplate {
  id: number;
  sync_id: string;
  name: string;
  test_type: string | null;
  tone: string | null;
  structure_instructions: string | null;
  closing_text: string | null;
  sharer_user_id: string;
  sharer_email: string;
  created_at: string;
  updated_at: string;
}
