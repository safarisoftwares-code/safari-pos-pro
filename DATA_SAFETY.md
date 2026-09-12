# DATA SAFETY MEASURES

## Where Data is Stored

- SQLite database: safari-pos-pro/database/safaripos.db
- Backups: safari-pos-pro/backups/
- Print archive: Desktop Safari-POS-Printed
- Logs: safari-pos-pro/logs/
- NOT in browser (sessionStorage cleared on logout)

## Automatic Protections

1. Backup created on every server startup
2. Soft delete for users (records preserved via cashier_name)
3. Double verification for all deletions
4. Products marked inactive instead of hard delete
5. Tax ledger is never deleted without an audit-trail manifest

## Manual Backups

- Admin can create backups anytime
- Backups saved to Desktop Safari-POS Backup
- Download backups to external storage
- Recommended: Daily backup routine

## What is NOT Stored in Browser

- Passwords (only in session for active login)
- Product data (server database only)
- Sales records (server database only)
- Business settings (server database only)

## Browser Storage Usage

- sessionStorage: Temporary token (cleared on logout/close)
- localStorage: NOT USED (cleared on login page)
- Cookies: NOT USED

## Emergency Recovery

1. Check backups/ folder or Desktop Safari-POS Backup
2. Copy latest backup .db file
3. Rename to safaripos.db
4. Replace in database/ folder
5. Restart server

## Tax Ledger Safety (v4.0 Pro)

- Live records (last 12 months) in tax_ledger
- Older records auto-archived monthly as gzipped JSON
- Each archive block has SHA-256 hash + chain to previous block
- Purge only allowed after retention period (default 5 years)
- Every purge writes a permanent manifest row with hash proof

**From Vision to Version**
