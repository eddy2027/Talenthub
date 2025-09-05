# core/services/quiz.py
from django.utils import timezone
from ..models import QuizAttempt, QuizAnswer, Enrollment

def grade_attempt(attempt: QuizAttempt):
    """
    Califica un intento.
    - MULTIPLE / TRUE_FALSE: suma puntos si la opción es correcta.
    - SHORT_TEXT: no se califica (0) en el MVP.
    """
    quiz = attempt.quiz
    questions = list(quiz.questions.all())
    total_points = sum(q.points for q in questions) or 1

    # Pre-cargar respuestas con relaciones para eficiencia
    answers = QuizAnswer.objects.select_related("question", "selected_choice").filter(attempt=attempt)

    obtained = 0
    for ans in answers:
        q = ans.question
        if q.question_type in (q.Kind.MULTIPLE, q.Kind.TRUE_FALSE):
            if ans.selected_choice and ans.selected_choice.is_correct:
                obtained += q.points
        # SHORT_TEXT se deja en 0 para calificación manual futura

    score_pct = round(100 * obtained / total_points, 2)
    attempt.score = score_pct
    attempt.passed = score_pct >= quiz.pass_score
    attempt.finished_at = timezone.now()
    attempt.save(update_fields=["score", "passed", "finished_at"])

    # Si pasó, marca la matrícula como completada
    try:
        enr = Enrollment.objects.get(user=attempt.user, course=quiz.course)
    except Enrollment.DoesNotExist:
        return attempt

    if attempt.passed:
        enr.mark_completed()
    return attempt
