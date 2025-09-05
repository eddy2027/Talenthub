# core/models.py — versión consolidada (autollenado + compat UI + fallback YouTube)
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
import os
import uuid

# -----------------------------
# Helpers para subir materiales
# -----------------------------
def material_upload_to(instance, filename):
    """
    Guarda archivos en: courses/<course_id>/<uuid>.<ext>
    """
    base, ext = os.path.splitext(filename)
    new_name = f"{uuid.uuid4().hex}{ext.lower()}"
    course_id = getattr(instance.course, "id", "uncategorized")
    return os.path.join("courses", str(course_id), new_name)

# Compat con migraciones antiguas
def course_material_upload_to(instance, filename):
    return material_upload_to(instance, filename)

# -----------------------------
# Department
# -----------------------------
class Department(models.Model):
    name = models.CharField(max_length=120, unique=True)
    def __str__(self):
        return self.name

# -----------------------------
# Profile (con ROLE)
# -----------------------------
class Profile(models.Model):
    SEX_CHOICES = (("M", "Male"), ("F", "Female"), ("O", "Other"))
    ROLE_ADMIN = "ADMIN"
    ROLE_MANAGER = "MANAGER"
    ROLE_LEARNER = "LEARNER"
    ROLE_CHOICES = [
        (ROLE_ADMIN, "Admin"),
        (ROLE_MANAGER, "Manager"),
        (ROLE_LEARNER, "Learner"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    phone = models.CharField(max_length=40, blank=True, default="")
    position = models.CharField(max_length=120, blank=True, default="")
    age = models.PositiveIntegerField(null=True, blank=True)
    sex = models.CharField(max_length=1, choices=SEX_CHOICES, blank=True, default="")
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.SET_NULL)
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default=ROLE_LEARNER, help_text="Access level for this user.")
    # (opcional) idioma preferido para i18n
    locale = models.CharField(max_length=8, blank=True, default="en")
    def __str__(self):
        return self.user.username

# -----------------------------
# Course
# -----------------------------
class Course(models.Model):
    title = models.CharField(max_length=255)
    instructor = models.CharField(max_length=255, blank=True, default="")
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    delivered_by_external = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)  # sin auto_now_add para compat

    # NEW: prerrequisitos (opcional, para rutas)
    prerequisites = models.ManyToManyField("self", symmetrical=False, blank=True, related_name="unlocks")

    def __str__(self):
        return self.title

# -----------------------------
# Enrollment
# -----------------------------
class Enrollment(models.Model):
    class Status(models.TextChoices):
        ASSIGNED = "ASSIGNED", "Assigned"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        COMPLETED = "COMPLETED", "Completed"
        OVERDUE = "OVERDUE", "Overdue"

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)

    enrolled_at = models.DateTimeField(default=timezone.now)
    progress = models.PositiveIntegerField(default=0)  # 0..100
    completed_at = models.DateTimeField(null=True, blank=True)

    # NEW: control operativo para P0.2
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ASSIGNED)
    due_date = models.DateField(null=True, blank=True)
    required = models.BooleanField(default=True)
    auto_enrolled = models.BooleanField(default=False)
    assigned_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_enrollments")

    class Meta:
        unique_together = ("user", "course")
        indexes = [
            models.Index(fields=["user", "course"]),
            models.Index(fields=["status"]),
        ]

    def mark_completed(self):
        self.status = self.Status.COMPLETED
        if not self.completed_at:
            self.completed_at = timezone.now()
        self.progress = 100
        self.save(update_fields=["status", "completed_at", "progress"])

    def __str__(self):
        return f"{self.user.username} -> {self.course.title}"

