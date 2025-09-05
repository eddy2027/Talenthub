from django.contrib import admin
from pathlib import Path
from django.contrib import messages

from .models import (
    Department, Profile, Course, Enrollment, CourseAssignmentRule,
    CourseMaterial, MaterialProgress,
    Quiz, Question, Choice, QuizAttempt, QuizAnswer
)

# para calificar intentos
from core.services.quiz import grade_attempt

# ---------------------------
# Department / Profile
# ---------------------------
@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "role", "department", "locale", "position", "phone")
    list_filter = ("role", "department")
    search_fields = ("user__username", "user__first_name", "user__last_name", "position", "phone")
    autocomplete_fields = ("department",)

# ---------------------------
# Course / Enrollment / Rules
# ---------------------------
@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "instructor", "duration_minutes", "created_at", "delivered_by_external")
    search_fields = ("title", "instructor")
    filter_horizontal = ("prerequisites",)

@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = (
        "id", "user", "course", "status", "progress", "due_date",
        "required", "auto_enrolled", "enrolled_at", "completed_at", "assigned_by"
    )
    list_filter = ("status", "required", "auto_enrolled")
    search_fields = ("user__username", "user__email", "course__title")
    autocomplete_fields = ("user", "course", "assigned_by")

@admin.register(CourseAssignmentRule)
class CourseAssignmentRuleAdmin(admin.ModelAdmin):
    list_display = ("id", "department", "role", "course", "due_in_days", "required", "active", "created_at")
    list_filter = ("active", "role", "department")
    search_fields = ("course__title",)
    autocomplete_fields = ("department", "course")

# ---------------------------
# Materials / Progress
# ---------------------------
@admin.register(CourseMaterial)
class CourseMaterialAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "display_title", "kind", "filename", "uploaded_by", "uploaded_at")
    list_filter = ("kind", "course")
    search_fields = ("title", "original_name", "youtube_url", "course__title")
    autocomplete_fields = ("course", "uploaded_by")

    def display_title(self, obj):
        return obj.title or obj.original_name or self.filename(obj) or "Material"
    display_title.short_description = "Title"

    def filename(self, obj):
        try:
            if obj.file:
                return Path(obj.file.name).name
        except Exception:
            pass
        return "-"
    filename.short_description = "Filename"
    filename.admin_order_field = "file"

@admin.register(MaterialProgress)
class MaterialProgressAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "material", "percent", "is_completed", "last_position_seconds", "updated_at")
    list_filter = ("is_completed",)
    search_fields = ("user__username", "user__email", "material__title", "material__course__title")
    autocomplete_fields = ("user", "material")

# ---------------------------
# Quizzes
# ---------------------------
class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 1

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "quiz", "question_type", "points")
    inlines = [ChoiceInline]
    autocomplete_fields = ("quiz",)
    search_fields = ("text", "quiz__title", "quiz__course__title")

@admin.register(Choice)
class ChoiceAdmin(admin.ModelAdmin):
    list_display = ("id", "question", "text", "is_correct")
    autocomplete_fields = ("question",)
    search_fields = ("text", "question__text", "question__quiz__title", "question__quiz__course__title")

@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "title", "pass_score", "attempts_allowed", "active", "created_at")
    search_fields = ("title", "course__title")
    autocomplete_fields = ("course",)

def admin_grade_attempts(modeladmin, request, queryset):
    graded = 0
    for attempt in queryset:
        grade_attempt(attempt)
        graded += 1
    messages.success(request, f"Calificados {graded} intento(s).")

admin_grade_attempts.short_description = "Calificar intentos seleccionados"

@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ("id", "quiz", "user", "score", "passed", "started_at", "finished_at")
    list_filter = ("passed",)
    autocomplete_fields = ("quiz", "user")
    search_fields = ("user__username", "user__email", "quiz__title", "quiz__course__title")
    actions = [admin_grade_attempts]

@admin.register(QuizAnswer)
class QuizAnswerAdmin(admin.ModelAdmin):
    list_display = ("id", "attempt", "question", "selected_choice")
    autocomplete_fields = ("attempt", "question", "selected_choice")
    search_fields = ("attempt__user__username", "attempt__quiz__title", "question__text")
