import { IS_TAURI, API_BASE_URL } from "./platform";
import { getSession } from "./supabase";
import type {
  HealthResponse,
  ExtractionResult,
  DetectionResult,
  DetectTypeResponse,
  ParsedReport,
  ExplainRequest,
  ExplainResponse,
  GlossaryResponse,
  AppSettings,
  SettingsUpdate,
  Template,
  TemplateCreateRequest,
  TemplateUpdateRequest,
  TemplateListResponse,
  HistoryListResponse,
  HistoryDetailResponse,
  HistoryCreateRequest,
  HistoryDeleteResponse,
  HistoryLikeResponse,
  ConsentStatusResponse,
  LetterGenerateRequest,
  LetterResponse,
  LetterListResponse,
  LetterDeleteResponse,
  TeachingPoint,
  SharedTeachingPoint,
  SharedTemplate,
} from "../types/sidecar";

class SidecarApi {
  private baseUrl: string | null = null;

  async initialize(): Promise<void> {
    if (IS_TAURI) {
      const { invoke } = await import("@tauri-apps/api/core");
      const port = await invoke<number>("get_sidecar_port");
      this.baseUrl = `http://127.0.0.1:${port}`;
    } else {
      if (!API_BASE_URL) {
        throw new Error(
          "VITE_API_URL is not configured. Set it in your .env file.",
        );
      }
      this.baseUrl = API_BASE_URL;
    }
  }

