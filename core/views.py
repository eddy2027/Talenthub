# core/views.py
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Q, Avg, Count
from django.utils import timezone

from .models import (
    Department, Profile, Course, Enrollment, CourseMaterial, MaterialProgress,
    QuizAttempt,  # <-- añadido para la sección de quizzes en course_view
)
from .forms import CourseMaterialForm

import os
import pandas as pd
from io import BytesIO


# -----------------------------------
# Helpers de rol (locales a esta app)
# -----------------------------------
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


# -----------------------------
# Dashboard por rol
# -----------------------------
@login_required
def dashboard(request):
    """
    Dashboard por rol:
      - Learner: KPIs personales + Mis Cursos + Sugeridos
      - Manager: KPIs del departamento + tablas por curso/usuario
      - Admin: KPIs globales
    """
    # Rol “efectivo” (superuser trata como Admin)
    if request.user.is_superuser:
        role = "ADMIN"
    else:
        role_val = getattr(getattr(request.user, "profile", None), "role", Profile.ROLE_LEARNER)
        role = "ADMIN" if role_val == Profile.ROLE_ADMIN else ("MANAGER" if role_val == Profile.ROLE_MANAGER else "LEARNER")

    # ===== Learner =====
    if role == "LEARNER":
        my_enrolls = (
            Enrollment.objects.select_related("course")
            .filter(user=request.user)
            .order_by("course__title")
        )
        total = my_enrolls.count()
        completed = my_enrolls.filter(progress__gte=100).count()
        in_progress = my_enrolls.filter(progress__gt=0, progress__lt=100).count()
        avg_progress = my_enrolls.aggregate(v=Avg("progress"))["v"] or 0.0
        avg_progress = round(float(avg_progress), 1)

        # Sugerencias: cursos en los que NO está inscrito
        suggestions = Course.objects.exclude(
            id__in=my_enrolls.values_list("course_id", flat=True)
        ).order_by("-created_at")[:6]

        return render(
            request,
            "dashboard.html",
            {
                "role": "LEARNER",
                "my_enrolls": my_enrolls,
                "kpi_total": total,
                "kpi_completed": completed,
                "kpi_in_progress": in_progress,
                "kpi_avg": avg_progress,
                "suggestions": suggestions,
            },
        )

    # ===== Manager =====
    if role == "MANAGER":
        profile = getattr(request.user, "profile", None)
        dept = getattr(profile, "department", None)

        users_qs = User.objects.select_related("profile")
        if dept:
            users_qs = users_qs.filter(profile__department=dept)
        else:
            users_qs = users_qs.none()

        enroll_qs = (
            Enrollment.objects.select_related("user", "course")
            .filter(user__in=users_qs)
        )

        k_people = users_qs.count()
        k_total_enrolls = enroll_qs.count()
        k_completed_enrolls = enroll_qs.filter(progress__gte=100).count()
        k_avg_progress = round(float(enroll_qs.aggregate(v=Avg("progress"))["v"] or 0.0), 1)
        k_courses_with_enrolls = enroll_qs.values("course_id").distinct().count()

        # Por curso (hasta 8 filas para vista compacta)
        per_course_raw = (
            enroll_qs.values("course_id", "course__title")
            .annotate(
                learners=Count("id"),
                avg=Avg("progress"),
                completed=Count("id", filter=Q(progress__gte=100)),
            )
            .order_by("course__title")[:8]
        )
        per_course = []
        for r in per_course_raw:
            learners = r["learners"] or 0
            completed = r["completed"] or 0
            rate = int(round((completed / learners) * 100)) if learners else 0
            per_course.append(
                {
                    "course_title": r["course__title"],
                    "learners": learners,
                    "avg_progress": round(float(r["avg"] or 0.0), 1),
                    "completed": completed,
                    "completion_rate": rate,
                }
            )

        # Por usuario (hasta 8 filas)
        per_user_raw = (
            enroll_qs.values("user__id", "user__username", "user__first_name", "user__last_name")
            .annotate(
                enrolls=Count("id"),
                avg=Avg("progress"),
                completed=Count("id", filter=Q(progress__gte=100)),
            )
            .order_by("user__username")[:8]
        )
        per_user = []
        for r in per_user_raw:
            full_name = (f'{r["user__first_name"]} {r["user__last_name"]}').strip()
            per_user.append(
                {
                    "username": r["user__username"],
                    "full_name": full_name,
                    "enrolls": r["enrolls"],
                    "avg_progress": round(float(r["avg"] or 0.0), 1),
                    "completed": r["completed"],
                }
            )

        return render(
            request,
            "dashboard.html",
            {
                "role": "MANAGER",
                "dept": dept,
                "k_people": k_people,
                "k_total_enrolls": k_total_enrolls,
                "k_completed_enrolls": k_completed_enrolls,
                "k_avg_progress": k_avg_progress,
                "k_courses_with_enrolls": k_courses_with_enrolls,
                "per_course": per_course,
                "per_user": per_user,
            },
        )

    # ===== Admin =====
    k_users = User.objects.count()
    k_courses = Course.objects.count()
    enrolls_qs = Enrollment.objects.all()
    k_enrolls = enrolls_qs.count()
    k_avg_progress = round(float(enrolls_qs.aggregate(v=Avg("progress"))["v"] or 0.0), 1)

    return render(
        request,
        "dashboard.html",
        {
            "role": "ADMIN",
            "k_users": k_users,
            "k_courses": k_courses,
            "k_enrolls": k_enrolls,
            "k_avg_progress": k_avg_progress,
        },
    )


