# eddylms/urls.py — rutas estables + bulk enroll + quizzes + quiz builder
from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static

# Vistas existentes en core/views.py
from core.views import (
    # Home / dashboard
    dashboard,

    # Users
    user_list, user_create, user_edit, user_delete,
    import_users, export_users,

    # Courses (admin UI)
    courses_list, course_create, course_edit, course_delete,

    # Course materials
    course_materials, material_delete,

    # Enrollments / Reports
    enrollments_list, enrollment_create, enrollment_delete,

    # Export progress
    export_progress,

    # Learner-facing básicos
    catalog, course_view,

    # NUEVA: Bulk enroll
    course_bulk_enroll,
)

# Vistas nuevas en core/extra_views.py
from core.extra_views import (
    my_courses,
    team,
    impersonate_start,
    impersonate_stop,
)

# Abrir materiales
from core.views_material_watch import material_watch

# Quizzes (frontend)
from core.views_quiz import quiz_list_for_course, quiz_take, quiz_result

# >>> NUEVO: Quiz builder (crear quiz y preguntas desde la web + gestor)
from core.views_quiz_builder import (
    quiz_create,
    quiz_add_question,
    question_list,       # <-- añadido
    question_delete,     # <-- añadido
    question_edit,
)

urlpatterns = [
    path('admin/', admin.site.urls),

    # Home / dashboard
    path('', dashboard, name='dashboard'),

    # Auth
    path('accounts/login/',
         auth_views.LoginView.as_view(template_name='registration/login.html'),
         name='login'),
    path('accounts/logout/',
         auth_views.LogoutView.as_view(),
         name='logout'),

    # Users
    path('users/', user_list, name='user_list'),
    path('users/create/', user_create, name='user_create'),
    path('users/<int:user_id>/edit/', user_edit, name='user_edit'),
    path('users/<int:user_id>/delete/', user_delete, name='user_delete'),
    path('import-users/', import_users, name='import_users'),
    path('export-users/', export_users, name='export_users'),

    # Courses (admin UI)
    path('courses/', courses_list, name='courses_list'),
    path('courses/create/', course_create, name='course_create'),
    path('courses/<int:course_id>/edit/', course_edit, name='course_edit'),
    path('courses/<int:course_id>/delete/', course_delete, name='course_delete'),

    # Course materials (upload/list/delete)
    path('courses/<int:course_id>/materials/', course_materials, name='course_materials'),
    path('courses/<int:course_id>/materials/<int:material_id>/delete/', material_delete, name='material_delete'),

    # Enrollments / Reports
    path('enrollments/', enrollments_list, name='enrollments_list'),
    path('enrollments/create/', enrollment_create, name='enrollment_create'),
    path('enrollments/<int:enrollment_id>/delete/', enrollment_delete, name='enrollment_delete'),

    # Export progress
    path('export-progress/', export_progress, name='export_progress'),

    # Learner-facing
    path('catalog/', catalog, name='catalog'),
    path('course/<int:course_id>/', course_view, name='course_view'),
    path('my-courses/', my_courses, name='my_courses'),

    # Manager
    path('team/', team, name='team'),

    # Impersonation
    path('impersonate/<int:user_id>/', impersonate_start, name='impersonate_start'),
    path('impersonate/stop/', impersonate_stop, name='impersonate_stop'),

    # Bulk enroll
    path('courses/<int:course_id>/bulk-enroll/', course_bulk_enroll, name='course_bulk_enroll'),

    # Abrir material (file/link)
    path('material/<int:material_id>/', material_watch, name='material_watch'),

    # Quizzes (frontend)
    path('course/<int:course_id>/quizzes/', quiz_list_for_course, name='quiz_list_for_course'),
    path('quiz/<int:quiz_id>/take/', quiz_take, name='quiz_take'),
    path('quiz/<int:quiz_id>/result/<int:attempt_id>/', quiz_result, name='quiz_result'),

    # >>> NUEVO: Quiz builder
    path('course/<int:course_id>/quizzes/new/', quiz_create, name='quiz_create'),
    path('quiz/<int:quiz_id>/add-question/', quiz_add_question, name='quiz_add_question'),
    path('question/<int:question_id>/edit/', question_edit, name='question_edit'),

    # >>> NUEVO: Gestor de preguntas (solo staff, se accede desde Quizzes ?manage=1)
    path('quiz/<int:quiz_id>/questions/', question_list, name='question_list'),
    path('question/<int:question_id>/delete/', question_delete, name='question_delete'),
    path('question/<int:question_id>/edit/', question_edit, name='question_edit'),
]

# Media en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
