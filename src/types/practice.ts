export interface Practice {
  id: string;
  name: string;
  specialty: string | null;
  join_code: string;
  sharing_enabled: boolean;
  created_at?: string;
}

export interface PracticeMember {
  user_id: string;
  email: string;
  role: "admin" | "member";
  joined_at: string;
  report_count: number;
  last_active: string | null;
}

export interface PracticeInfo {
  practice: Practice;
  role: "admin" | "member";
  member_count: number;
}

export interface PracticeUsageSummary {
  total_members: number;
  total_queries: number;
  total_input_tokens: number;
  total_output_tokens: number;
  deep_analysis_count: number;
}