# -----------------------------
# Users
# -----------------------------
@login_required
def user_list(request):
    q = (request.GET.get("q") or "").strip()
    dept = (request.GET.get("dept") or "").strip()

    users = User.objects.select_related("profile").all().order_by("username")

    if q:
        users = users.filter(
            Q(username__icontains=q)
            | Q(email__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(profile__phone__icontains=q)
            | Q(profile__position__icontains=q)
        )

    if dept:
        users = users.filter(profile__department__name=dept)

    paginator = Paginator(users, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    departments = Department.objects.order_by("name")

    return render(
        request,
        "users.html",
        {
            "users": page_obj.object_list,
            "page_obj": page_obj,
            "q": q,
            "dept": dept,
            "departments": departments,
            "role_choices": Profile.ROLE_CHOICES,
        },
    )


@login_required
def user_create(request):
    if request.method == "POST":
        full_name = (request.POST.get("full_name") or "").strip()
        email = (request.POST.get("email") or "").strip().lower()
        phone = (request.POST.get("phone") or "").strip()
        age = request.POST.get("age")
        sex = (request.POST.get("sex") or "").strip().upper()[:1]
        position = (request.POST.get("position") or "").strip()

        dep_id = request.POST.get("department_id")
        dep_name = (request.POST.get("department") or "").strip()
        role = (request.POST.get("role") or Profile.ROLE_LEARNER).strip()

        if not email:
            messages.error(request, "Email is required.")
            return redirect("user_create")
        username = email.split("@")[0][:150]

        first = full_name.split(" ")[0] if full_name else ""
        last = " ".join(full_name.split(" ")[1:]) if full_name else ""

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return redirect("user_create")

        user = User.objects.create_user(
            username=username,
            email=email,
            first_name=first,
            last_name=last,
            password=User.objects.make_random_password(),
        )

        dept = None
        if dep_id:
            try:
                dept = Department.objects.get(pk=int(dep_id))
            except Exception:
                dept = None
        elif dep_name:
            dept, _ = Department.objects.get_or_create(name=dep_name)

        p = Profile.objects.create(
            user=user,
            phone=phone,
            position=position,
            department=dept,
            role=role if role in [c[0] for c in Profile.ROLE_CHOICES] else Profile.ROLE_LEARNER,
        )
        if age:
            try:
                p.age = int(age)
            except Exception:
                pass
        if sex in ["M", "F", "O"]:
            p.sex = sex
        p.save()

        messages.success(request, "User created.")
        return redirect("user_list")

    departments = Department.objects.order_by("name")
    return render(
        request,
        "user_create.html",
        {
            "departments": departments,
            "sex_choices": Profile.SEX_CHOICES,
            "role_choices": Profile.ROLE_CHOICES,
        },
    )


@login_required
def user_edit(request, user_id):
    u = get_object_or_404(User, pk=user_id)
    profile, _ = Profile.objects.get_or_create(user=u)

    if request.method == "POST":
        full_name = (request.POST.get("full_name") or "").strip()
        email = (request.POST.get("email") or "").strip().lower()
        phone = (request.POST.get("phone") or "").strip()
        age = request.POST.get("age")
        sex = (request.POST.get("sex") or "").strip().upper()[:1]
        position = (request.POST.get("position") or "").strip()

        dep_id = request.POST.get("department_id")
        dep_name = (request.POST.get("department") or "").strip()
        role = (request.POST.get("role") or profile.role).strip()

        if full_name:
            u.first_name = full_name.split(" ")[0]
            u.last_name = " ".join(full_name.split(" ")[1:])
        if email:
            u.email = email
        u.save()

        profile.phone = phone
        profile.position = position

        if age:
            try:
                profile.age = int(age)
            except Exception:
                pass

        if sex in ["M", "F", "O"]:
            profile.sex = sex

        dept = None
        if dep_id:
            try:
                dept = Department.objects.get(pk=int(dep_id))
            except Exception:
                dept = None
        elif dep_name:
            dept, _ = Department.objects.get_or_create(name=dep_name)
        profile.department = dept

        if role in [c[0] for c in Profile.ROLE_CHOICES]:
            profile.role = role

        profile.save()

        messages.success(request, "User updated.")
        return redirect("user_list")

    departments = Department.objects.order_by("name")
    return render(
        request,
        "user_edit.html",
        {
            "u": u,
            "profile": profile,
            "departments": departments,
            "sex_choices": Profile.SEX_CHOICES,
            "role_choices": Profile.ROLE_CHOICES,
        },
    )


@login_required
def user_delete(request, user_id):
    u = get_object_or_404(User, pk=user_id)
    if request.method == "POST":
        u.delete()
        messages.success(request, "User deleted.")
        return redirect("user_list")
    return redirect("user_list")


# -----------------------------
# Import/Export Users
# -----------------------------
@login_required
def import_users(request):
    if request.method == "POST" and request.FILES.get("file"):
        try:
            df = pd.read_excel(request.FILES["file"])
        except Exception as e:
            messages.error(request, f"Could not read file: {e}")
            return redirect("import_users")

        required = ["full_name", "email", "phone", "age", "sex", "department", "position"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            messages.error(request, f"Missing columns: {', '.join(missing)}")
            return redirect("import_users")

        created, updated = 0, 0
        for _, row in df.iterrows():
            email = str(row.get("email") or "").strip().lower()
            if not email:
                continue
            username = email.split("@")[0][:150]
            full_name = str(row.get("full_name") or "").strip()
            first = full_name.split(" ")[0] if full_name else ""
            last = " ".join(full_name.split(" ")[1:]) if full_name else ""

            user, was_created = User.objects.get_or_create(
                username=username,
                defaults={"email": email, "first_name": first, "last_name": last},
            )
            if was_created:
                created += 1
            else:
                user.email = email or user.email
                if first:
                    user.first_name = first
                if last:
                    user.last_name = last
                user.save()
                updated += 1

            dep_name = str(row.get("department") or "").strip()
            dept = None
            if dep_name:
                dept, _ = Department.objects.get_or_create(name=dep_name)

            profile, _ = Profile.objects.get_or_create(user=user)
            profile.phone = str(row.get("phone") or "").strip()
            profile.position = str(row.get("position") or "").strip()
            age_val = row.get("age")
            profile.age = int(age_val) if pd.notna(age_val) else None
            sex_val = str(row.get("sex") or "").upper()[:1]
            if sex_val in ["M", "F", "O"]:
                profile.sex = sex_val
            profile.department = dept
            profile.save()

        messages.success(request, f"Import OK — Created: {created}, Updated: {updated}.")
        return redirect("import_users")

    return render(request, "import_users.html")


@login_required
def export_users(request):
    rows = []
    qs = Profile.objects.select_related("user", "department").all()
    for p in qs:
        rows.append(
            {
                "full_name": (f"{p.user.first_name} {p.user.last_name}").strip() or p.user.username,
                "username": p.user.username,
                "email": p.user.email,
                "phone": p.phone,
                "position": p.position,
                "age": p.age,
                "sex": p.sex,
                "department": p.department.name if p.department else "",
                "role": p.role,
            }
        )
    df = pd.DataFrame(rows)
    with BytesIO() as bio:
        with pd.ExcelWriter(bio, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Users")
        bio.seek(0)
        resp = HttpResponse(
            bio.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = 'attachment; filename="users_export.xlsx"'
        return resp


# -----------------------------
# Courses (UI admin)
# -----------------------------
@login_required
def courses_list(request):
    q = (request.GET.get("q") or "").strip()
    qs = Course.objects.all().order_by("title")
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(instructor__icontains=q))
    return render(request, "courses_list.html", {"courses": qs, "q": q})


@login_required
def course_create(request):
    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        instructor = (request.POST.get("instructor") or "").strip()
        duration = request.POST.get("duration_minutes")
        delivered = bool(request.POST.get("delivered_by_external"))

        if not title:
            messages.error(request, "Title is required.")
            return redirect("course_create")

        Course.objects.create(
            title=title,
            instructor=instructor,
            duration_minutes=int(duration) if duration else None,
            delivered_by_external=delivered,
        )
        messages.success(request, "Course created.")
        return redirect("courses_list")

    return render(request, "course_form.html", {"form_title": "New Course"})


@login_required
def course_edit(request, course_id):
    c = get_object_or_404(Course, pk=course_id)
    if request.method == "POST":
        c.title = (request.POST.get("title") or "").strip()
        c.instructor = (request.POST.get("instructor") or "").strip()
        duration = request.POST.get("duration_minutes")
        c.duration_minutes = int(duration) if duration else None
        c.delivered_by_external = bool(request.POST.get("delivered_by_external"))
        c.save()
        messages.success(request, "Course updated.")
        return redirect("courses_list")

    return render(request, "course_form.html", {"course": c, "form_title": "Edit Course"})


@login_required
def course_delete(request, course_id):
    c = get_object_or_404(Course, pk=course_id)
    if request.method == "POST":
        c.delete()
        messages.success(request, "Course deleted.")
        return redirect("courses_list")
    return redirect("courses_list")


# -----------------------------
# Course Materials (UI admin)
# -----------------------------
@login_required
def course_materials(request, course_id):
    course = get_object_or_404(Course, pk=course_id)

    if request.method == "POST":
        form = CourseMaterialForm(request.POST, request.FILES)
        if form.is_valid():
            material = form.save(commit=False)
            material.course = course
            material.uploaded_by = request.user

            uploaded = request.FILES.get("file")
            if uploaded and not (material.title and material.title.strip()):
                base, _ = os.path.splitext(uploaded.name)
                material.title = base[:200]

            material.save()
            messages.success(request, "Material saved.")
            return redirect("course_materials", course_id=course.id)
        else:
            messages.error(request, "Please complete the form correctly.")
    else:
        form = CourseMaterialForm()

    materials = CourseMaterial.objects.filter(course=course).order_by("-uploaded_at")
    return render(
        request,
        "course_materials.html",
        {"course": course, "materials": materials, "form": form},
    )


@login_required
def material_delete(request, course_id, material_id):
    course = get_object_or_404(Course, pk=course_id)
    m = get_object_or_404(CourseMaterial, pk=material_id, course=course)
    if request.method == "POST":
        if m.file:
            m.file.delete(save=False)
        m.delete()
        messages.success(request, "File deleted.")
        return redirect("course_materials", course_id=course.id)
    return redirect("course_materials", course_id=course.id)


# -----------------------------
# Enrollments / Reports
# -----------------------------
@login_required
def enrollments_list(request):
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()

    qs = Enrollment.objects.select_related("user", "course").all()

    if q:
        qs = qs.filter(
            Q(user__first_name__icontains=q)
            | Q(user__last_name__icontains=q)
            | Q(user__username__icontains=q)
            | Q(user__email__icontains=q)
            | Q(course__title__icontains=q)
            | Q(course__instructor__icontains=q)
        )

    if status == "completed":
        qs = qs.filter(progress__gte=100)
    elif status == "in_progress":
        qs = qs.filter(progress__lt=100)

    return render(request, "enrollments_list.html", {"enrollments": qs})


@login_required
def enrollment_create(request):
    if request.method == "POST":
        user_id = request.POST.get("user_id")
        course_id = request.POST.get("course_id")
        progress = request.POST.get("progress")

        user = get_object_or_404(User, pk=user_id)
        course = get_object_or_404(Course, pk=course_id)

        e = Enrollment.objects.create(
            user=user,
            course=course,
            enrolled_at=timezone.now(),
            progress=int(progress) if progress else 0,
        )
        if e.progress >= 100 and not e.completed_at:
            e.completed_at = timezone.now()
            e.save(update_fields=["completed_at"])

        messages.success(request, "Enrollment created.")
        return redirect("enrollments_list")

    users = User.objects.order_by("username")
    courses = Course.objects.order_by("title")
    return render(request, "enrollment_form.html", {"users": users, "courses": courses})


@login_required
def enrollment_delete(request, enrollment_id):
    e = get_object_or_404(Enrollment, pk=enrollment_id)
    if request.method == "POST":
        e.delete()
        messages.success(request, "Enrollment deleted.")
        return redirect("enrollments_list")
    return redirect("enrollments_list")


# -----------------------------
# Export Progress (Excel)
# -----------------------------
@login_required
def export_progress(request):
    rows = []
    qs = Enrollment.objects.select_related("user", "course").all()
    for en in qs:
        rows.append(
            {
                "learner": (f"{en.user.first_name} {en.user.last_name}").strip()
                or en.user.username,
                "email": en.user.email,
                "course": en.course.title,
                "instructor": en.course.instructor,
                "duration_min": en.course.duration_minutes or "",
                "external": "Yes" if en.course.delivered_by_external else "No",
                "enrolled_at": en.enrolled_at,
                "progress": en.progress if en.progress is not None else 0,
                "completed_at": en.completed_at,
            }
        )

    df = pd.DataFrame(rows)
    with BytesIO() as bio:
        with pd.ExcelWriter(bio, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Progress")
        bio.seek(0)
        resp = HttpResponse(
            bio.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = 'attachment; filename="enrollments_progress.xlsx"'
        return resp


# =============================
#     LEARNER (catalog & view)
# =============================
@login_required
def catalog(request):
    courses = list(Course.objects.all().order_by("title"))
    return render(request, "catalog.html", {"courses": courses})


@login_required
def course_view(request, course_id):
    """
    Vista unificada del curso: Materials + Quizzes (con intentos, último resultado e historial).
    """
    course = get_object_or_404(Course, pk=course_id)

    # ---------- Materials + progreso ----------
    materials = list(CourseMaterial.objects.filter(course=course).order_by("uploaded_at"))
    prog_qs = MaterialProgress.objects.filter(user=request.user, material__in=materials)
    prog_map = {p.material_id: p for p in prog_qs}

    completed = 0
    for m in materials:
        # display_name seguro
        try:
            dn = getattr(m, "display_name", None)
        except Exception:
            dn = None
        m.display_name = dn or m.name or (m.title or m.original_name or "Material")

        mp = prog_map.get(m.id)
        m.is_done = bool(mp and (mp.is_completed or mp.percent == 100))
        if m.is_done:
            completed += 1

    total = len(materials)
    percent = int(round((completed * 100 / total))) if total else 0

    # ---------- Quizzes (activos del curso) ----------
    quizzes = list(course.quizzes.filter(active=True).order_by("id"))
    for q in quizzes:
        used = QuizAttempt.objects.filter(quiz=q, user=request.user).count()
        allowed = q.attempts_allowed or 1
        q.used_attempts = used
        q.allowed_attempts = allowed
        q.attempts_left = max(0, allowed - used)

        q.recent_attempts = list(
            QuizAttempt.objects.filter(quiz=q, user=request.user).order_by("-id")[:5]
        )
        if q.recent_attempts:
            q.last_score = q.recent_attempts[0].score
            q.last_passed = q.recent_attempts[0].passed
        else:
            q.last_score = None
            q.last_passed = None

    return render(
        request,
        "course_view.html",
        {
            "course": course,
            "materials": materials,
            "completed_count": completed,
            "total_count": total,
            "percent": percent,
            "quizzes": quizzes,  # <-- nuevo bloque para la plantilla integrada
        },
    )


# =============================
#   BULK ENROLL (por departamento)
# =============================
@login_required
def course_bulk_enroll(request, course_id):
    """
    Inscribe a todos los usuarios de un departamento en el curso indicado.
    - Admin: puede elegir cualquier departamento.
    - Manager: solo puede usar su propio departamento.
    - Evita duplicados (usa get_or_create).
    """
    course = get_object_or_404(Course, pk=course_id)

    # Departamentos para el form
    departments = Department.objects.order_by("name")
    my_profile = getattr(request.user, "profile", None)
    my_dept = getattr(my_profile, "department", None)

    # Restricciones por rol
    is_admin = _is_admin(request.user)
    is_mgr = _is_manager(request.user)

    if request.method == "POST":
        dep_id = request.POST.get("department_id")
        include_already = bool(request.POST.get("include_already"))  # (reservado para futuro)
        initial_progress = request.POST.get("initial_progress")
        try:
            initial_progress = int(initial_progress)
        except Exception:
            initial_progress = 0
        if initial_progress < 0:
            initial_progress = 0
        if initial_progress > 100:
            initial_progress = 100

        # Determinar departamento a usar
        dept = None
        if dep_id:
            try:
                dept = Department.objects.get(pk=int(dep_id))
            except Exception:
                dept = None

        # Si es manager y selecciona otro departamento, no permitido
        if is_mgr and not is_admin:
            if not my_dept or not dept or (dept.id != my_dept.id):
                messages.error(request, "Managers can only bulk enroll their own department.")
                return redirect("course_bulk_enroll", course_id=course.id)

        if not dept:
            messages.error(request, "Please select a department.")
            return redirect("course_bulk_enroll", course_id=course.id)

        # Usuarios a inscribir
        users_qs = User.objects.select_related("profile").filter(profile__department=dept)

        created = 0
        skipped = 0
        now = timezone.now()
        for u in users_qs:
            # Evita duplicados
            obj, was_created = Enrollment.objects.get_or_create(
                user=u, course=course,
                defaults={"enrolled_at": now, "progress": initial_progress}
            )
            if was_created:
                created += 1
                # Si initial_progress >= 100, marca completed_at
                if initial_progress >= 100:
                    obj.completed_at = now
                    obj.save(update_fields=["completed_at"])
            else:
                skipped += 1

        messages.success(
            request,
            f"Bulk enroll OK — Department: {dept.name} | Created: {created}, Skipped(existing): {skipped}."
        )
        return redirect("enrollments_list")

    # GET → renderizar formulario
    # Si es manager (no admin), el select se limita a su propio departamento
    if is_mgr and not is_admin:
        departments = Department.objects.filter(pk=my_dept.id) if my_dept else Department.objects.none()

    return render(
        request,
        "course_bulk_enroll.html",
        {
            "course": course,
            "departments": departments,
            "is_admin": is_admin,
            "is_manager": is_mgr,
            "my_department": my_dept,
        },
    )
