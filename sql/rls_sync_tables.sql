-- RLS policies for sync tables: settings, history, templates, letters, teaching_points
-- Run this in the Supabase SQL Editor.
-- Ensures each user can only access their own rows.

-- =============================================================================
-- settings
-- =============================================================================
ALTER TABLE settings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own settings" ON settings
  FOR ALL USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- =============================================================================
-- history
-- =============================================================================
ALTER TABLE history ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own history" ON history
  FOR ALL USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- =============================================================================
-- templates
-- =============================================================================
ALTER TABLE templates ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own templates" ON templates
  FOR ALL USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- =============================================================================
-- letters
-- =============================================================================
ALTER TABLE letters ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own letters" ON letters
  FOR ALL USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- =============================================================================
-- teaching_points
-- =============================================================================
-- RLS may already be enabled; this is idempotent.
ALTER TABLE teaching_points ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own teaching points" ON teaching_points
  FOR ALL USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- NOTE: The sharing_migration.sql already added SELECT policies for
-- recipients on teaching_points and templates. Those remain in effect
-- alongside the owner policies above.
