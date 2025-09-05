# core/views_quiz_builder.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.urls import reverse

from .models import Course, Quiz, Question, Choice, QuizAnswer
from .forms import QuizCreateForm, QuestionCreateForm


@login_required
def quiz_create(request, course_id: int):
    """Paso 1: crear el quiz para un curso."""
    course = get_object_or_404(Course, pk=course_id)

    if request.method == "POST":
        form = QuizCreateForm(request.POST)
        if form.is_valid():
            quiz = form.save(commit=False)
            quiz.course = course
            quiz.save()
            messages.success(request, f'Quiz "{quiz.title}" creado. Ahora agrega preguntas.')
            return redirect(reverse("quiz_add_question", args=[quiz.id]))
    else:
        form = QuizCreateForm(initial={"active": True, "attempts_allowed": 1, "pass_score": 70})

    return render(request, "quiz_create.html", {"course": course, "form": form})


@login_required
def quiz_add_question(request, quiz_id: int):
    """Paso 2: agregar preguntas (puedes guardar y seguir agregando)."""
    quiz = get_object_or_404(Quiz, pk=quiz_id)

    if request.method == "POST":
        form = QuestionCreateForm(request.POST)
        if form.is_valid():
            qtype = form.cleaned_data["question_type"]
            text = form.cleaned_data["text"]
            points = form.cleaned_data["points"]

            # Crear la pregunta
            question = Question.objects.create(
                quiz=quiz, text=text, question_type=qtype, points=points
            )

            # Opciones según tipo
            if qtype == Question.Kind.MULTIPLE:
                choices_txt = [
                    form.cleaned_data.get("choice1"),
                    form.cleaned_data.get("choice2"),
                    form.cleaned_data.get("choice3"),
                    form.cleaned_data.get("choice4"),
                ]
                correct_idx = int(form.cleaned_data["correct_choice"]) - 1
                for idx, txt in enumerate(choices_txt):
                    txt = (txt or "").strip()
                    if not txt:
                        continue
                    Choice.objects.create(
                        question=question,
                        text=txt,
                        is_correct=(idx == correct_idx),
                    )

            elif qtype == Question.Kind.TRUE_FALSE:
                true_is_correct = bool(form.cleaned_data.get("true_is_correct"))
                Choice.objects.bulk_create([
                    Choice(question=question, text="True",  is_correct=true_is_correct),
                    Choice(question=question, text="False", is_correct=not true_is_correct),
                ])

            # SHORT_TEXT no crea choices (corrección manual futura)

            messages.success(request, "Pregunta agregada.")
            # ¿Seguir agregando o terminar?
            if "add_more" in request.POST:
                return redirect(reverse("quiz_add_question", args=[quiz.id]))
            return redirect(reverse("quiz_list_for_course", args=[quiz.course.id]) + "?manage=1")
    else:
        form = QuestionCreateForm()

    return render(request, "quiz_add_question.html", {"quiz": quiz, "form": form})


# ===== NUEVO: gestor de preguntas (solo staff) =====

@login_required
def question_list(request, quiz_id: int):
    """Lista de preguntas y respuestas (solo staff, desde modo gestión)."""
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    if not request.user.is_staff:
        messages.error(request, "Not allowed.")
        return redirect("quiz_list_for_course", course_id=quiz.course.id)

    questions = quiz.questions.all().prefetch_related("choices").order_by("id")
    return render(request, "question_list.html", {"quiz": quiz, "questions": questions})


@login_required
def question_delete(request, question_id: int):
    """Borra la pregunta si no tiene respuestas en intentos (seguro)."""
    question = get_object_or_404(Question, pk=question_id)
    quiz = question.quiz

    if not request.user.is_staff:
        messages.error(request, "Not allowed.")
        return redirect("quiz_list_for_course", course_id=quiz.course.id)

    if request.method == "POST":
        has_answers = QuizAnswer.objects.filter(question=question).exists()
        if has_answers:
            messages.error(request, "No puedes borrar esta pregunta: ya tiene intentos/respuestas.")
        else:
            question.delete()
            messages.success(request, "Pregunta borrada.")
        return redirect("question_list", quiz.id)

    return redirect("question_list", quiz.id)

# --- al final de core/views_quiz_builder.py ---
from django.db.models import Exists, OuterRef

@login_required
def question_edit(request, question_id: int):
    """Editar una pregunta. 
    - Solo staff.
    - Si la pregunta ya tiene respuestas (QuizAnswer), se bloquea cambiar opciones/tipo
      y solo se permite editar texto y puntos.
    """
    question = get_object_or_404(Question, pk=question_id)
    quiz = question.quiz
    if not request.user.is_staff:
        messages.error(request, "Not allowed.")
        return redirect("quiz_list_for_course", course_id=quiz.course.id)

    # Hay intentos contestando esta pregunta?
    has_answers = QuizAnswer.objects.filter(question=question).exists()

    if request.method == "POST":
        text = (request.POST.get("text") or "").strip()
        points_raw = request.POST.get("points")
        try:
            points = int(points_raw) if points_raw else question.points
        except Exception:
            points = question.points

        if text:
            question.text = text
        question.points = points
        question.save(update_fields=["text", "points"])

        if not has_answers:
            # Podemos tocar opciones
            if question.question_type == Question.Kind.MULTIPLE:
                # Reemplazamos choices
                question.choices.all().delete()
                choices_txt = [
                    (request.POST.get("choice1") or "").strip(),
                    (request.POST.get("choice2") or "").strip(),
                    (request.POST.get("choice3") or "").strip(),
                    (request.POST.get("choice4") or "").strip(),
                ]
                try:
                    correct_idx = int(request.POST.get("correct_choice") or "1") - 1
                except Exception:
                    correct_idx = 0
                for idx, txt in enumerate(choices_txt):
                    if not txt:
                        continue
                    Choice.objects.create(
                        question=question,
                        text=txt,
                        is_correct=(idx == correct_idx),
                    )
            elif question.question_type == Question.Kind.TRUE_FALSE:
                # Ajustamos cuál es la correcta
                true_is_correct = bool(request.POST.get("true_is_correct"))
                question.choices.all().delete()
                Choice.objects.bulk_create([
                    Choice(question=question, text="True",  is_correct=true_is_correct),
                    Choice(question=question, text="False", is_correct=not true_is_correct),
                ])
            # SHORT_TEXT no tiene choices

        else:
            # Si hay respuestas, no tocamos estructura de opciones
            pass

        messages.success(request, "Question updated.")
        return redirect("question_list", quiz.id)

    # GET → armar iniciales para el template
    initial = {
        "text": question.text,
        "points": question.points,
        "type": question.get_question_type_display(),
        "has_answers": has_answers,
        "kind": question.question_type,
        "choices": list(question.choices.all().values("text", "is_correct")),
    }
    return render(request, "question_edit.html", {"quiz": quiz, "question": question, "initial": initial})
