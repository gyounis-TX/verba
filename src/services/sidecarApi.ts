import { invoke } from "@tauri-apps/api/core";
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
  ConsentStatusResponse,
} from "../types/sidecar";

class SidecarApi {
  private baseUrl: string | null = null;

  async initialize(): Promise<void> {
    const port = await invoke<number>("get_sidecar_port");
    this.baseUrl = `http://127.0.0.1:${port}`;
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

  private ensureInitialized(): string {
    if (!this.baseUrl) {
      throw new Error("SidecarApi not initialized");
    }
    return this.baseUrl;
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

  async healthCheck(): Promise<HealthResponse> {
    const baseUrl = this.ensureInitialized();
    const response = await fetch(`${baseUrl}/health`);
    if (!response.ok) {
      throw new Error(`Health check failed: ${response.status}`);
    }
    return response.json();
  }

  async extractPdf(file: File): Promise<ExtractionResult> {
    const baseUrl = this.ensureInitialized();
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(`${baseUrl}/extract/pdf`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      await this.handleErrorResponse(response);
    }

    return response.json();
  }

  async extractText(text: string): Promise<ExtractionResult> {
    const baseUrl = this.ensureInitialized();

    const response = await fetch(`${baseUrl}/extract/text`, {
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
    const baseUrl = this.ensureInitialized();
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(`${baseUrl}/detect`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      await this.handleErrorResponse(response);
    }

    return response.json();
  }

  async detectTestType(
    extractionResult: ExtractionResult,
  ): Promise<DetectTypeResponse> {
    const baseUrl = this.ensureInitialized();

    const response = await fetch(`${baseUrl}/analyze/detect-type`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(extractionResult),
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
    const baseUrl = this.ensureInitialized();

    const response = await fetch(`${baseUrl}/analyze/parse`, {
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
    const baseUrl = this.ensureInitialized();

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

    const response = await fetch(`${baseUrl}/analyze/explain`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      await this.handleErrorResponse(response);
    }

    return response.json();
  }

  async getGlossary(testType: string): Promise<GlossaryResponse> {
    const baseUrl = this.ensureInitialized();
    const response = await fetch(`${baseUrl}/glossary/${testType}`);
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async exportPdf(explainResponse: ExplainResponse): Promise<Blob> {
    const baseUrl = this.ensureInitialized();
    const response = await fetch(`${baseUrl}/export/pdf`, {
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
    const baseUrl = this.ensureInitialized();
    const response = await fetch(`${baseUrl}/settings`);
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async updateSettings(update: SettingsUpdate): Promise<AppSettings> {
    const baseUrl = this.ensureInitialized();
    const response = await fetch(`${baseUrl}/settings`, {
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
    const baseUrl = this.ensureInitialized();
    const response = await fetch(`${baseUrl}/templates`);
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async createTemplate(request: TemplateCreateRequest): Promise<Template> {
    const baseUrl = this.ensureInitialized();
    const response = await fetch(`${baseUrl}/templates`, {
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
    const baseUrl = this.ensureInitialized();
    const response = await fetch(`${baseUrl}/templates/${id}`, {
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
    const baseUrl = this.ensureInitialized();
    const response = await fetch(`${baseUrl}/templates/${id}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  // --- History ---

  async listHistory(
    offset = 0,
    limit = 20,
    search?: string,
  ): Promise<HistoryListResponse> {
    const baseUrl = this.ensureInitialized();
    const params = new URLSearchParams({
      offset: String(offset),
      limit: String(limit),
    });
    if (search) {
      params.set("search", search);
    }
    const response = await fetch(`${baseUrl}/history?${params}`);
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async getHistoryDetail(id: number): Promise<HistoryDetailResponse> {
    const baseUrl = this.ensureInitialized();
    const response = await fetch(`${baseUrl}/history/${id}`);
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async saveHistory(
    request: HistoryCreateRequest,
  ): Promise<HistoryDetailResponse> {
    const baseUrl = this.ensureInitialized();
    const response = await fetch(`${baseUrl}/history`, {
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
    const baseUrl = this.ensureInitialized();
    const response = await fetch(`${baseUrl}/history/${id}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  // --- Consent ---

  async getConsent(): Promise<ConsentStatusResponse> {
    const baseUrl = this.ensureInitialized();
    const response = await fetch(`${baseUrl}/consent`);
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  async grantConsent(): Promise<ConsentStatusResponse> {
    const baseUrl = this.ensureInitialized();
    const response = await fetch(`${baseUrl}/consent`, {
      method: "POST",
    });
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }
}

export const sidecarApi = new SidecarApi();
