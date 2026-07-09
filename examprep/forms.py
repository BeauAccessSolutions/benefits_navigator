"""
Forms for examprep app - Accessible form validation
"""

from django import forms
from .models import ExamChecklist


class ExamChecklistForm(forms.ModelForm):
    """
    Form for creating and updating exam preparation checklists
    Includes accessible labels and help text
    """

    class Meta:
        model = ExamChecklist
        fields = [
            "condition",
            "exam_date",
            "guidance",
            "symptom_notes",
            "worst_day_description",
            "functional_limitations",
            "questions_for_examiner",
        ]

        labels = {
            "condition": "Condition or Disability",
            "exam_date": "Scheduled Exam Date",
            "guidance": "Related Exam Guide (optional)",
            "symptom_notes": "Symptom Notes",
            "worst_day_description": "Describe Your Worst Days",
            "functional_limitations": "How Does This Affect Your Daily Life?",
            "questions_for_examiner": "Questions for the Examiner",
        }

        help_texts = {
            "condition": "What condition is this exam for? (e.g., PTSD, Back Pain, Tinnitus)",
            "exam_date": "When is your C&P exam scheduled? Leave blank if not yet scheduled.",
            "guidance": "Select an exam guide if you want to use a template checklist.",
            "symptom_notes": "Note all symptoms you experience, including frequency and severity.",
            "worst_day_description": "Describe what happens on your worst days with this condition. Be specific about how it impacts you.",
            "functional_limitations": "How does this condition limit your ability to work, socialize, or perform daily activities?",
            "questions_for_examiner": "Write down any questions you want to ask the examiner during your appointment.",
        }

        widgets = {
            "condition": forms.TextInput(
                attrs={
                    "placeholder": "e.g., PTSD, Back Pain, Tinnitus",
                    "aria-required": "true",
                }
            ),
            "exam_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "aria-describedby": "id_exam_date_help",
                }
            ),
            "guidance": forms.Select(
                attrs={
                    "aria-describedby": "id_guidance_help",
                }
            ),
            "symptom_notes": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "List your symptoms, when they occur, and how severe they are...",
                    "aria-describedby": "id_symptom_notes_help",
                }
            ),
            "worst_day_description": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "On my worst days, I experience...",
                    "aria-describedby": "id_worst_day_description_help",
                }
            ),
            "functional_limitations": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "This condition makes it difficult for me to...",
                    "aria-describedby": "id_functional_limitations_help",
                }
            ),
            "questions_for_examiner": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Questions I want to ask...",
                    "aria-describedby": "id_questions_for_examiner_help",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Filter guidance to only show published guides
        from .models import ExamGuidance

        self.fields["guidance"].queryset = ExamGuidance.objects.filter(
            is_published=True
        ).order_by("category", "title")

        # Make guidance optional
        self.fields["guidance"].required = False

    def clean_condition(self):
        """Validate condition field"""
        condition = self.cleaned_data.get("condition", "").strip()
        if not condition:
            raise forms.ValidationError("Please enter the condition for this exam.")
        if len(condition) < 3:
            raise forms.ValidationError("Condition name must be at least 3 characters.")
        return condition
