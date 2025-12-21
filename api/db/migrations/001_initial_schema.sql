-- KikuAI Unified Schema Initialization (Full B2B Edition)
-- Purpose: Complete Source of Truth for Accounts, Billing, Scoped Keys, and Ledger

-- 1. Accounts (Unified Billing Entity)
CREATE TABLE IF NOT EXISTS accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id BIGINT UNIQUE NOT NULL,
    email TEXT,
    balance_usd DECIMAL(18, 8) DEFAULT 0.00000000,
    
    -- B2B Features
    auto_recharge_threshold DECIMAL(18, 8),
    auto_recharge_amount DECIMAL(18, 8),
    opt_in_debug BOOLEAN DEFAULT FALSE,
    
    -- Auth (Email Magic Link / Refresh Tokens)
    email_auth_token TEXT UNIQUE,
    email_auth_expires TIMESTAMP WITH TIME ZONE,
    refresh_token_hash TEXT, -- For JWT refresh session
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_active_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Products Metadata
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY, -- 'masker', 'patas', 'reliapi', 'datafold', 'fynx', 'chart2csv'
    name TEXT NOT NULL,
    base_price_per_unit DECIMAL(18, 8) NOT NULL,
    unit_name TEXT NOT NULL DEFAULT 'request',
    is_active BOOLEAN DEFAULT TRUE
);

-- Insert core products
INSERT INTO products (id, name, base_price_per_unit, unit_name) VALUES
('masker', 'Masker', 0.00100000, 'request'),
('patas', 'PATAS', 0.00050000, 'request'),
('reliapi', 'ReliAPI', 0.00010000, 'request'),
('datafold', 'DataFold', 0.00200000, 'row'),
('fynx', 'Fynx', 0.00080000, 'request'),
('chart2csv', 'Chart2CSV', 0.05000000, 'image')
ON CONFLICT (id) DO NOTHING;

-- 3. API Keys (Scoped and Hashed)
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES accounts(id) ON DELETE CASCADE,
    key_prefix TEXT NOT NULL, -- e.g. 'kikusm'
    key_hash TEXT UNIQUE NOT NULL, -- HMAC-SHA256
    label TEXT,
    scopes TEXT[] DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_used_at TIMESTAMP WITH TIME ZONE
);

-- 4. Transactions Ledger (Strictly Idempotent)
CREATE TABLE IF NOT EXISTS transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES accounts(id) ON DELETE RESTRICT,
    amount_usd DECIMAL(18, 8) NOT NULL,
    type TEXT NOT NULL, -- 'topup', 'usage', 'adjustment'
    product_id TEXT REFERENCES products(id),
    idempotency_key TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 5. Usage Logs
CREATE TABLE IF NOT EXISTS usage_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES accounts(id) ON DELETE RESTRICT,
    product_id TEXT NOT NULL REFERENCES products(id),
    units_consumed INT NOT NULL,
    cost_usd DECIMAL(18, 8) NOT NULL,
    metadata_json JSONB,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 6. Audit Logs
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES accounts(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    actor_id TEXT,
    request_id TEXT,
    ip_address TEXT,
    user_agent TEXT,
    metadata_json JSONB,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 7. Debug Logs
CREATE TABLE IF NOT EXISTS debug_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES accounts(id) ON DELETE CASCADE,
    request_id TEXT,
    path TEXT NOT NULL,
    method TEXT NOT NULL,
    request_body TEXT,
    response_body TEXT,
    status_code INT NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_accounts_telegram_id ON accounts(telegram_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_account_id ON api_keys(account_id);
CREATE INDEX IF NOT EXISTS idx_transactions_account_id ON transactions(account_id);
CREATE INDEX IF NOT EXISTS idx_usage_logs_account_id_timestamp ON usage_logs(account_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_logs_account_id ON audit_logs(account_id);
CREATE INDEX IF NOT EXISTS idx_debug_logs_account_id ON debug_logs(account_id);