# -----------------------------
# Reglas de asignación (auto-enroll por dept/rol)
# -----------------------------
class CourseAssignmentRule(models.Model):
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.CASCADE)
    role = models.CharField(max_length=16, choices=Profile.ROLE_CHOICES, null=True, blank=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    due_in_days = models.PositiveIntegerField(null=True, blank=True)
    required = models.BooleanField(default=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        parts = []
        if self.department: parts.append(self.department.name)
        if self.role: parts.append(self.role)
        return f"Rule({', '.join(parts) or 'ALL'} -> {self.course.title})"

# -----------------------------
# CourseMaterial
# -----------------------------
class CourseMaterial(models.Model):
    KIND_FILE = "FILE"
    KIND_YOUTUBE = "YOUTUBE"
    KIND_CHOICES = [
        (KIND_FILE, "File"),
        (KIND_YOUTUBE, "Link"),  # la UI lo muestra como "Link"
    ]

    course = models.ForeignKey('core.Course', on_delete=models.CASCADE, related_name='materials')
    title = models.CharField(max_length=200, blank=True, default="")

    # Campos que usa tu pantalla Materials:
    kind = models.CharField(max_length=12, choices=KIND_CHOICES, default=KIND_FILE)
    youtube_url = models.URLField(blank=True, default="")
    original_name = models.CharField(max_length=255, blank=True, default="")

    file = models.FileField(upload_to=material_upload_to, blank=True, null=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    # Alias que muchas plantillas usan como "Name"
    @property
    def name(self):
        if self.title:
            return self.title
        if self.original_name:
            return self.original_name
        if self.file:
            try:
                return os.path.basename(self.file.name)
            except Exception:
                pass
        # Fallback para enlaces YouTube sin título
        if getattr(self, "youtube_url", ""):
            return "Video"
        return ""

    def save(self, *args, **kwargs):
        """
        Autollenar:
        - original_name: del archivo subido si está vacío.
        - title: si viene vacío, usar original_name (sin extensión) o, en su defecto, el basename del archivo.
        """
        # 1) Rellenar original_name si hay archivo y está vacío
        try:
            if self.file and not self.original_name:
                bn = os.path.basename(getattr(self.file, "name", "") or "")
                if bn:
                    self.original_name = bn
        except Exception:
            pass

        # 2) Rellenar title si está vacío
        if not (self.title and self.title.strip()):
            base = ""
            if self.original_name:
                base, _ = os.path.splitext(self.original_name)
            elif self.file:
                try:
                    bn = os.path.basename(self.file.name or "")
                    base, _ = os.path.splitext(bn)
                except Exception:
                    base = ""
            if base:
                self.title = base[:200]

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name or f"Material #{self.pk}"

# -----------------------------
# MaterialProgress
# -----------------------------
class MaterialProgress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    material = models.ForeignKey(CourseMaterial, on_delete=models.CASCADE)
    percent = models.PositiveIntegerField(default=0)  # 0..100
    is_completed = models.BooleanField(default=False)
    last_position_seconds = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'material')

    def __str__(self):
        return f"{self.user.username} - {self.material_id} ({self.percent}%)"

# -----------------------------
# QUizzes / Evaluaciones (P0.3)
# -----------------------------
class Quiz(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="quizzes")
    title = models.CharField(max_length=200)
    pass_score = models.PositiveSmallIntegerField(default=70)  # porcentaje requerido
    time_limit_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    attempts_allowed = models.PositiveSmallIntegerField(default=1)
    randomize = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.course.title} · {self.title}"

class Question(models.Model):
    class Kind(models.TextChoices):
        MULTIPLE = "MULTIPLE", "Multiple Choice"
        TRUE_FALSE = "TRUE_FALSE", "True/False"
        SHORT_TEXT = "SHORT_TEXT", "Short Text"

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField()
    question_type = models.CharField(max_length=12, choices=Kind.choices, default=Kind.MULTIPLE)
    points = models.PositiveSmallIntegerField(default=1)

    def __str__(self):
        return f"{self.quiz.title} · {self.question_type}"

class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    text = models.CharField(max_length=300)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.question_id} · {self.text[:40]}"

class QuizAttempt(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="attempts")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(null=True, blank=True)
    passed = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["quiz", "user", "started_at"])]

    def __str__(self):
        return f"Attempt {self.id} · {self.user.username}"

class QuizAnswer(models.Model):
    attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_choice = models.ForeignKey(Choice, null=True, blank=True, on_delete=models.SET_NULL)
    free_text = models.TextField(blank=True, default="")

    def __str__(self):
        return f"Ans {self.id} · Q{self.question_id}"
