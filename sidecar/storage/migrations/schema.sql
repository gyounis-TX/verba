-- =============================================================================
-- RDS Migration: Complete schema for AWS RDS PostgreSQL
-- Replaces Supabase-managed database. No RLS, no auth.users — the sidecar
-- handles all access control via JWT verification.
-- =============================================================================

-- =============================================================================
-- 1. Users table (replaces Supabase auth.users)
-- Cognito is the auth source of truth; this table stores user metadata.
-- =============================================================================

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY,                          -- matches Cognito sub
    email TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_sign_in_at TIMESTAMPTZ,
    raw_user_meta_data JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(LOWER(email));

-- =============================================================================
-- 2. Settings
-- =============================================================================

CREATE TABLE IF NOT EXISTS settings (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, key)
);

-- =============================================================================
-- 3. History
-- =============================================================================

CREATE TABLE IF NOT EXISTS history (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sync_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    test_type TEXT NOT NULL,
    test_type_display TEXT NOT NULL,
    filename TEXT,
    summary TEXT NOT NULL,
    full_response TEXT NOT NULL,
    liked BOOLEAN NOT NULL DEFAULT FALSE,
    copied BOOLEAN NOT NULL DEFAULT FALSE,
    edited_text TEXT,
    quality_rating INTEGER,
    quality_note TEXT,
    tone_preference INTEGER,
    detail_preference INTEGER,
    tone_used INTEGER,
    detail_used INTEGER,
    literacy_used TEXT,
    was_edited BOOLEAN NOT NULL DEFAULT FALSE,
    severity_score REAL
);

CREATE INDEX IF NOT EXISTS idx_history_user_id ON history(user_id);
CREATE INDEX IF NOT EXISTS idx_history_created_at ON history(created_at);
CREATE INDEX IF NOT EXISTS idx_history_sync_id ON history(user_id, sync_id);
CREATE INDEX IF NOT EXISTS idx_history_liked ON history(user_id, liked);

-- =============================================================================
-- 4. Templates
-- =============================================================================

