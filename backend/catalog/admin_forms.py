"""Evidence-aware Django Admin forms for the Pakistan catalog.

Admin edits are trusted human operations, but research proposals are *untrusted data*.
These forms only record review decisions; they never execute research payloads or
silently copy proposed values into published phone specifications or prices.
"""

from django import forms
from django.utils import timezone

from .models import (
    DeviceClaim,
    IngestionCandidate,
    MarketPriceObservation,
    ResearchSource,
    ReviewStatus,
)


class ResearchSourceAdminForm(forms.ModelForm):
    class Meta:
        model = ResearchSource
        fields = "__all__"
        widgets = {"reuse_notes": forms.Textarea(attrs={"rows": 3})}

    def clean(self):
        data = super().clean()
        if (
            data.get("reuse_status") == ResearchSource.ReuseStatus.PERMITTED
            and not (data.get("reuse_notes") or "").strip()
        ):
            self.add_error(
                "reuse_notes",
                "Explain the permission/license or other basis for using this source.",
            )
        return data


class ReviewTimestampForm(forms.ModelForm):
    """Assign a review time before ModelForm validates model constraints.

    reviewed_at is intentionally not editable in the admin. Setting the
    instance attribute here ensures Django model full_clean sees the timestamp.
    """

    status_field = None

    def clean(self):
        data = super().clean()
        if self.status_field and data.get(self.status_field) not in (None, ReviewStatus.PENDING):
            if self.instance.reviewed_at is None:
                self.instance.reviewed_at = timezone.now()
        return data


class MarketPriceObservationAdminForm(ReviewTimestampForm):
    status_field = "verification_status"

    class Meta:
        model = MarketPriceObservation
        exclude = ("reviewed_at",)
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        data = super().clean()
        observed = data.get("observed_at")
        if observed and observed > timezone.now():
            self.add_error("observed_at", "A market observation cannot be in the future.")
        if (
            data.get("verification_status") == ReviewStatus.VERIFIED
            and not data.get("source")
            and not (data.get("notes") or "").strip()
        ):
            self.add_error(
                "notes", "Record the evidence for a verified manual price, or choose a source."
            )
        return data


class DeviceClaimAdminForm(ReviewTimestampForm):
    status_field = "status"

    class Meta:
        model = DeviceClaim
        exclude = ("reviewed_at",)
        widgets = {"review_notes": forms.Textarea(attrs={"rows": 3})}

    def clean(self):
        data = super().clean()
        if data.get("status") == ReviewStatus.VERIFIED:
            source = data.get("source") or (self.instance.source if self.instance.source_id else None)
            if source and source.reuse_status != ResearchSource.ReuseStatus.PERMITTED:
                self.add_error(
                    "status", "Verify source reuse rights before approving a research claim."
                )
        return data


class IngestionCandidateReviewForm(ReviewTimestampForm):
    status_field = "status"

    class Meta:
        model = IngestionCandidate
        exclude = ("reviewed_at",)
        widgets = {"review_notes": forms.Textarea(attrs={"rows": 3})}

    def clean(self):
        data = super().clean()
        status = data.get("status")
        if status == IngestionCandidate.Status.INGESTED:
            self.add_error(
                "status", "Ingestion is performed by a future validated ingestion service, not Admin."
            )
        if status == IngestionCandidate.Status.APPROVED:
            source = data.get("source") or (self.instance.source if self.instance.source_id else None)
            if source and source.reuse_status != ResearchSource.ReuseStatus.PERMITTED:
                self.add_error(
                    "status", "Document permitted data reuse on the source before approval."
                )
        return data
