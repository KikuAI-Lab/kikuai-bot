-- KikuAI Unified Schema Initialization (Refined B2B Edition)
-- Purpose: Source of Truth for Accounts, Billing, Scoped Keys, and Ledger

-- 1. Accounts (Unified Billing Entity)
CREATE TABLE IF NOT EXISTS accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id BIGINT UNIQUE NOT NULL,
    email TEXT,
    balance_usd DECIMAL(12, 4) DEFAULT 0.0000,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_active_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Products Metadata
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY, -- 'masker', 'patas', 'reliapi', 'datafold', 'fynx', 'chart2csv'
    name TEXT NOT NULL,
    base_price_per_unit DECIMAL(12, 6) NOT NULL,
    unit_name TEXT NOT NULL DEFAULT 'request',
    is_active BOOLEAN DEFAULT TRUE
);

-- Insert core products
INSERT INTO products (id, name, base_price_per_unit, unit_name) VALUES
('masker', 'Masker', 0.001000, 'request'),
('patas', 'PATAS', 0.000500, 'request'),
('reliapi', 'ReliAPI', 0.000100, 'request'),
('datafold', 'DataFold', 0.002000, 'row'),
('fynx', 'Fynx', 0.000800, 'request'),
('chart2csv', 'Chart2CSV', 0.050000, 'image')
ON CONFLICT (id) DO NOTHING;

-- 3. API Keys (Scoped and Hashed)
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES accounts(id) ON DELETE CASCADE,
    key_hash TEXT UNIQUE NOT NULL,
    label TEXT,
    scopes TEXT[] DEFAULT '{}', -- e.g. {'masker:read', 'patas:write'}
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_used_at TIMESTAMP WITH TIME ZONE
);

-- 4. Transactions Ledger (Strictly Idempotent)
CREATE TABLE IF NOT EXISTS transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES accounts(id) ON DELETE RESTRICT,
    amount_usd DECIMAL(12, 4) NOT NULL,
    type TEXT NOT NULL, -- 'topup', 'usage', 'refund', 'adjustment'
    product_id TEXT REFERENCES products(id),
    idempotency_key TEXT UNIQUE NOT NULL, -- Required for all financial events
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 5. Usage Logs (Granular activity for analytics/billing)
CREATE TABLE IF NOT EXISTS usage_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES accounts(id) ON DELETE RESTRICT,
    product_id TEXT NOT NULL REFERENCES products(id),
    units_consumed INT NOT NULL,
    cost_usd DECIMAL(12, 6) NOT NULL,
    metadata JSONB,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_accounts_telegram_id ON accounts(telegram_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_account_id ON api_keys(account_id);
CREATE INDEX IF NOT EXISTS idx_transactions_account_id ON transactions(account_id);
CREATE INDEX IF NOT EXISTS idx_usage_logs_account_id_timestamp ON usage_logs(account_id, timestamp);
