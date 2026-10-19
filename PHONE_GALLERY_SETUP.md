# Phone detail gallery — setup

After applying the patch, start your backend using the earlier Python launcher (which runs migrations):

```powershell
cd "C:\Users\ak821\Desktop\phone-discover"
py dev.py
```

If you start Django manually instead, activate the project's Python virtual environment and run `python manage.py migrate` from `backend` before `python manage.py runserver`. Start the frontend separately with `cd frontend; npm run dev`.

## Add authentic photos and device finishes

The repository's existing phone records usually have **one** product photograph. This patch does not invent unseen front, back, or side photos, and does not guess what colors were manufactured. To populate the new gallery, use **Django admin** at `/admin/`:

1. Open **Catalog > Devices** and select the phone.
2. In **Official colors / finishes**, add its verified marketed finish names (for example, enter a name and an optional real swatch `#RRGGBB`). Save the phone to create the finishes.
3. In **Product photography**, enter a different **HTTPS image URL** for each verified photo. Set **View** to `Front`, `Back`, `Side`, or `Detail`. Select the exact **Color** if the picture represents that specific finish, or leave it blank for an unspecific product image. Assign an optional caption in **Alt text**, and set the sort order.
4. Save. The public View Details modal now shows these photos as labelled thumbnails and filters by selected finish.

**Important:** Swatches are visual representations of marketed finishes, not a claim that local sellers have that finish in stock. When the selected finish has no matching photos, the interface shows only unassigned/generic photos with a notice, or an empty-photo state. It never substitutes photos of a different confirmed finish.

Existing imported images continue to work unchanged. Their view is `Product photo / angle unknown` until an administrator labels it. The Django admin rejects attempting to link a photo to a color belonging to another phone. Source permissions and correct device identity should be checked before entering new image URLs.

## Verification

Frontend checks: `cd frontend; npm run test:ui`.

Backend checks (with dependencies and database): `cd backend; py manage.py check; py manage.py migrate; py manage.py test catalog.test_device_gallery`.
