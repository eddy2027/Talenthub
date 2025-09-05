# core/extra_views.py — vistas auxiliares (impersonación, equipo, mis cursos)
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.db.models import Avg, Count, Q
from django.utils import timezone

from .models import Profile, Enrollment, Department, Course


# ---------- Helpers de rol ----------
def _role_of(user):
    try:
        return user.profile.role
    except Exception:
        return Profile.ROLE_LEARNER


def _is_admin(user):
    return user.is_superuser or _role_of(user) == Profile.ROLE_ADMIN


def _is_manager(user):
    r = _role_of(user)
    return r == Profile.ROLE_MANAGER or _is_admin(user)


# ---------- Impersonación (solo admin) ----------
@login_required
def impersonate_start(request, user_id):
    if not _is_admin(request.user):
        messages.error(request, "Not authorized.")
        return redirect("user_list")

    target = get_object_or_404(User, pk=user_id)
    if request.user.id == target.id:
        messages.info(request, "You are already this user.")
        return redirect("dashboard")

    # Guardamos SIEMPRE el admin y una bandera robusta
    request.session["impersonator_id"] = request.user.id
    request.session["is_impersonating"] = "1"

    # Cambiamos las credenciales activas
    target.backend = "django.contrib.auth.backends.ModelBackend"
    login(request, target, backend=target.backend)
    messages.success(request, f"Now impersonating: {target.username}")
    return redirect("dashboard")


@login_required
def impersonate_stop(request):
    # Quitamos ambas banderas
    orig_id = request.session.pop("impersonator_id", None)
    request.session.pop("is_impersonating", None)

    if not orig_id:
        messages.info(request, "You are not impersonating anyone.")
        return redirect("dashboard")

    original = get_object_or_404(User, pk=orig_id)
    original.backend = "django.contrib.auth.backends.ModelBackend"
    login(request, original, backend=original.backend)
    messages.success(request, "Stopped impersonation.")
    return redirect("dashboard")


# ---------- Manager: ver/definir equipo + RESUMEN ----------
@login_required
def team(request):
    if not _is_manager(request.user):
        messages.error(request, "Not authorized.")
        return redirect("dashboard")

    # Permitir al manager (o admin) fijar su propio departamento desde aquí
    if request.method == "POST":
        dep_id = request.POST.get("department_id")
        dep_name = (request.POST.get("department_name") or "").strip()

        dept = None
        if dep_id:
            try:
                dept = Department.objects.get(pk=int(dep_id))
            except Exception:
                dept = None
        elif dep_name:
            dept, _ = Department.objects.get_or_create(name=dep_name)

        prof, _ = Profile.objects.get_or_create(user=request.user)
        prof.department = dept
        prof.save()
        messages.success(request, "Department updated for your profile.")
        return redirect("team")

    # Departamento del manager (o el que establezca el admin)
    my_profile = getattr(request.user, "profile", None)
    dept = getattr(my_profile, "department", None)

    # Usuarios del equipo
    qs = User.objects.select_related("profile").all()
    if dept:
        qs = qs.filter(profile__department=dept).order_by("username")
    else:
        qs = qs.none()

    # --- MÉTRICAS DEL EQUIPO ---
    total_users = qs.count()

    enroll_qs = Enrollment.objects.select_related("user", "course").filter(user__in=qs)
    total_enrolls = enroll_qs.count()
    completed_enrolls = enroll_qs.filter(progress__gte=100).count()
    avg_progress = enroll_qs.aggregate(v=Avg("progress"))["v"] or 0.0
    avg_progress = round(float(avg_progress), 1)

    distinct_users_with_enrolls = enroll_qs.values("user_id").distinct().count()
    users_without_enrolls = max(total_users - distinct_users_with_enrolls, 0)

    distinct_courses = enroll_qs.values("course_id").distinct().count()

    # Por curso
    per_course_raw = (
        enroll_qs.values("course_id", "course__title")
        .annotate(
            learners=Count("id"),
            avg=Avg("progress"),
            completed=Count("id", filter=Q(progress__gte=100)),
        )
        .order_by("course__title")
    )
    per_course = []
    for r in per_course_raw:
        avg = round(float(r["avg"] or 0.0), 1)
        rate = 0
        if r["learners"]:
            rate = int(round((r["completed"] / r["learners"]) * 100))
        per_course.append(
            {
                "course_id": r["course_id"],
                "course_title": r["course__title"],
                "learners": r["learners"],
                "avg_progress": avg,
                "completed": r["completed"],
                "completion_rate": rate,
            }
        )

    # Por usuario
    per_user_raw = (
        enroll_qs.values("user__id", "user__username", "user__first_name", "user__last_name")
        .annotate(
            enrolls=Count("id"),
            avg=Avg("progress"),
            completed=Count("id", filter=Q(progress__gte=100)),
        )
        .order_by("user__username")
    )
    per_user = []
    for r in per_user_raw:
        per_user.append(
            {
                "user_id": r["user__id"],
                "username": r["user__username"],
                "full_name": (f'{r["user__first_name"]} {r["user__last_name"]}').strip(),
                "enrolls": r["enrolls"],
                "avg_progress": round(float(r["avg"] or 0.0), 1),
                "completed": r["completed"],
            }
        )

    departments = Department.objects.order_by("name")

    return render(
        request,
        "team.html",
        {
            "users": qs,
            "department": dept,
            "departments": departments,
            "is_admin": _is_admin(request.user),
            # Métricas agregadas
            "total_users": total_users,
            "total_enrolls": total_enrolls,
            "completed_enrolls": completed_enrolls,
            "avg_progress": avg_progress,
            "users_without_enrolls": users_without_enrolls,
            "distinct_courses": distinct_courses,
            "per_course": per_course,
            "per_user": per_user,
        },
    )


# ---------- Learner: mis cursos ----------
@login_required
def my_courses(request):
    qs = (
        Enrollment.objects.select_related("course")
        .filter(user=request.user)
        .order_by("course__title")
    )
    return render(request, "my_courses.html", {"enrollments": qs})
