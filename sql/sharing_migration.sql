-- Sharing Migration: user_shares table, RLS policies, RPC functions
-- Run this in the Supabase SQL Editor

-- =============================================================================
-- Table: user_shares
-- One row = "sharer shares all their teaching points and templates with recipient"
-- =============================================================================

CREATE TABLE user_shares (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  sharer_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  recipient_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(sharer_id, recipient_id),
  CHECK (sharer_id != recipient_id)
);

CREATE INDEX idx_user_shares_sharer ON user_shares(sharer_id);
CREATE INDEX idx_user_shares_recipient ON user_shares(recipient_id);

-- =============================================================================
-- RLS Policies for user_shares
-- =============================================================================

ALTER TABLE user_shares ENABLE ROW LEVEL SECURITY;

-- Sharers can manage their outbound shares
CREATE POLICY "Sharers manage own shares" ON user_shares
  FOR ALL USING (auth.uid() = sharer_id)
  WITH CHECK (auth.uid() = sharer_id);

-- Recipients can view inbound shares
CREATE POLICY "Recipients view inbound shares" ON user_shares
  FOR SELECT USING (auth.uid() = recipient_id);

-- =============================================================================
-- RLS on existing teaching_points table — add SELECT policy for recipients
-- =============================================================================

CREATE POLICY "Recipients read shared teaching points" ON teaching_points
  FOR SELECT USING (
    user_id IN (
      SELECT sharer_id FROM user_shares WHERE recipient_id = auth.uid()
    )
  );

-- =============================================================================
-- RLS on existing templates table — add SELECT policy for recipients
-- =============================================================================

CREATE POLICY "Recipients read shared templates" ON templates
  FOR SELECT USING (
    user_id IN (
      SELECT sharer_id FROM user_shares WHERE recipient_id = auth.uid()
    )
  );

-- =============================================================================
-- RPC Functions
-- =============================================================================

-- Look up user by email (SECURITY DEFINER to access auth.users)
CREATE OR REPLACE FUNCTION lookup_user_by_email(target_email text)
RETURNS TABLE (user_id uuid, email text)
LANGUAGE sql SECURITY DEFINER AS $$
  SELECT id, email FROM auth.users
  WHERE LOWER(email) = LOWER(target_email) LIMIT 1;
$$;

-- Get all teaching points shared with the calling user
CREATE OR REPLACE FUNCTION get_shared_teaching_points()
RETURNS TABLE (
  sync_id text, text text, test_type text,
  created_at timestamptz, updated_at timestamptz,
  sharer_user_id uuid, sharer_email text
) LANGUAGE sql SECURITY DEFINER STABLE AS $$
  SELECT tp.sync_id, tp.text, tp.test_type, tp.created_at, tp.updated_at,
         tp.user_id, au.email
  FROM teaching_points tp
  JOIN user_shares us ON us.sharer_id = tp.user_id
  JOIN auth.users au ON au.id = tp.user_id
  WHERE us.recipient_id = auth.uid();
$$;

-- Get all templates shared with the calling user
CREATE OR REPLACE FUNCTION get_shared_templates()
RETURNS TABLE (
  sync_id text, name text, test_type text, tone text,
  structure_instructions text, closing_text text,
  created_at timestamptz, updated_at timestamptz,
  sharer_user_id uuid, sharer_email text
) LANGUAGE sql SECURITY DEFINER STABLE AS $$
  SELECT t.sync_id, t.name, t.test_type, t.tone,
         t.structure_instructions, t.closing_text,
         t.created_at, t.updated_at,
         t.user_id, au.email
  FROM templates t
  JOIN user_shares us ON us.sharer_id = t.user_id
  JOIN auth.users au ON au.id = t.user_id
  WHERE us.recipient_id = auth.uid();
$$;

-- Get users I'm sharing TO
CREATE OR REPLACE FUNCTION get_my_share_recipients()
RETURNS TABLE (
  share_id bigint, recipient_user_id uuid,
  recipient_email text, created_at timestamptz
) LANGUAGE sql SECURITY DEFINER STABLE AS $$
  SELECT us.id, us.recipient_id, au.email, us.created_at
  FROM user_shares us
  JOIN auth.users au ON au.id = us.recipient_id
  WHERE us.sharer_id = auth.uid()
  ORDER BY us.created_at DESC;
$$;

-- Get users sharing WITH me
CREATE OR REPLACE FUNCTION get_my_share_sources()
RETURNS TABLE (
  share_id bigint, sharer_user_id uuid,
  sharer_email text, created_at timestamptz
) LANGUAGE sql SECURITY DEFINER STABLE AS $$
  SELECT us.id, us.sharer_id, au.email, us.created_at
  FROM user_shares us
  JOIN auth.users au ON au.id = us.sharer_id
  WHERE us.recipient_id = auth.uid()
  ORDER BY us.created_at DESC;
$$;
