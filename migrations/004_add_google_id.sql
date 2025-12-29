-- Add google_id column to accounts table for Google OAuth support
-- Run this migration on production database

ALTER TABLE accounts ADD COLUMN IF NOT EXISTS google_id TEXT UNIQUE;

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_accounts_google_id ON accounts (google_id) WHERE google_id IS NOT NULL;
