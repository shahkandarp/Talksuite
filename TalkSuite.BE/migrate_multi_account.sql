-- =============================================================================
-- Multi-account migration — run AFTER the 4 CREATE/ALTER statements.
-- =============================================================================

-- 1. Schema changes (if you didn't run them via the earlier block)
CREATE TABLE IF NOT EXISTS netsuite_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR NOT NULL,
    account_id VARCHAR NOT NULL,
    client_id VARCHAR NOT NULL,
    client_secret TEXT,
    mcp_url VARCHAR,
    redirect_uri VARCHAR,
    scope VARCHAR DEFAULT 'mcp',
    refresh_token TEXT,
    access_token TEXT,
    token_expiry TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_account_map (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES netsuite_accounts(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (user_id, account_id)
);

CREATE TABLE IF NOT EXISTS pkce_sessions (
    state VARCHAR PRIMARY KEY,
    code_verifier VARCHAR NOT NULL,
    account_id UUID REFERENCES netsuite_accounts(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE conversations
ADD COLUMN IF NOT EXISTS account_id UUID REFERENCES netsuite_accounts(id) ON DELETE CASCADE;

-- 2. OPTIONAL: seed your existing account so the current setup keeps working.
--    NOTE: refresh_token/client_secret are stored ENCRYPTED by the app. You cannot
--    paste a plaintext token here and have it work. Instead, create the account row
--    WITHOUT tokens, then use the Admin Portal "Connect" button to run the PKCE flow
--    which will populate the encrypted refresh_token automatically.
--
-- INSERT INTO netsuite_accounts (id, name, account_id, client_id, mcp_url, scope)
-- VALUES (
--   gen_random_uuid(),
--   'Opus Sandbox',
--   '661135_SB2',
--   '5e115e8402e094cff6b6fcd9f4f83d0f1f0ddae40ec7527f2f2f6324e03359f5',
--   'https://***REMOVED***.suitetalk.api.netsuite.com/services/mcp/v1/all',
--   'mcp'
-- );

-- 3. After creating the account + connecting it, assign it to your admin user:
-- INSERT INTO user_account_map (id, user_id, account_id)
-- SELECT gen_random_uuid(), u.id, a.id
-- FROM users u, netsuite_accounts a
-- WHERE u.email = 'test@talksuite.dev' AND a.account_id = '661135_SB2';
