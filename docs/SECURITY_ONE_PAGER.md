# KikuAI Security One-Pager

This document provides a high-level overview of the security measures and policies governing the KikuAI API platform.

## 1. Data Integrity & Financial Precision
- **Financial Ledger:** All transactions are recorded in a PostgreSQL-based ledger with `DECIMAL(18, 8)` precision.
- **Race Condition Protection:** We use row-level locking (`FOR UPDATE`) to ensure atomic balance adjustments.
- **Indempotency:** All state-changing operations (usage recording, top-ups) are protected by unique idempotency keys.

## 2. API Security Architecture
- **Key Structure:** Keys follow the `kikuai_{prefix}_{secret}` format. 
- **HMAC Storage:** We only store the 12-character hex prefix and the **HMAC-SHA256 hash** of the secret. Plaintext secrets are never stored in our persistent layer.
- **Prefix-based Revocation:** Customers can revoke keys via the public prefix without exposing the secret.
- **Brute-force Prevention:** Automatic rate-limiting on authentication failures is enforced at the IP level.

## 3. Infrastructure & Resilience
- **Database Fallback:** Our system implements a circuit breaker for Redis. In the event of a cache failure, the system falls back to a PostgreSQL source-of-truth.
- **Traceability:** Every request is assigned a unique `X-Request-ID`, which is propagated through all internal service calls and audit logs.

## 4. Privacy & Data Handling
- **Stateless Proxying:** No customer input data is stored by default.
- **Opt-in Debugging:** Detailed request/response logging is disabled by default. If enabled by the user for troubleshooting, logs are stored in an encrypted table and automatically purged after **24 hours**.
- **Audit Logging:** Administrative actions (key management, login) are logged with IP and User-Agent metadata for security auditing.

## 5. Authentication Fallback
- **Primary Auth:** Telegram-based secure login.
- **Secondary Auth:** Email-based magic link login for environments where Telegram access is restricted.

---
*For more detailed information or specific compliance requests, please contact security@kikuai.dev.*