CREATE TABLE IF NOT EXISTS templates (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sync_id TEXT,
    name TEXT NOT NULL,
    test_type TEXT,
    tone TEXT,
    structure_instructions TEXT,
    closing_text TEXT,
    is_builtin BOOLEAN DEFAULT FALSE,
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_templates_user_id ON templates(user_id);
CREATE INDEX IF NOT EXISTS idx_templates_sync_id ON templates(user_id, sync_id);

-- =============================================================================
-- 5. Letters
-- =============================================================================

CREATE TABLE IF NOT EXISTS letters (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sync_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    prompt TEXT NOT NULL,
    content TEXT NOT NULL,
    letter_type TEXT DEFAULT 'general',
    liked BOOLEAN DEFAULT FALSE,
    model_used TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER
);

CREATE INDEX IF NOT EXISTS idx_letters_user_id ON letters(user_id);
CREATE INDEX IF NOT EXISTS idx_letters_created_at ON letters(created_at);
CREATE INDEX IF NOT EXISTS idx_letters_sync_id ON letters(user_id, sync_id);

-- =============================================================================
-- 6. Teaching Points
-- =============================================================================

CREATE TABLE IF NOT EXISTS teaching_points (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sync_id TEXT,
    text TEXT NOT NULL,
    test_type TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_teaching_points_user_id ON teaching_points(user_id);
CREATE INDEX IF NOT EXISTS idx_teaching_points_test_type ON teaching_points(user_id, test_type);
CREATE INDEX IF NOT EXISTS idx_teaching_points_sync_id ON teaching_points(user_id, sync_id);

-- =============================================================================
-- 7. User Shares
-- =============================================================================

CREATE TABLE IF NOT EXISTS user_shares (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sharer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recipient_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(sharer_id, recipient_id),
    CHECK (sharer_id != recipient_id)
);

CREATE INDEX IF NOT EXISTS idx_user_shares_sharer ON user_shares(sharer_id);
CREATE INDEX IF NOT EXISTS idx_user_shares_recipient ON user_shares(recipient_id);

-- =============================================================================
-- 8. Usage Log
-- =============================================================================

CREATE TABLE IF NOT EXISTS usage_log (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    model_used TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    request_type TEXT NOT NULL DEFAULT 'explain',
    deep_analysis BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_usage_log_user_id ON usage_log(user_id);
CREATE INDEX IF NOT EXISTS idx_usage_log_created_at ON usage_log(created_at);

-- =============================================================================
-- 9. Personalization: Term Preferences
-- =============================================================================

CREATE TABLE IF NOT EXISTS term_preferences (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    medical_term TEXT NOT NULL,
    test_type TEXT,
    preferred_phrasing TEXT NOT NULL,
    keep_technical BOOLEAN DEFAULT FALSE,
    source TEXT DEFAULT 'edit',
    count INTEGER DEFAULT 1,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, medical_term, test_type)
);

-- =============================================================================
-- 10. Personalization: Conditional Rules
-- =============================================================================

CREATE TABLE IF NOT EXISTS conditional_rules (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    test_type TEXT NOT NULL,
    severity_band TEXT NOT NULL,
    phrase TEXT NOT NULL,
    pattern_type TEXT DEFAULT 'general',
    count INTEGER DEFAULT 1,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, test_type, severity_band, phrase)
);

-- =============================================================================
-- 11. Personalization: Style Profiles
-- =============================================================================

CREATE TABLE IF NOT EXISTS style_profiles (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    test_type TEXT NOT NULL,
    profile TEXT NOT NULL,
    sample_count INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_data_at TIMESTAMPTZ,
    PRIMARY KEY (test_type, user_id)
);

-- =============================================================================
-- 12. Billing: Customers
-- =============================================================================

CREATE TABLE IF NOT EXISTS customers (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    stripe_customer_id TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- 13. Billing: Products
-- =============================================================================

CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    active BOOLEAN DEFAULT TRUE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- 14. Billing: Prices
-- =============================================================================

CREATE TABLE IF NOT EXISTS prices (
    id TEXT PRIMARY KEY,
    product_id TEXT REFERENCES products(id) ON DELETE CASCADE,
    unit_amount INTEGER NOT NULL,
    currency TEXT DEFAULT 'usd',
    interval TEXT DEFAULT 'month',
    interval_count INTEGER DEFAULT 1,
    trial_period_days INTEGER,
    active BOOLEAN DEFAULT TRUE,
    tier TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- 15. Billing: Subscriptions
-- =============================================================================

CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    price_id TEXT REFERENCES prices(id),
    status TEXT NOT NULL,
    tier TEXT,
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    trial_start TIMESTAMPTZ,
    trial_end TIMESTAMPTZ,
    cancel_at TIMESTAMPTZ,
    cancel_at_period_end BOOLEAN DEFAULT FALSE,
    canceled_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    paused_at TIMESTAMPTZ,
    discount_code TEXT,
    discount_percent REAL,
    discount_amount_off INTEGER,
    discount_name TEXT,
    discount_duration TEXT,
    discount_months_remaining INTEGER,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);

-- =============================================================================
-- 16. Billing: Usage Periods
-- =============================================================================

CREATE TABLE IF NOT EXISTS usage_periods (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    report_count INTEGER DEFAULT 0,
    deep_analysis_count INTEGER DEFAULT 0,
    batch_count INTEGER DEFAULT 0,
    letter_count INTEGER DEFAULT 0,
    comparison_count INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, period_start)
);

-- =============================================================================
-- 17. Billing: Config
-- =============================================================================

CREATE TABLE IF NOT EXISTS billing_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO billing_config (key, value) VALUES
    ('payments_enabled', 'false'),
    ('trial_period_days', '14'),
    ('trial_tier', 'professional'),
    ('grace_period_hours', '72'),
    ('require_payment_method_for_trial', 'false'),
    ('retention_coupon_id', ''),
    ('retention_offer_text', 'Stay for 50% off for 3 months')
ON CONFLICT (key) DO NOTHING;

-- =============================================================================
-- 18. Billing: Tier Limits
-- =============================================================================

CREATE TABLE IF NOT EXISTS tier_limits (
    tier TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    monthly_reports INTEGER,
    monthly_deep_analysis INTEGER,
    monthly_letters INTEGER,
    max_batch_size INTEGER DEFAULT 1,
    has_comparison BOOLEAN DEFAULT FALSE,
    has_synthesis BOOLEAN DEFAULT FALSE,
    has_custom_templates BOOLEAN DEFAULT FALSE,
    has_teaching_points_create BOOLEAN DEFAULT FALSE,
    has_full_personalization BOOLEAN DEFAULT FALSE,
    history_days INTEGER,
    price_monthly_cents INTEGER,
    price_annual_cents INTEGER,
    sort_order INTEGER DEFAULT 0
);

INSERT INTO tier_limits VALUES
    ('starter', 'Starter', 75, 0, 0, 1, FALSE, FALSE, FALSE, FALSE, FALSE, 30, 2900, 29000, 1),
    ('professional', 'Professional', 300, 10, NULL, 3, TRUE, TRUE, TRUE, TRUE, TRUE, NULL, 4900, 49000, 2),
    ('unlimited', 'Unlimited', NULL, NULL, NULL, 10, TRUE, TRUE, TRUE, TRUE, TRUE, NULL, 9900, 99000, 3)
ON CONFLICT (tier) DO NOTHING;

-- Stripe Products
INSERT INTO products (id, name, description, active) VALUES
    ('prod_Tz5ZGL3AUuss98', 'Explify - Starter', 'Starter tier for Explify', TRUE),
    ('prod_Tz5a0ffvqql5Kl', 'Explify - Professional', 'Professional tier for Explify', TRUE),
    ('prod_Tz5aamtXHH1Crc', 'Explify - Unlimited', 'Unlimited tier for Explify', TRUE)
ON CONFLICT (id) DO NOTHING;

-- Stripe Prices
INSERT INTO prices (id, product_id, unit_amount, currency, interval, interval_count, tier, active) VALUES
    ('price_1T17lIHSjjrILQoYBzwcGV2C', 'prod_Tz5ZGL3AUuss98', 2900, 'usd', 'month', 1, 'starter', TRUE),
    ('price_1T17O6HSjjrILQoYNciwe0Iv', 'prod_Tz5ZGL3AUuss98', 29000, 'usd', 'year', 1, 'starter', TRUE),
    ('price_1T17PKHSjjrILQoY3x9oAmKz', 'prod_Tz5a0ffvqql5Kl', 4900, 'usd', 'month', 1, 'professional', TRUE),
    ('price_1T17joHSjjrILQoYNCLkkCMC', 'prod_Tz5a0ffvqql5Kl', 49000, 'usd', 'year', 1, 'professional', TRUE),
    ('price_1T17PlHSjjrILQoYUmFKq6a7', 'prod_Tz5aamtXHH1Crc', 9900, 'usd', 'month', 1, 'unlimited', TRUE),
    ('price_1T17bjHSjjrILQoYAMSSIPiK', 'prod_Tz5aamtXHH1Crc', 99000, 'usd', 'year', 1, 'unlimited', TRUE)
ON CONFLICT (id) DO NOTHING;

-- =============================================================================
-- 19. Billing: User Overrides
-- =============================================================================

CREATE TABLE IF NOT EXISTS user_billing_overrides (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    payments_exempt BOOLEAN DEFAULT FALSE,
    custom_trial_days INTEGER,
    custom_tier TEXT,
    notes TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by TEXT
);

-- =============================================================================
-- 20. Billing: Cancellation Analytics
-- =============================================================================

CREATE TABLE IF NOT EXISTS subscription_cancellations (
    id SERIAL PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    subscription_id TEXT,
    reason TEXT,
    reason_detail TEXT,
    retention_offered BOOLEAN DEFAULT FALSE,
    retention_accepted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- 21. Billing: Discount Codes
-- =============================================================================

CREATE TABLE IF NOT EXISTS admin_discount_codes (
    id SERIAL PRIMARY KEY,
    stripe_coupon_id TEXT NOT NULL,
    stripe_promo_code_id TEXT,
    code TEXT NOT NULL,
    description TEXT,
    discount_type TEXT NOT NULL,
    discount_value REAL NOT NULL,
    duration TEXT NOT NULL,
    duration_months INTEGER,
    max_redemptions INTEGER,
    expires_at TIMESTAMPTZ,
    first_time_only BOOLEAN DEFAULT FALSE,
    active BOOLEAN DEFAULT TRUE,
    times_redeemed INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by TEXT
);

-- =============================================================================
-- 22. Billing: Stripe Event Deduplication
-- =============================================================================

CREATE TABLE IF NOT EXISTS stripe_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    processed_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- RPC Functions (no auth.uid() — user_id passed explicitly by sidecar)
-- =============================================================================

-- Get active subscription for a user
CREATE OR REPLACE FUNCTION get_subscription(p_user_id UUID)
RETURNS TABLE (
    id TEXT,
    status TEXT,
    tier TEXT,
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    trial_start TIMESTAMPTZ,
    trial_end TIMESTAMPTZ,
    cancel_at_period_end BOOLEAN,
    discount_name TEXT,
    discount_percent REAL,
    discount_months_remaining INTEGER
) LANGUAGE sql STABLE AS $$
    SELECT
        s.id, s.status, s.tier,
        s.current_period_start, s.current_period_end,
        s.trial_start, s.trial_end,
        s.cancel_at_period_end,
        s.discount_name, s.discount_percent, s.discount_months_remaining
    FROM subscriptions s
    WHERE s.user_id = p_user_id
      AND s.status IN ('active', 'trialing', 'past_due', 'paused')
    ORDER BY s.created_at DESC
    LIMIT 1;
$$;

-- Get or create usage period
CREATE OR REPLACE FUNCTION get_usage_period(
    p_user_id UUID,
    p_period_start TIMESTAMPTZ,
    p_period_end TIMESTAMPTZ
)
RETURNS TABLE (
    report_count INTEGER,
    deep_analysis_count INTEGER,
    batch_count INTEGER,
    letter_count INTEGER,
    comparison_count INTEGER
) LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO usage_periods (user_id, period_start, period_end)
    VALUES (p_user_id, p_period_start, p_period_end)
    ON CONFLICT (user_id, period_start) DO NOTHING;

    RETURN QUERY
    SELECT up.report_count, up.deep_analysis_count, up.batch_count,
           up.letter_count, up.comparison_count
    FROM usage_periods up
    WHERE up.user_id = p_user_id AND up.period_start = p_period_start;
END;
$$;

-- Atomically increment a usage counter
CREATE OR REPLACE FUNCTION increment_usage(p_user_id UUID, p_feature TEXT)
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    CASE p_feature
        WHEN 'report_count' THEN
            UPDATE usage_periods SET report_count = report_count + 1, updated_at = NOW()
            WHERE user_id = p_user_id
              AND period_start = (SELECT period_start FROM usage_periods WHERE user_id = p_user_id ORDER BY period_start DESC LIMIT 1);
        WHEN 'deep_analysis_count' THEN
            UPDATE usage_periods SET deep_analysis_count = deep_analysis_count + 1, updated_at = NOW()
            WHERE user_id = p_user_id
              AND period_start = (SELECT period_start FROM usage_periods WHERE user_id = p_user_id ORDER BY period_start DESC LIMIT 1);
        WHEN 'batch_count' THEN
            UPDATE usage_periods SET batch_count = batch_count + 1, updated_at = NOW()
            WHERE user_id = p_user_id
              AND period_start = (SELECT period_start FROM usage_periods WHERE user_id = p_user_id ORDER BY period_start DESC LIMIT 1);
        WHEN 'letter_count' THEN
            UPDATE usage_periods SET letter_count = letter_count + 1, updated_at = NOW()
            WHERE user_id = p_user_id
              AND period_start = (SELECT period_start FROM usage_periods WHERE user_id = p_user_id ORDER BY period_start DESC LIMIT 1);
        WHEN 'comparison_count' THEN
            UPDATE usage_periods SET comparison_count = comparison_count + 1, updated_at = NOW()
            WHERE user_id = p_user_id
              AND period_start = (SELECT period_start FROM usage_periods WHERE user_id = p_user_id ORDER BY period_start DESC LIMIT 1);
        ELSE
            RAISE EXCEPTION 'Unknown feature: %', p_feature;
    END CASE;
END;
$$;

-- Get tier limits
CREATE OR REPLACE FUNCTION get_tier_limits(p_tier TEXT)
RETURNS TABLE (
    tier TEXT, display_name TEXT,
    monthly_reports INTEGER, monthly_deep_analysis INTEGER, monthly_letters INTEGER,
    max_batch_size INTEGER,
    has_comparison BOOLEAN, has_synthesis BOOLEAN, has_custom_templates BOOLEAN,
    has_teaching_points_create BOOLEAN, has_full_personalization BOOLEAN,
    history_days INTEGER, price_monthly_cents INTEGER, price_annual_cents INTEGER
) LANGUAGE sql STABLE AS $$
    SELECT tl.tier, tl.display_name,
           tl.monthly_reports, tl.monthly_deep_analysis, tl.monthly_letters,
           tl.max_batch_size,
           tl.has_comparison, tl.has_synthesis, tl.has_custom_templates,
           tl.has_teaching_points_create, tl.has_full_personalization,
           tl.history_days, tl.price_monthly_cents, tl.price_annual_cents
    FROM tier_limits tl WHERE tl.tier = p_tier;
$$;

-- Get all billing config
CREATE OR REPLACE FUNCTION get_billing_config()
RETURNS TABLE (key TEXT, value TEXT) LANGUAGE sql STABLE AS $$
    SELECT bc.key, bc.value FROM billing_config bc;
$$;

-- Check user billing overrides
CREATE OR REPLACE FUNCTION check_user_billing_override(p_user_id UUID)
RETURNS TABLE (
    payments_exempt BOOLEAN, custom_trial_days INTEGER,
    custom_tier TEXT, notes TEXT
) LANGUAGE sql STABLE AS $$
    SELECT ubo.payments_exempt, ubo.custom_trial_days, ubo.custom_tier, ubo.notes
    FROM user_billing_overrides ubo WHERE ubo.user_id = p_user_id;
$$;

-- Upsert customer mapping
CREATE OR REPLACE FUNCTION upsert_customer(p_user_id UUID, p_stripe_customer_id TEXT)
RETURNS VOID LANGUAGE sql AS $$
    INSERT INTO customers (user_id, stripe_customer_id)
    VALUES (p_user_id, p_stripe_customer_id)
    ON CONFLICT (user_id) DO UPDATE SET stripe_customer_id = EXCLUDED.stripe_customer_id;
$$;

-- Upsert subscription from webhook
CREATE OR REPLACE FUNCTION upsert_subscription(
    p_id TEXT, p_user_id UUID, p_price_id TEXT, p_status TEXT, p_tier TEXT,
    p_current_period_start TIMESTAMPTZ, p_current_period_end TIMESTAMPTZ,
    p_trial_start TIMESTAMPTZ DEFAULT NULL, p_trial_end TIMESTAMPTZ DEFAULT NULL,
    p_cancel_at_period_end BOOLEAN DEFAULT FALSE,
    p_canceled_at TIMESTAMPTZ DEFAULT NULL, p_ended_at TIMESTAMPTZ DEFAULT NULL
)
RETURNS VOID LANGUAGE sql AS $$
    INSERT INTO subscriptions (
        id, user_id, price_id, status, tier,
        current_period_start, current_period_end,
        trial_start, trial_end,
        cancel_at_period_end, canceled_at, ended_at, updated_at
    ) VALUES (
        p_id, p_user_id, p_price_id, p_status, p_tier,
        p_current_period_start, p_current_period_end,
        p_trial_start, p_trial_end,
        p_cancel_at_period_end, p_canceled_at, p_ended_at, NOW()
    )
    ON CONFLICT (id) DO UPDATE SET
        status = EXCLUDED.status, tier = EXCLUDED.tier, price_id = EXCLUDED.price_id,
        current_period_start = EXCLUDED.current_period_start,
        current_period_end = EXCLUDED.current_period_end,
        trial_start = EXCLUDED.trial_start, trial_end = EXCLUDED.trial_end,
        cancel_at_period_end = EXCLUDED.cancel_at_period_end,
        canceled_at = EXCLUDED.canceled_at, ended_at = EXCLUDED.ended_at,
        updated_at = NOW();
$$;

-- Record cancellation
CREATE OR REPLACE FUNCTION record_cancellation(
    p_user_id UUID, p_subscription_id TEXT, p_reason TEXT, p_detail TEXT
)
RETURNS VOID LANGUAGE sql AS $$
    INSERT INTO subscription_cancellations (user_id, subscription_id, reason, reason_detail)
    VALUES (p_user_id, p_subscription_id, p_reason, p_detail);
$$;

-- Look up user by email
CREATE OR REPLACE FUNCTION lookup_user_by_email(target_email TEXT)
RETURNS TABLE (user_id UUID, email TEXT)
LANGUAGE sql STABLE AS $$
    SELECT u.id, u.email FROM users u
    WHERE LOWER(u.email) = LOWER(target_email) LIMIT 1;
$$;

-- Admin: list all users with billing info
CREATE OR REPLACE FUNCTION admin_list_users()
RETURNS TABLE (
    user_id UUID, email TEXT, created_at TIMESTAMPTZ, last_sign_in_at TIMESTAMPTZ,
    subscription_status TEXT, subscription_tier TEXT,
    trial_end TIMESTAMPTZ, current_period_end TIMESTAMPTZ,
    discount_code TEXT, discount_name TEXT,
    payments_exempt BOOLEAN,
    period_report_count INTEGER, period_deep_count INTEGER
)
LANGUAGE sql STABLE AS $$
    SELECT
        u.id, u.email, u.created_at, u.last_sign_in_at,
        s.status, s.tier, s.trial_end, s.current_period_end,
        s.discount_code, s.discount_name,
        COALESCE(ubo.payments_exempt, FALSE),
        COALESCE(up.report_count, 0),
        COALESCE(up.deep_analysis_count, 0)
    FROM users u
    LEFT JOIN LATERAL (
        SELECT * FROM subscriptions sub
        WHERE sub.user_id = u.id ORDER BY sub.created_at DESC LIMIT 1
    ) s ON TRUE
    LEFT JOIN user_billing_overrides ubo ON ubo.user_id = u.id
    LEFT JOIN LATERAL (
        SELECT * FROM usage_periods up2
        WHERE up2.user_id = u.id ORDER BY up2.period_start DESC LIMIT 1
    ) up ON TRUE
    ORDER BY u.last_sign_in_at DESC NULLS LAST;
$$;

-- Admin: usage summary
CREATE OR REPLACE FUNCTION admin_usage_summary(since TIMESTAMPTZ)
RETURNS TABLE (
    user_id UUID, email TEXT,
    total_queries BIGINT, total_input_tokens BIGINT, total_output_tokens BIGINT,
    sonnet_queries BIGINT, sonnet_input_tokens BIGINT, sonnet_output_tokens BIGINT,
    opus_queries BIGINT, opus_input_tokens BIGINT, opus_output_tokens BIGINT,
    deep_analysis_count BIGINT, last_active TIMESTAMPTZ
)
LANGUAGE sql STABLE AS $$
    SELECT
        ul.user_id, u.email,
        COUNT(*)::BIGINT AS total_queries,
        COALESCE(SUM(ul.input_tokens), 0)::BIGINT AS total_input_tokens,
        COALESCE(SUM(ul.output_tokens), 0)::BIGINT AS total_output_tokens,
        COUNT(*) FILTER (WHERE ul.model_used ILIKE '%sonnet%')::BIGINT AS sonnet_queries,
        COALESCE(SUM(ul.input_tokens) FILTER (WHERE ul.model_used ILIKE '%sonnet%'), 0)::BIGINT AS sonnet_input_tokens,
        COALESCE(SUM(ul.output_tokens) FILTER (WHERE ul.model_used ILIKE '%sonnet%'), 0)::BIGINT AS sonnet_output_tokens,
        COUNT(*) FILTER (WHERE ul.model_used ILIKE '%opus%')::BIGINT AS opus_queries,
        COALESCE(SUM(ul.input_tokens) FILTER (WHERE ul.model_used ILIKE '%opus%'), 0)::BIGINT AS opus_input_tokens,
        COALESCE(SUM(ul.output_tokens) FILTER (WHERE ul.model_used ILIKE '%opus%'), 0)::BIGINT AS opus_output_tokens,
        COUNT(*) FILTER (WHERE ul.deep_analysis)::BIGINT AS deep_analysis_count,
        MAX(ul.created_at) AS last_active
    FROM usage_log ul
    JOIN users u ON u.id = ul.user_id
    WHERE ul.created_at >= since
    GROUP BY ul.user_id, u.email
    ORDER BY 3 DESC;
$$;

-- Sharing: get shared teaching points for a user
CREATE OR REPLACE FUNCTION get_shared_teaching_points(p_user_id UUID)
RETURNS TABLE (
    sync_id TEXT, text TEXT, test_type TEXT,
    created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ,
    sharer_user_id UUID, sharer_email TEXT
) LANGUAGE sql STABLE AS $$
    SELECT tp.sync_id, tp.text, tp.test_type, tp.created_at, tp.updated_at,
           tp.user_id, u.email
    FROM teaching_points tp
    JOIN user_shares us ON us.sharer_id = tp.user_id
    JOIN users u ON u.id = tp.user_id
    WHERE us.recipient_id = p_user_id;
$$;

-- Sharing: get shared templates for a user
CREATE OR REPLACE FUNCTION get_shared_templates(p_user_id UUID)
RETURNS TABLE (
    sync_id TEXT, name TEXT, test_type TEXT, tone TEXT,
    structure_instructions TEXT, closing_text TEXT,
    created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ,
    sharer_user_id UUID, sharer_email TEXT
) LANGUAGE sql STABLE AS $$
    SELECT t.sync_id, t.name, t.test_type, t.tone,
           t.structure_instructions, t.closing_text,
           t.created_at, t.updated_at,
           t.user_id, u.email
    FROM templates t
    JOIN user_shares us ON us.sharer_id = t.user_id
    JOIN users u ON u.id = t.user_id
    WHERE us.recipient_id = p_user_id;
$$;

-- Sharing: get my share recipients
CREATE OR REPLACE FUNCTION get_my_share_recipients(p_user_id UUID)
RETURNS TABLE (
    share_id BIGINT, recipient_user_id UUID,
    recipient_email TEXT, created_at TIMESTAMPTZ
) LANGUAGE sql STABLE AS $$
    SELECT us.id, us.recipient_id, u.email, us.created_at
    FROM user_shares us
    JOIN users u ON u.id = us.recipient_id
    WHERE us.sharer_id = p_user_id
    ORDER BY us.created_at DESC;
$$;

-- Sharing: get users sharing with me
CREATE OR REPLACE FUNCTION get_my_share_sources(p_user_id UUID)
RETURNS TABLE (
    share_id BIGINT, sharer_user_id UUID,
    sharer_email TEXT, created_at TIMESTAMPTZ
) LANGUAGE sql STABLE AS $$
    SELECT us.id, us.sharer_id, u.email, us.created_at
    FROM user_shares us
    JOIN users u ON u.id = us.sharer_id
    WHERE us.recipient_id = p_user_id
    ORDER BY us.created_at DESC;
$$;

-- =============================================================================
-- 23. Practices (organizations)
-- =============================================================================

CREATE TABLE IF NOT EXISTS practices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    specialty TEXT,
    join_code TEXT UNIQUE NOT NULL,
    sharing_enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_practices_join_code ON practices(join_code);

-- =============================================================================
-- 24. Practice Members
-- =============================================================================

CREATE TABLE IF NOT EXISTS practice_members (
    practice_id UUID NOT NULL REFERENCES practices(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'member',
    share_content BOOLEAN NOT NULL DEFAULT true,
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (practice_id, user_id),
    UNIQUE (user_id)
);

-- Backfill: add share_content column if table already exists without it
DO $$ BEGIN
    ALTER TABLE practice_members ADD COLUMN share_content BOOLEAN NOT NULL DEFAULT true;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_practice_members_user ON practice_members(user_id);

-- =============================================================================
-- Practice RPC Functions
-- =============================================================================

-- Get practice info for a user
CREATE OR REPLACE FUNCTION get_user_practice(p_user_id UUID)
RETURNS TABLE(
    practice_id UUID, practice_name TEXT, specialty TEXT,
    join_code TEXT, sharing_enabled BOOLEAN,
    role TEXT, member_count BIGINT
) LANGUAGE sql STABLE AS $$
    SELECT p.id, p.name, p.specialty, p.join_code, p.sharing_enabled,
           pm.role, (SELECT COUNT(*) FROM practice_members WHERE practice_id = p.id)
    FROM practice_members pm
    JOIN practices p ON p.id = pm.practice_id
    WHERE pm.user_id = p_user_id;
$$;

-- List practice members with usage stats
CREATE OR REPLACE FUNCTION list_practice_members(p_practice_id UUID)
RETURNS TABLE(
    user_id UUID, email TEXT, role TEXT, share_content BOOLEAN,
    joined_at TIMESTAMPTZ,
    report_count BIGINT, last_active TIMESTAMPTZ
) LANGUAGE sql STABLE AS $$
    SELECT pm.user_id, u.email, pm.role, pm.share_content, pm.joined_at,
           COALESCE(up.report_count, 0)::BIGINT,
           u.last_sign_in_at
    FROM practice_members pm
    JOIN users u ON u.id = pm.user_id
    LEFT JOIN LATERAL (
        SELECT * FROM usage_periods up2
        WHERE up2.user_id = pm.user_id ORDER BY up2.period_start DESC LIMIT 1
    ) up ON TRUE
    WHERE pm.practice_id = p_practice_id
    ORDER BY pm.role DESC, pm.joined_at;
$$;

-- Practice usage summary
CREATE OR REPLACE FUNCTION practice_usage_summary(p_practice_id UUID, p_since TIMESTAMPTZ)
RETURNS TABLE(
    total_members BIGINT, total_queries BIGINT,
    total_input_tokens BIGINT, total_output_tokens BIGINT,
    deep_analysis_count BIGINT
) LANGUAGE sql STABLE AS $$
    SELECT
        (SELECT COUNT(*) FROM practice_members WHERE practice_id = p_practice_id),
        COUNT(*),
        COALESCE(SUM(input_tokens), 0),
        COALESCE(SUM(output_tokens), 0),
        COALESCE(SUM(CASE WHEN deep_analysis THEN 1 ELSE 0 END), 0)
    FROM usage_log ul
    JOIN practice_members pm ON pm.user_id = ul.user_id
    WHERE pm.practice_id = p_practice_id
      AND ul.created_at >= p_since;
$$;

-- =============================================================================
-- Detection corrections — learn from user overrides of auto-detected test type
-- =============================================================================
CREATE TABLE IF NOT EXISTS detection_corrections (
    id SERIAL PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    detected_type TEXT NOT NULL,        -- what the system detected
    corrected_type TEXT NOT NULL,       -- what the user changed it to
    report_title TEXT,                  -- first ~200 chars of report for pattern matching
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_detection_corrections_types
    ON detection_corrections(detected_type, corrected_type);

-- =============================================================================
-- PHI Access Audit Log — HIPAA §164.312(b) compliance
-- =============================================================================
CREATE TABLE IF NOT EXISTS phi_access_log (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    ip_address TEXT,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_phi_access_log_user ON phi_access_log(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_phi_access_log_resource ON phi_access_log(resource_type, resource_id);

-- =============================================================================
-- BAA Acceptances — track Business Associate Agreement acceptance per user
-- =============================================================================
CREATE TABLE IF NOT EXISTS baa_acceptances (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    baa_version TEXT NOT NULL,
    accepted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ip_address TEXT,
    user_agent TEXT
);

CREATE INDEX IF NOT EXISTS idx_baa_acceptances_user ON baa_acceptances(user_id);
