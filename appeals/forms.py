"""
Appeals app forms - Forms for appeal creation, decision tree, and management.
"""

from django import forms
from django.core.exceptions import ValidationError
from datetime import date

from .models import Appeal, AppealDocument, AppealNote


class AppealStartForm(forms.ModelForm):
    """
    Initial form to start an appeal - captures basic info about the decision being appealed.
    """

    class Meta:
        model = Appeal
        fields = [
            "original_decision_date",
            "conditions_appealed",
            "denial_reasons",
        ]
        widgets = {
            "original_decision_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "form-input",
                    "aria-describedby": "decision-date-help",
                }
            ),
            "conditions_appealed": forms.Textarea(
                attrs={
                    "rows": 4,
                    "class": "form-textarea",
                    "placeholder": "Example:\n- PTSD (denied)\n- Lower back (rated 10%, believe it should be higher)\n- Tinnitus (denied)",
                    "aria-describedby": "conditions-help",
                }
            ),
            "denial_reasons": forms.Textarea(
                attrs={
                    "rows": 4,
                    "class": "form-textarea",
                    "placeholder": "What reasons did the VA give for denying or under-rating your conditions?",
                    "aria-describedby": "denial-help",
                }
            ),
        }
        labels = {
            "original_decision_date": "Date of VA Decision",
            "conditions_appealed": "What conditions are you appealing?",
            "denial_reasons": "Why was your claim denied or rated low?",
        }
        help_texts = {
            "original_decision_date": "Find this date on your Rating Decision letter.",
            "conditions_appealed": "List each condition and whether it was denied or rated too low.",
            "denial_reasons": "This helps us recommend the right appeal type.",
        }

    def clean_original_decision_date(self):
        decision_date = self.cleaned_data.get("original_decision_date")
        if decision_date and decision_date > date.today():
            raise ValidationError("Decision date cannot be in the future.")
        # We intentionally do NOT reject decisions older than one year here.
        # This intake form runs BEFORE the appeal lane is chosen, and a
        # Supplemental Claim has no filing deadline (38 CFR § 20.204) — blocking
        # old decisions wrongly turned away veterans who can still file one.
        # Lane-specific deadline handling happens once the lane is known: the
        # model's save() sets Appeal.deadline per lane (None for supplemental,
        # decision + 1 year for HLR/Board per 38 CFR § 20.202), and the appeal
        # detail page surfaces urgency/overdue status from there.
        return decision_date


class DecisionTreeForm(forms.Form):
    """
    Decision tree questions to recommend the best appeal type.
    Based on research: new evidence → Supplemental, VA error → HLR
    """

    has_new_evidence = forms.ChoiceField(
        label="Do you have NEW evidence the VA has not seen?",
        choices=[
            ("", "Select..."),
            (
                "yes",
                "Yes - I have new medical records, nexus letters, or other evidence",
            ),
            ("no", "No - I don't have any new evidence"),
            ("unsure", "I'm not sure"),
        ],
        widget=forms.Select(
            attrs={
                "class": "form-select",
                "aria-describedby": "evidence-help",
            }
        ),
        help_text="New evidence means records, letters, or statements the VA did not review in your original claim.",
    )

    believes_va_error = forms.ChoiceField(
        label="Do you believe the VA made an error with your existing evidence?",
        choices=[
            ("", "Select..."),
            (
                "yes",
                "Yes - They misread records, ignored evidence, or made a calculation error",
            ),
            (
                "no",
                "No - They reviewed everything correctly, I just disagree with the decision",
            ),
            ("unsure", "I'm not sure"),
        ],
        widget=forms.Select(
            attrs={
                "class": "form-select",
                "aria-describedby": "error-help",
            }
        ),
        help_text="Examples: VA ignored a nexus letter, miscalculated your combined rating, or didn't consider flare-ups.",
    )

    wants_hearing = forms.ChoiceField(
        label="Would you like to present your case to a judge in person?",
        choices=[
            ("", "Select..."),
            ("yes", "Yes - I want to explain my case directly"),
            ("no", "No - I prefer a paper review"),
        ],
        widget=forms.Select(
            attrs={
                "class": "form-select",
                "aria-describedby": "hearing-help",
            }
        ),
        help_text="A Board hearing lets you speak to a Veterans Law Judge, but takes longer (1-2+ years).",
    )

    def get_recommendation(self):
        """
        Return recommended appeal type based on answers.
        """
        has_evidence = self.cleaned_data.get("has_new_evidence")
        believes_error = self.cleaned_data.get("believes_va_error")
        wants_hearing = self.cleaned_data.get("wants_hearing")

        # Decision logic based on research
        if has_evidence == "yes":
            return {
                "type": "supplemental",
                "name": "Supplemental Claim",
                "form": "VA Form 20-0995",
                "time": "~93 days average",
                "reason": "You have new evidence the VA needs to consider. This is the fastest path when you have additional documentation.",
            }
        elif believes_error == "yes" and wants_hearing != "yes":
            return {
                "type": "hlr",
                "name": "Higher-Level Review",
                "form": "VA Form 20-0996",
                "time": "~141 days average",
                "reason": "You believe the VA made an error with your existing evidence. A senior reviewer will take a fresh look.",
            }
        elif wants_hearing == "yes":
            return {
                "type": "board_hearing",
                "name": "Board Appeal with Hearing",
                "form": "VA Form 10182",
                "time": "1-2+ years",
                "reason": "You want to present your case to a Veterans Law Judge. This takes longer but lets you explain your situation directly.",
            }
        elif has_evidence == "no" and believes_error == "no":
            return {
                "type": "board_direct",
                "name": "Board Appeal - Direct Review",
                "form": "VA Form 10182",
                "time": "~400-500 days",
                "reason": "Without new evidence or a clear VA error, a Board appeal gives you a fresh review by a Veterans Law Judge.",
            }
        else:
            # Unsure answers - default recommendation
            return {
                "type": "supplemental",
                "name": "Supplemental Claim (Recommended starting point)",
                "form": "VA Form 20-0995",
                "time": "~93 days average",
                "reason": "If you're unsure, gathering new evidence (like a nexus letter) and filing a Supplemental Claim is often the best path.",
            }


