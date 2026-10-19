# Phone Discover Django admin — burgundy & white redesign

## What changes

- Branded white header and navigation shared by the entire native Django admin.
- New permission-aware dashboard with catalog totals, publishing status, unreviewed PKR observations, refresh status, shortcuts and a complete automatically populated admin directory.
- Light background, black text, burgundy buttons/links, consistent tables, inputs, filters, form pages and login page.
- Compact responsive layout at mobile widths and reduced-motion support.
- The Price Refresh button remains a CSRF-protected POST on its **Price refresh runs** changelist; dashboard links only open that page.
- No API, model, migration, or database changes. All existing permissions and review rules remain in force.

## Apply on your current project

This patch is based on the Phone Discover backend **after** the previously supplied 48-hour price-refresh patch and gallery/color patch. Do not apply to the original unpatched backend.

```powershell
cd "C:\Users\ak821\Desktop\phone-discover"
$patch = "$HOME\Downloads\phone_discover_admin_burgundy_dashboard.patch"
git apply --check $patch
if ($LASTEXITCODE -eq 0) { git apply $patch }
```

Restart Django:

```powershell
py dev.py
```

Open **http://127.0.0.1:8000/admin/**. If already signed in, press **Ctrl+Shift+R** to refresh cached CSS.

## Verification

With backend dependencies installed and PostgreSQL running:

```powershell
cd "C:\Users\ak821\Desktop\phone-discover\backend"
.\.venv\Scripts\python.exe manage.py test config.test_admin_design
```

For production static file hosting, run `collectstatic` through your normal deployment process. This style sheet is local (`catalog/admin/brand_admin.css`) and needs no CDN.

## Limitations

- Dashboard counters summarize the local database, not a live remote price crawl.
- No new background refresh runs are launched from the homepage.
- All admin screens still use Django's native forms, validations and permission checks.
- The first live Django render should be checked in your Windows environment, because the packaging environment cannot install Django.
