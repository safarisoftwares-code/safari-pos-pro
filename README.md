# Safari POS Pro

Complete Point of Sale Solution by Safari Softwares

**From Vision to Version**

Version: 4.0.0 (Pro)

---

## Quick Start

### Windows (Recommended)
Double-click the desktop icon **Safari POS Pro**.

The launcher will:
1. Show a splash screen
2. Start the backend server silently
3. Open the app in Edge app-mode (looks like a native desktop app)

### Manual (Development)
1. pip install -r requirements.txt
2. cd backend
3. python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Access: http://localhost:8000

---

## Features (v4.0 Pro)

### Inherited from v3.0 Standard
- Authentication (Admin, Manager, Cashier)
- Product Management with Categories
- Sales Processing (Cash, M-Pesa, Card)
- User Management
- Reports and Analytics
- Data Backup
- Mobile Responsive Design
- A/B Tax (16% inclusive VAT)
- Permanent tax ledger
- Purchase Orders
- Expiry tracking

### New in v4.0 Pro
- Print Queue System - Phone cashiers auto-print to main PC
- PDF Fallback - If main PC offline, print to PDF archive
- Print Archive - Desktop Safari-POS-Printed organized by date
- Printer Configuration - Settings page with auto-detect Windows printers
- Phone Integration - Auto-detect mobile, auto-queue print jobs
- Tax Ledger v2 - 3-tier archive system (live + archive + purge-manifest)
- Smooth Launcher - Splash screen + app-mode Edge (no dinosaur errors)

---

## User Roles

- Admin: Everything - products, users, reports, backup, tax purge
- Manager: Products, reports, inventory (no user delete, no tax purge)
- Cashier: Sales only

---

## Project Structure

safari-pos-pro/
  backend/
    main.py
    database.py
    models.py
    auth.py
    schemas.py
    core/
    services/
      tax_archiver.py
      print_processor.py
    routers/
      auth.py, products.py, sales.py, customers.py,
      reports.py, users.py, backup.py, settings.py,
      purchase_orders.py, analytics.py, mpesa.py,
      tax.py, print_queue.py, printers.py
  frontend/
    index.html
    login.html
    css/style.css
    js/
      auth.js, app.js, main.js, analytics.js, tax.js,
      print_queue.js
    assets/
  launcher/
    Safari-POS-Pro.vbs
    splash.html
    splash.css
    splash.js
    start_server.bat
    launcher_helpers.bat
    assets/
  database/
  backups/
  logs/
  docs/
  dist/
  .env
  .env.example
  .gitignore
  requirements.txt
  README.md
  DATA_SAFETY.md

---

## Security

- Credentials stored in .env (never committed to git)
- JWT authentication
- Role-based access control
- Password hashing with bcrypt
- Recovery code (one-time use) for admin password reset

---

## Tax Ledger Retention (KRA-Compliant)

- Live tier (tax_ledger): Last 12 months, fast queries
- Archive tier (tax_ledger_archive): Older, gzipped JSON per month, up to 5 years
- Purge manifest (tax_ledger_purged): Permanent proof of purged records with SHA-256 hash
- Auto-archive: Runs once per day on server startup
- Manual purge: Admin-only, requires typing confirmation, creates backup first

---

## About Safari Softwares

Website: https://safarisoftwares.co.ke
Email: info@safarisoftwares.co.ke

**From Vision to Version**

Copyright 2026 Safari Softwares. All Rights Reserved.
