# core/services/assignments.py
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from ..models import Enrollment, CourseAssignmentRule, Course, MaterialProgress, Profile

def assign_course(user, course, due_date=None, assigned_by=None, required=True, auto=False):
    obj, created = Enrollment.objects.get_or_create(
        user=user, course=course,
        defaults={
            "due_date": due_date,
            "assigned_by": assigned_by,
            "required": required,
            "auto_enrolled": auto,
        },
    )
    if not created and due_date and not obj.due_date:
        obj.due_date = due_date
        obj.save(update_fields=["due_date"])
    return obj, created

def assign_by_rules(user):
    # Reglas activas por dept/rol con fallback a null
    prof = getattr(user, "profile", None)
    qs = CourseAssignmentRule.objects.filter(active=True)

    dept_id = getattr(prof, "department_id", None)
    role = getattr(prof, "role", None)

    # department: (igual) o (null)
    if dept_id:
        qs = qs.filter(department_id=dept_id) | qs.filter(department__isnull=True)
    else:
        qs = qs.filter(department__isnull=True)

    # role: (igual) o (null)
    if role:
        qs = qs.filter(role=role) | qs.filter(role__isnull=True)
    else:
        qs = qs.filter(role__isnull=True)

    qs = qs.distinct()
    today = timezone.now().date()
    for rule in qs:
        due = today + timedelta(days=rule.due_in_days) if rule.due_in_days else None
        assign_course(user, rule.course, due_date=due, assigned_by=None, required=rule.required, auto=True)

def recompute_enrollment_progress_for(user, course: Course):
    total = course.materials.count()
    if total == 0:
        percent = 0
    else:
        done = MaterialProgress.objects.filter(user=user, material__course=course, is_completed=True).count()
        percent = int(round(100 * done / total))

    enr, _ = Enrollment.objects.get_or_create(user=user, course=course)
    # Estado por vencimiento
    if enr.due_date and percent < 100 and timezone.now().date() > enr.due_date:
        enr.status = Enrollment.Status.OVERDUE
    else:
        if percent == 0:
            enr.status = Enrollment.Status.ASSIGNED
        elif percent < 100:
            enr.status = Enrollment.Status.IN_PROGRESS
        else:
            enr.status = Enrollment.Status.COMPLETED
            if not enr.completed_at:
                enr.completed_at = timezone.now()

    enr.progress = percent
    enr.save(update_fields=["status", "progress", "completed_at"])
