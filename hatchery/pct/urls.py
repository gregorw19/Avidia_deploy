from django.urls import path
from . import views


urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('home/', views.home_view, name='home'),
    path('profile/', views.profile_view, name='profile'),
    path('manage-users/', views.manage_users_view, name='manage_users'),
    path('ban-error/', views.ban_error_view, name='ban_error'),
    path('role-error/', views.role_error_view, name='role_error'),
    path('auth/google/<str:role>/', views.google_login_with_role, name='google_login_with_role'),
    path('add-certifications/', views.add_certifications, name='add_certifications'),
    path('view-student-profile/<int:user_id>/', views.view_student_profile, name='view_student_profile'),
    path('api/search-certifications/', views.search_certifications_api, name='search_certifications_api'),
    path('api/search-users/', views.search_users_api, name='search_users_api'),
    path('api/create-certification/', views.create_certification_api, name='create_certification_api'),
    path('api/update-certification/<int:cert_id>/', views.update_certification_api, name='update_certification_api'),
    path('api/remove-certification/<int:user_id>/<int:cert_id>/', views.remove_certification_api, name='remove_certification_api'),
    path('reports/', views.reports_view, name='reports'),
    path('submit-report/', views.submit_report_view, name='submit_report'),
    path('admin-log/', views.admin_log_view, name='admin_log'),
    path('reservations/', views.reservations_view, name='reservations'),
    path('api/majors/', views.get_majors_by_school, name='get_majors_by_school'),
    path("trainings/", views.training_list, name="training-list"),
    path("trainings/mine/", views.staff_training_list, name="staff-training-list"),
    path("trainings/new/", views.TrainingCreateView.as_view(), name="training-create"),
    path("trainings/<int:pk>/signup/", views.training_signup, name="training-signup"),
    path("trainings/<int:pk>/cancel/", views.training_cancel, name="training-cancel"),
    path("about/", views.about_view, name="about"),
    path("help/", views.help_view, name="help"),
    path("contact/", views.contact_view, name="contact"),
    path("schedule/", views.schedule_overview, name="schedule"),
    path("schedule/builder/", views.schedule_builder, name="schedule-builder"),
    path("semesters/", views.semester_settings, name="semester-settings"),
    
    #Calendar page
    path('calendar/', views.CalendarView.as_view(), name='calendar'),
    path('calendar/staff/', views.CalendarView.as_view(), {"staff_view": True}, name='staff_calendar'),

    # Events (get/add/update/delete)
    path('calendar/events/', views.EventsView.as_view(), name='events'),

    # Waitlist
    path("training/<int:training_id>/register/", views.RegisterTrainingView.as_view(), name="register_training"),
    path("training/<int:training_id>/cancel/", views.cancel_training, name="cancel_training"),
    path("training/<int:training_id>/confirm/<int:profile_id>/", views.ConfirmTrainingView.as_view(), name="confirm_training"),
    path("trainings/<int:training_id>/waitlist/", views.join_waitlist, name="join_waitlist"),
    path("trainings/<int:training_id>/waitlist/leave/", views.leave_waitlist, name="leave_waitlist"),
    path("waitlist/respond/<int:waitlist_id>/", views.respond_invitation, name="respond_invitation"),
    path("training/<int:training_id>/<int:profile_id>/decline/", views.DeclineTrainingView.as_view(), name="decline_training"),
    path('user-home/', views.user_home, name='user_home'),
]  
