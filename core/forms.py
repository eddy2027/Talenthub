# core/forms.py — CourseMaterialForm robusto (File o YouTube)
from django import forms
from .models import CourseMaterial

class CourseMaterialForm(forms.ModelForm):
    class Meta:
        model = CourseMaterial
        fields = ["kind", "title", "file", "youtube_url"]
        widgets = {
            "kind": forms.Select(attrs={"class": "form-control"}),
            "title": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Title of the material (optional)",
            }),
            "file": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "youtube_url": forms.URLInput(attrs={
                "class": "form-control",
                "placeholder": "https://www.youtube.com/watch?v=...",
            }),
        }
        help_texts = {
            "file": "Allowed: PDF, PPT, DOCX, images, etc.",
        }

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get("kind")
        f = cleaned.get("file")
        yt = (cleaned.get("youtube_url") or "").strip()

        if kind == CourseMaterial.KIND_FILE:
            # Para archivos: exigir file y limpiar youtube_url
            if not f:
                raise forms.ValidationError("File is required for Type = File.")
            cleaned["youtube_url"] = ""
        elif kind == CourseMaterial.KIND_YOUTUBE:
            # Para YouTube: exigir url y anular file
            if not yt:
                raise forms.ValidationError("YouTube URL is required for Type = YouTube.")
            cleaned["file"] = None
            cleaned["youtube_url"] = yt
        else:
            raise forms.ValidationError("Invalid material type.")

        return cleaned

# ==== QUIZ CREATION FORMS (frontend) ====
from django import forms
from .models import Quiz, Question, Choice

class QuizCreateForm(forms.ModelForm):
    class Meta:
        model = Quiz
        fields = ["title", "pass_score", "attempts_allowed", "time_limit_minutes", "active"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "input", "placeholder": "Quiz title"}),
            "pass_score": forms.NumberInput(attrs={"min": 0, "max": 100}),
            "attempts_allowed": forms.NumberInput(attrs={"min": 1}),
            "time_limit_minutes": forms.NumberInput(attrs={"min": 1}),
        }

class QuestionCreateForm(forms.Form):
    question_type = forms.ChoiceField(choices=Question.Kind.choices, initial=Question.Kind.MULTIPLE)
    text = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), max_length=2000)
    points = forms.IntegerField(min_value=1, initial=1)

    # Para MULTIPLE
    choice1 = forms.CharField(required=False, max_length=300, label="Choice 1")
    choice2 = forms.CharField(required=False, max_length=300, label="Choice 2")
    choice3 = forms.CharField(required=False, max_length=300, label="Choice 3")
    choice4 = forms.CharField(required=False, max_length=300, label="Choice 4")
    correct_choice = forms.ChoiceField(
        required=False,
        choices=[("1", "1"), ("2", "2"), ("3", "3"), ("4", "4")],
        label="Which choice is correct?",
        widget=forms.RadioSelect
    )

    # Para TRUE/FALSE
    true_is_correct = forms.BooleanField(
        required=False,
        label="Mark if 'True' is the correct answer (otherwise 'False' will be correct)."
    )

    def clean(self):
        data = super().clean()
        qtype = data.get("question_type")
        if qtype == Question.Kind.MULTIPLE:
            choices = [data.get("choice1"), data.get("choice2"), data.get("choice3"), data.get("choice4")]
            filled = [c for c in choices if c and c.strip()]
            if len(filled) < 2:
                raise forms.ValidationError("Provide at least two choices.")
            cc = data.get("correct_choice")
            if not cc:
                raise forms.ValidationError("Select which choice is correct.")
            idx = int(cc)
            if not choices[idx - 1]:
                raise forms.ValidationError("Correct choice must have text.")
        # TRUE_FALSE y SHORT_TEXT no requieren validación adicional aquí
        return data