class AppealTypeForm(forms.ModelForm):
    """
    Form to select/confirm appeal type after decision tree.
    """

    class Meta:
        model = Appeal
        fields = ["appeal_type"]
        widgets = {
            "appeal_type": forms.RadioSelect(
                attrs={
                    "class": "form-radio",
                }
            ),
        }

    def __init__(self, *args, recommended_type=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.recommended_type = recommended_type
        # Add recommendation indicator to choices
        if recommended_type:
            choices = []
            for value, label in Appeal.APPEAL_TYPE_CHOICES:
                if value == recommended_type or (
                    recommended_type.startswith("board") and value.startswith("board")
                ):
                    label = f"{label} (Recommended)"
                choices.append((value, label))
            self.fields["appeal_type"].choices = choices


class AppealUpdateForm(forms.ModelForm):
    """
    Form to update appeal status and tracking info.
    """

    class Meta:
        model = Appeal
        fields = [
            "status",
            "submission_date",
            "va_confirmation_number",
            "notes",
        ]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
            "submission_date": forms.DateInput(
                attrs={"type": "date", "class": "form-input"}
            ),
            "va_confirmation_number": forms.TextInput(attrs={"class": "form-input"}),
            "notes": forms.Textarea(attrs={"rows": 4, "class": "form-textarea"}),
        }


class AppealDecisionForm(forms.ModelForm):
    """
    Form to record appeal decision outcome.
    """

    class Meta:
        model = Appeal
        fields = [
            "decision_received_date",
            "decision_outcome",
            "decision_notes",
        ]
        widgets = {
            "decision_received_date": forms.DateInput(
                attrs={"type": "date", "class": "form-input"}
            ),
            "decision_outcome": forms.Select(attrs={"class": "form-select"}),
            "decision_notes": forms.Textarea(
                attrs={
                    "rows": 4,
                    "class": "form-textarea",
                    "placeholder": "Summarize the decision and any next steps...",
                }
            ),
        }


class AppealDocumentForm(forms.ModelForm):
    """
    Form to upload/track documents for an appeal.
    """

    class Meta:
        model = AppealDocument
        fields = ["document_type", "title", "file", "notes"]
        widgets = {
            "document_type": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": 'e.g., "Dr. Smith Nexus Letter" or "2024 MRI Report"',
                }
            ),
            "file": forms.FileInput(
                attrs={
                    "class": "form-input",
                    "accept": ".pdf,.jpg,.jpeg,.png,.tiff",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "rows": 2,
                    "class": "form-textarea",
                    "placeholder": "Optional notes about this document...",
                }
            ),
        }


class AppealNoteForm(forms.ModelForm):
    """
    Form to add notes/updates to appeal timeline.
    """

    class Meta:
        model = AppealNote
        fields = ["note_type", "content", "is_important"]
        widgets = {
            "note_type": forms.Select(attrs={"class": "form-select"}),
            "content": forms.Textarea(
                attrs={
                    "rows": 3,
                    "class": "form-textarea",
                    "placeholder": "What happened? What did you do?",
                }
            ),
            "is_important": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
        }
