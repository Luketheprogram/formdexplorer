from django import forms
from .models import Collection, ReaderRequest, ResearchItem


class CollectionForm(forms.ModelForm):
    description = forms.CharField(
        required=False, max_length=2000, widget=forms.Textarea
    )

    class Meta:
        model = Collection
        fields = ["name", "description"]


class ItemForm(forms.ModelForm):
    note = forms.CharField(required=False, max_length=10000, widget=forms.Textarea)

    class Meta:
        model = ResearchItem
        fields = ["dataset", "reference", "note"]

    def clean(self):
        data = super().clean()
        if data.get("dataset") and data.get("reference"):
            if data["dataset"] == "adv":
                from advisers.models import Adviser

                found = Adviser.objects.filter(crd=data["reference"]).exists()
            else:
                from .evidence import MODELS

                found = (
                    MODELS[data["dataset"]]
                    .objects.filter(accession_number=data["reference"])
                    .exists()
                )
            if not found:
                raise forms.ValidationError(
                    "Choose an existing stored disclosure or adviser identifier."
                )
        return data


class ReaderRequestForm(forms.ModelForm):
    description = forms.CharField(max_length=10000, widget=forms.Textarea)
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = ReaderRequest
        fields = [
            "kind",
            "dataset",
            "reference",
            "field",
            "description",
            "email",
            "consent_to_contact",
        ]

    def clean(self):
        data = super().clean()
        if data.get("website"):
            raise forms.ValidationError("The request could not be accepted.")
        if data.get("email") and not data.get("consent_to_contact"):
            self.add_error(
                "consent_to_contact",
                "Choose permission to use the contact address, or leave the email blank.",
            )
        return data