  async waitForReady(maxRetries = 30, intervalMs = 500): Promise<boolean> {
    for (let i = 0; i < maxRetries; i++) {
      try {
        if (!this.baseUrl) {
          await this.initialize();
        }
        const health = await this.healthCheck();
        if (health.status === "ok") {
          return true;
        }
      } catch {
        // Sidecar not ready yet
      }
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
    return false;
  }

  private async ensureInitialized(): Promise<string> {
    if (!this.baseUrl) {
      try {
        await this.initialize();
      } catch {
        throw new Error(
          "SidecarApi not initialized. Backend may still be starting.",
        );
      }
    }
    return this.baseUrl!;
  }

  private async handleErrorResponse(response: Response): Promise<never> {
    let detail = `Request failed: ${response.status}`;
    try {
      const body = await response.json();
      if (body.detail) {
        if (typeof body.detail === "string") {
          detail = body.detail;
        } else if (Array.isArray(body.detail)) {
          detail = body.detail
            .map((d: { msg?: string }) => d.msg || JSON.stringify(d))
            .join("; ");
        } else {
          detail = JSON.stringify(body.detail);
        }
      }
    } catch {
      // Response body wasn't JSON
    }
    throw new Error(detail);
  }

  private async fetchWithAuth(
    url: string,
    init?: RequestInit,
  ): Promise<Response> {
    if (!IS_TAURI) {
      const session = await getSession();
      const token = session?.access_token;
      if (token) {
        const headers = new Headers(init?.headers);
        headers.set("Authorization", `Bearer ${token}`);
        return fetch(url, { ...init, headers });
      }
    }
    return fetch(url, init);
  }

  async healthCheck(): Promise<HealthResponse> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/health`, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Health check failed: ${response.status}`);
    }
    return response.json();
  }

  async extractPdf(file: File): Promise<ExtractionResult> {
    const baseUrl = await this.ensureInitialized();
    const formData = new FormData();
    formData.append("file", file);

    const response = await this.fetchWithAuth(`${baseUrl}/extract/pdf`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      await this.handleErrorResponse(response);
    }

    return response.json();
  }

  async extractFile(file: File): Promise<ExtractionResult> {
    const baseUrl = await this.ensureInitialized();
    const formData = new FormData();
    formData.append("file", file);

    const response = await this.fetchWithAuth(`${baseUrl}/extract/file`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      await this.handleErrorResponse(response);
    }

    return response.json();
  }

  async extractText(text: string): Promise<ExtractionResult> {
    const baseUrl = await this.ensureInitialized();

    const response = await this.fetchWithAuth(`${baseUrl}/extract/text`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });

    if (!response.ok) {
      await this.handleErrorResponse(response);
    }

    return response.json();
  }

  async classifyInput(
    text: string,
  ): Promise<{ classification: "report" | "question"; confidence: number }> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/analyze/classify-input`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async detectPdfType(file: File): Promise<DetectionResult> {
    const baseUrl = await this.ensureInitialized();
    const formData = new FormData();
    formData.append("file", file);

    const response = await this.fetchWithAuth(`${baseUrl}/detect`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      await this.handleErrorResponse(response);
    }

    return response.json();
  }

  async scrubPreview(
    fullText: string,
    clinicalContext?: string,
  ): Promise<{
    scrubbed_text: string;
    scrubbed_clinical_context: string;
    phi_found: string[];
    redaction_count: number;
  }> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/extraction/scrub-preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        full_text: fullText,
        clinical_context: clinicalContext ?? "",
      }),
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async detectTestType(
    extractionResult: ExtractionResult,
    userHint?: string,
  ): Promise<DetectTypeResponse> {
    const baseUrl = await this.ensureInitialized();

    const response = await this.fetchWithAuth(`${baseUrl}/analyze/detect-type`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        extraction_result: extractionResult,
        user_hint: userHint || null,
      }),
    });

    if (!response.ok) {
      await this.handleErrorResponse(response);
    }

    return response.json();
  }

  async parseReport(
    extractionResult: ExtractionResult,
    testType?: string,
  ): Promise<ParsedReport> {
    const baseUrl = await this.ensureInitialized();

    const response = await this.fetchWithAuth(`${baseUrl}/analyze/parse`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        extraction_result: extractionResult,
        test_type: testType ?? null,
      }),
    });

    if (!response.ok) {
      await this.handleErrorResponse(response);
    }

    return response.json();
  }

  async explainReport(request: ExplainRequest): Promise<ExplainResponse> {
    const baseUrl = await this.ensureInitialized();

    const body: Record<string, unknown> = {
      extraction_result: request.extraction_result,
    };
    if (request.test_type != null) body.test_type = request.test_type;
    if (request.literacy_level != null)
      body.literacy_level = request.literacy_level;
    if (request.provider != null) body.provider = request.provider;
    if (request.api_key != null) body.api_key = request.api_key;
    if (request.clinical_context != null)
      body.clinical_context = request.clinical_context;
    if (request.template_id != null) body.template_id = request.template_id;
    if (request.shared_template_sync_id != null)
      body.shared_template_sync_id = request.shared_template_sync_id;
    if (request.refinement_instruction != null)
      body.refinement_instruction = request.refinement_instruction;
    if (request.tone_preference != null)
      body.tone_preference = request.tone_preference;
    if (request.detail_preference != null)
      body.detail_preference = request.detail_preference;
    if (request.next_steps != null) body.next_steps = request.next_steps;
    if (request.short_comment != null)
      body.short_comment = request.short_comment;
    if (request.sms_summary != null)
      body.sms_summary = request.sms_summary;
    if (request.explanation_voice != null)
      body.explanation_voice = request.explanation_voice;
    if (request.name_drop != null)
      body.name_drop = request.name_drop;
    if (request.physician_name_override != null)
      body.physician_name_override = request.physician_name_override;
    if (request.include_key_findings != null)
      body.include_key_findings = request.include_key_findings;
    if (request.include_measurements != null)
      body.include_measurements = request.include_measurements;
    if (request.deep_analysis != null)
      body.deep_analysis = request.deep_analysis;
    if (request.high_anxiety_mode != null)
      body.high_anxiety_mode = request.high_anxiety_mode;
    if (request.quick_reasons != null)
      body.quick_reasons = request.quick_reasons;
    if (request.use_analogies != null)
      body.use_analogies = request.use_analogies;
    if (request.quick_normal != null)
      body.quick_normal = request.quick_normal;

    const response = await this.fetchWithAuth(`${baseUrl}/analyze/explain`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      await this.handleErrorResponse(response);
    }

    return response.json();
  }

  async *explainReportStream(
    request: ExplainRequest,
  ): AsyncGenerator<{
    stage: string;
    message?: string;
    data?: ExplainResponse;
  }> {
    const baseUrl = await this.ensureInitialized();

    const body: Record<string, unknown> = {
      extraction_result: request.extraction_result,
    };
    if (request.test_type != null) body.test_type = request.test_type;
    if (request.literacy_level != null)
      body.literacy_level = request.literacy_level;
    if (request.provider != null) body.provider = request.provider;
    if (request.api_key != null) body.api_key = request.api_key;
    if (request.clinical_context != null)
      body.clinical_context = request.clinical_context;
    if (request.template_id != null) body.template_id = request.template_id;
    if (request.shared_template_sync_id != null)
      body.shared_template_sync_id = request.shared_template_sync_id;
    if (request.refinement_instruction != null)
      body.refinement_instruction = request.refinement_instruction;
    if (request.tone_preference != null)
      body.tone_preference = request.tone_preference;
    if (request.detail_preference != null)
      body.detail_preference = request.detail_preference;
    if (request.next_steps != null) body.next_steps = request.next_steps;
    if (request.short_comment != null)
      body.short_comment = request.short_comment;
    if (request.sms_summary != null)
      body.sms_summary = request.sms_summary;
    if (request.explanation_voice != null)
      body.explanation_voice = request.explanation_voice;
    if (request.name_drop != null)
      body.name_drop = request.name_drop;
    if (request.physician_name_override != null)
      body.physician_name_override = request.physician_name_override;
    if (request.include_key_findings != null)
      body.include_key_findings = request.include_key_findings;
    if (request.include_measurements != null)
      body.include_measurements = request.include_measurements;
    if (request.deep_analysis != null)
      body.deep_analysis = request.deep_analysis;
    if (request.high_anxiety_mode != null)
      body.high_anxiety_mode = request.high_anxiety_mode;
    if (request.quick_reasons != null)
      body.quick_reasons = request.quick_reasons;
    if (request.use_analogies != null)
      body.use_analogies = request.use_analogies;
    if (request.avoid_openings != null)
      body.avoid_openings = request.avoid_openings;
    if (request.batch_prior_summaries != null)
      body.batch_prior_summaries = request.batch_prior_summaries;

    const response = await this.fetchWithAuth(`${baseUrl}/analyze/explain-stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      await this.handleErrorResponse(response);
    }

    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Parse SSE events from buffer
      while (true) {
        const eventEnd = buffer.indexOf("\n\n");
        if (eventEnd === -1) break;
        const eventStr = buffer.slice(0, eventEnd);
        buffer = buffer.slice(eventEnd + 2);

        for (const line of eventStr.split("\n")) {
          if (line.startsWith("data: ")) {
            yield JSON.parse(line.slice(6));
          }
        }
      }
    }
  }

  async getGlossary(testType: string): Promise<GlossaryResponse> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/glossary/${testType}`, {
      cache: "no-store",
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async exportPdf(explainResponse: ExplainResponse): Promise<Blob> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/export/pdf`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(explainResponse),
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.blob();
  }

  async getSettings(): Promise<AppSettings> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/settings`, { cache: "no-store" });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async updateSettings(update: SettingsUpdate): Promise<AppSettings> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/settings`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(update),
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  // --- Templates ---

  async listTemplates(): Promise<TemplateListResponse> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/templates`, { cache: "no-store" });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async createTemplate(request: TemplateCreateRequest): Promise<Template> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/templates`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async updateTemplate(
    id: number,
    request: TemplateUpdateRequest,
  ): Promise<Template> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/templates/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async deleteTemplate(id: number): Promise<{ deleted: boolean; id: number }> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/templates/${id}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async listTestTypes(): Promise<{ id: string; name: string; category?: string }[]> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/test-types`);
    if (!response.ok) return [];
    return response.json();
  }

  async listHistoryTestTypes(): Promise<
    { test_type: string; test_type_display: string }[]
  > {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/history/test-types`, {
      cache: "no-store",
    });
    if (!response.ok) return [];
    return response.json();
  }

  async getDefaultTemplate(testType: string): Promise<Template | null> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(
      `${baseUrl}/templates/default/${encodeURIComponent(testType)}`,
    );
    if (!response.ok) return null;
    const data = await response.json();
    return data.template ?? null;
  }

  // --- History ---

  async listHistory(
    offset = 0,
    limit = 20,
    search?: string,
    likedOnly?: boolean,
  ): Promise<HistoryListResponse> {
    const baseUrl = await this.ensureInitialized();
    const params = new URLSearchParams({
      offset: String(offset),
      limit: String(limit),
    });
    if (search) {
      params.set("search", search);
    }
    if (likedOnly) {
      params.set("liked_only", "true");
    }
    const response = await this.fetchWithAuth(`${baseUrl}/history?${params}`, {
      cache: "no-store",
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async getHistoryDetail(id: number): Promise<HistoryDetailResponse> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/history/${id}`, {
      cache: "no-store",
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async saveHistory(
    request: HistoryCreateRequest,
  ): Promise<HistoryDetailResponse> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/history`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async deleteHistory(id: number): Promise<HistoryDeleteResponse> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/history/${id}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async toggleHistoryLiked(
    id: number,
    liked: boolean,
  ): Promise<HistoryLikeResponse> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/history/${id}/like`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ liked }),
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async markHistoryCopied(id: number): Promise<void> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/history/${id}/copied`, {
      method: "PUT",
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
  }

  async saveEditedText(id: number, editedText: string): Promise<void> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/history/${id}/edited_text`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ edited_text: editedText }),
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
  }

  async rateHistory(id: number, rating: number, note?: string): Promise<void> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/history/${id}/rate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rating, note: note || null }),
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
  }

  async computePatientFingerprints(texts: string[]): Promise<string[]> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/analyze/patient-fingerprints`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ texts }),
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    const data = await response.json();
    return data.fingerprints;
  }

  // --- Consent ---

  async getConsent(): Promise<ConsentStatusResponse> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/consent`, { cache: "no-store" });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async grantConsent(): Promise<ConsentStatusResponse> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/consent`, {
      method: "POST",
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async getRawApiKey(
    provider: string,
  ): Promise<{ provider: string; key?: string; credentials?: { access_key: string; secret_key: string; region: string } }> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/settings/raw-key/${provider}`, {
      cache: "no-store",
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async getOnboarding(): Promise<{ onboarding_completed: boolean }> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/onboarding`, {
      cache: "no-store",
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async completeOnboarding(): Promise<{ onboarding_completed: boolean }> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/onboarding`, {
      method: "POST",
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  // --- Letters ---

  async generateLetter(
    request: LetterGenerateRequest,
  ): Promise<LetterResponse> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/letters/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async listLetters(
    offset?: number,
    limit?: number,
    search?: string,
    likedOnly?: boolean,
  ): Promise<LetterListResponse> {
    const baseUrl = await this.ensureInitialized();
    const params = new URLSearchParams();
    if (offset !== undefined) params.set("offset", String(offset));
    if (limit !== undefined) params.set("limit", String(limit));
    if (search) params.set("search", search);
    if (likedOnly) params.set("liked_only", "true");
    const qs = params.toString();
    const response = await this.fetchWithAuth(
      `${baseUrl}/letters${qs ? `?${qs}` : ""}`,
      { cache: "no-store" },
    );
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async getLetter(id: number): Promise<LetterResponse> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/letters/${id}`, {
      cache: "no-store",
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async updateLetter(id: number, content: string): Promise<LetterResponse> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/letters/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async toggleLetterLiked(
    id: number,
    liked: boolean,
  ): Promise<{ id: number; liked: boolean }> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/letters/${id}/like`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ liked }),
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async deleteLetter(id: number): Promise<LetterDeleteResponse> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/letters/${id}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  // --- Teaching Points ---

  async listTeachingPoints(testType?: string): Promise<TeachingPoint[]> {
    const baseUrl = await this.ensureInitialized();
    const params = new URLSearchParams();
    if (testType) {
      params.set("test_type", testType);
    }
    const qs = params.toString();
    const response = await this.fetchWithAuth(
      `${baseUrl}/teaching-points${qs ? `?${qs}` : ""}`,
      { cache: "no-store" },
    );
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async createTeachingPoint(request: {
    text: string;
    test_type?: string;
  }): Promise<TeachingPoint> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/teaching-points`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async updateTeachingPoint(id: number, request: {
    text?: string;
    test_type?: string | null;
  }): Promise<TeachingPoint> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/teaching-points/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async deleteTeachingPoint(id: number): Promise<void> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/teaching-points/${id}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
  }

  // --- Shared Content ---

  async listSharedTeachingPoints(
    testType?: string,
  ): Promise<SharedTeachingPoint[]> {
    const baseUrl = await this.ensureInitialized();
    const params = new URLSearchParams();
    if (testType) {
      params.set("test_type", testType);
    }
    const qs = params.toString();
    const response = await this.fetchWithAuth(
      `${baseUrl}/teaching-points/shared${qs ? `?${qs}` : ""}`,
      { cache: "no-store" },
    );
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async syncSharedTeachingPoints(
    rows: Record<string, unknown>[],
  ): Promise<{ replaced: number }> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/teaching-points/shared/sync`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rows }),
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async listSharedTemplates(): Promise<SharedTemplate[]> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/templates/shared`, {
      cache: "no-store",
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async syncSharedTemplates(
    rows: Record<string, unknown>[],
  ): Promise<{ replaced: number }> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/templates/shared/sync`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rows }),
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  // --- Sync ---

  async syncExportAll(table: string): Promise<Record<string, unknown>[]> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/sync/export/${table}`, {
      cache: "no-store",
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async syncExportRecord(
    table: string,
    recordId: number,
  ): Promise<Record<string, unknown>> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(
      `${baseUrl}/sync/export/${table}/${recordId}`,
      { cache: "no-store" },
    );
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async syncMerge(
    table: string,
    rows: Record<string, unknown>[],
  ): Promise<{ merged: number; skipped: number }> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/sync/merge`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ table, rows }),
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  // --- Comparison ---

  async compareReports(
    newerResponse: ExplainResponse,
    olderResponse: ExplainResponse,
    newerDate: string,
    olderDate: string,
  ): Promise<{
    trend_summary: string;
    model_used: string;
    input_tokens: number;
    output_tokens: number;
  }> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/analyze/compare`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        newer_response: newerResponse,
        older_response: olderResponse,
        newer_date: newerDate,
        older_date: olderDate,
      }),
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }
  // --- Synthesis ---

  async synthesizeReports(
    responses: ExplainResponse[],
    labels: string[],
    clinicalContext?: string,
  ): Promise<{
    combined_summary: string;
    model_used: string;
    input_tokens: number;
    output_tokens: number;
  }> {
    const baseUrl = await this.ensureInitialized();
    const response = await this.fetchWithAuth(`${baseUrl}/analyze/synthesize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        responses,
        labels,
        clinical_context: clinicalContext ?? "",
      }),
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }
}

export const sidecarApi = new SidecarApi();
