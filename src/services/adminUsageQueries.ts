import { sidecarApi } from "./sidecarApi";

export interface UserUsageSummary {
  user_id: string;
  email: string;
  total_queries: number;
  total_input_tokens: number;
  total_output_tokens: number;
  sonnet_queries: number;
  sonnet_input_tokens: number;
  sonnet_output_tokens: number;
  opus_queries: number;
  opus_input_tokens: number;
  opus_output_tokens: number;
  deep_analysis_count: number;
  last_active: string;
}

export interface RegisteredUser {
  user_id: string;
  email: string;
  created_at: string;
  app_version: string | null;
}

export async function fetchUsageSummary(
  since: Date,
): Promise<UserUsageSummary[]> {
  return sidecarApi.adminUsageSummary(since.toISOString()) as unknown as Promise<UserUsageSummary[]>;
}

export async function fetchAllUsers(): Promise<RegisteredUser[]> {
  return sidecarApi.adminListUsers() as unknown as Promise<RegisteredUser[]>;
}
