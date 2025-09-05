# core/views_quiz.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseForbidden
from django.urls import reverse

from .models import Quiz, Question, Choice, QuizAttempt, QuizAnswer, Course
from .services.quiz import grade_attempt


@login_required
def quiz_list_for_course(request, course_id: int):
    """Lista de quizzes para un curso (con intentos e historial).
    'manage_mode' se activa con ?manage=1 y solo se usa para admins.
    """
    course = get_object_or_404(Course, pk=course_id)
    quizzes = list(course.quizzes.filter(active=True).order_by("id"))

    for q in quizzes:
        used = QuizAttempt.objects.filter(quiz=q, user=request.user).count()
        allowed = q.attempts_allowed or 1
        q.used_attempts = used
        q.allowed_attempts = allowed
        q.attempts_left = max(0, allowed - used)

        q.recent_attempts = list(
            QuizAttempt.objects.filter(quiz=q, user=request.user)
            .order_by("-id")[:5]
        )
        if q.recent_attempts:
            q.last_score = q.recent_attempts[0].score
            q.last_passed = q.recent_attempts[0].passed
        else:
            q.last_score = None
            q.last_passed = None

    manage_mode = (request.GET.get("manage") == "1")
    ctx = {"course": course, "quizzes": quizzes, "manage_mode": manage_mode}
    return render(request, "quiz_list.html", ctx)


@login_required
def quiz_take(request, quiz_id: int):
    """
    Muestra el formulario del quiz y procesa las respuestas.
    - Crea un QuizAttempt nuevo.
    - Guarda QuizAnswer por cada pregunta enviada.
    - Llama a grade_attempt y redirige a resultados.
    """
    quiz = get_object_or_404(Quiz, pk=quiz_id, active=True)

    # Límite de intentos
    used = QuizAttempt.objects.filter(quiz=quiz, user=request.user).count()
    allowed = quiz.attempts_allowed or 1
    if used >= allowed and request.method == "GET":
        # Página amigable indicando que no quedan intentos
        return render(
            request,
            "quiz_no_attempts.html",
            {"quiz": quiz, "used": used, "allowed": allowed},
            status=403,
        )

    if request.method == "POST":
        # Crear intento
        attempt = QuizAttempt.objects.create(quiz=quiz, user=request.user)

        # Crear respuestas
        questions = quiz.questions.all().prefetch_related("choices")
        for q in questions:
            field = f"q_{q.id}"
            selected_choice = None
            choice_id = request.POST.get(field)
            if choice_id:
                try:
                    selected_choice = Choice.objects.get(pk=int(choice_id), question=q)
                except (Choice.DoesNotExist, ValueError):
                    selected_choice = None
            QuizAnswer.objects.create(
                attempt=attempt,
                question=q,
                selected_choice=selected_choice,
                free_text=request.POST.get(f"t_{q.id}", "")[:500],
            )

        # Calificar y redirigir
        grade_attempt(attempt)
        return redirect(reverse("quiz_result", args=[quiz.id, attempt.id]))

    # GET: renderizar formulario
    questions = quiz.questions.all().prefetch_related("choices")
    ctx = {"quiz": quiz, "questions": questions}
    return render(request, "quiz_take.html", ctx)


@login_required
def quiz_result(request, quiz_id: int, attempt_id: int):
    """Pantalla de resultados del intento + intentos restantes."""
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    attempt = get_object_or_404(QuizAttempt, pk=attempt_id, quiz=quiz, user=request.user)

    used = QuizAttempt.objects.filter(quiz=quiz, user=request.user).count()
    allowed = quiz.attempts_allowed or 1
    attempts_left = max(0, allowed - used)

    ctx = {
        "quiz": quiz,
        "attempt": attempt,
        "used": used,
        "allowed": allowed,
        "attempts_left": attempts_left,
    }
    return render(request, "quiz_result.html", ctx)
