from collections import defaultdict
from datetime import timedelta, datetime, date
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.models import User
from .models import Profile, Certification, CertificationType, CertificationLevel, School, Major, Minor, Training, WorkBlock, RoomReservation, TrainingWaitlist, Report, ActivityLog, Availability, ScheduleWeek, Shift, ShiftSwapRequest, Semester, OpenHour, Holiday
from django.core.exceptions import ValidationError
from .models import Profile, Certification, CertificationType, CertificationLevel, School, Major, Minor, Training, TrainingCancellationRequest, WorkBlock, RoomReservation, Availability, ScheduleWeek, Shift, ShiftSwapRequest, Semester, OpenHour, Holiday
from django.db.models import Q, F
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
import json
from django.http import HttpResponseRedirect, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.urls import reverse_lazy, reverse
from django.views.generic import CreateView
from .forms import (
    TrainingForm,
    RoomReservationForm,
    ReportForm,
    AvailabilityForm,
    ShiftForm,
    SwapRequestForm,
    SemesterForm,
    OpenHourForm,
    HolidayForm,
)
from django.views import View

VALID_ROLES = {"student", "staff", "admin", "team_member"}


def _certificate_level_cache(profile):
    """Return (any_level_set, per_type_level_sets) for quick prerequisite checks."""
    per_type = defaultdict(set)
    any_levels = set()
    for cert_type_id, level_value in profile.certificates.values_list("type_id", "level__level"):
        any_levels.add(level_value)
        if cert_type_id:
            per_type[cert_type_id].add(level_value)
    return any_levels, per_type


def _student_has_prerequisite(profile, training):
    """Return True if the profile qualifies for the given training."""
    level_value = training.level.level
    if level_value <= 1:
        return True

    prereq_level = level_value - 1
    qs = profile.certificates.filter(level__level=prereq_level)
    if training.certification_type_id:
        qs = qs.filter(type_id=training.certification_type_id)
    return qs.exists()


def _format_prereq_label(training, prereq_level):
    if training.certification_type:
        return f"{training.certification_type.name} level {prereq_level}"
    return f"level {prereq_level}"


def _week_start_from_param(param):
    """Parse week_start query param (YYYY-MM-DD) or return current week's Monday."""
    today = timezone.localdate()
    base = today
    if param:
        try:
            base = datetime.strptime(param, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            base = today
    return base - timedelta(days=base.weekday())


def _ensure_schedule_week(week_start: date, creator: Profile | None):
    schedule_week, _ = ScheduleWeek.objects.get_or_create(
        week_start=week_start, defaults={"created_by": creator}
    )
    return schedule_week


def _week_start_for_datetime(dt):
    """Return the Monday date for a given datetime (aware or naive)."""
    if not dt:
        return None
    local_dt = timezone.localtime(dt) if timezone.is_aware(dt) else dt
    base_date = local_dt.date()
    return base_date - timedelta(days=base_date.weekday())


def _schedule_week_for_datetime(dt):
    """Return the schedule week matching the datetime's week (if any)."""
    week_start = _week_start_for_datetime(dt)
    if not week_start:
        return None
    return ScheduleWeek.objects.filter(week_start=week_start).first()


def _active_semester_for_date(target_date: date):
    if not target_date:
        return None
    return Semester.objects.filter(start_date__lte=target_date, end_date__gte=target_date, is_active=True).order_by("-start_date").first()


def _is_holiday(semester: Semester, target_date: date):
    if not semester:
        return False
    return semester.holidays.filter(date=target_date).exists()


def _within_open_hours(semester: Semester, start_dt, end_dt):
    """Check if start/end fall within configured open hours for the weekday."""
    if not semester:
        return True
    weekday = start_dt.weekday()
    hours = semester.open_hours.filter(weekday=weekday)
    if not hours.exists():
        return False
    for window in hours:
        if window.open_time <= start_dt.time() and window.close_time >= end_dt.time():
            return True
    return False


def _invite_next_waitlisted(training):
    """Promote the next waiting user to invited for the given training."""
    next_entry = training.waitlist.filter(status="waiting").order_by("created_at").first()
    if next_entry:
        next_entry.status = "invited"
        next_entry.save(update_fields=["status"])
    return next_entry

def google_login_with_role(request, role: str):
    role = (role or "").lower()
    if role not in VALID_ROLES:
        messages.error(request, "Invalid role. Defaulting to student.")
        role = "student"

    # store chosen role for after OAuth
    request.session["chosen_role"] = role

    # kick off allauth's Google login (same as {% provider_login_url 'google' %})
    return redirect("/accounts/google/login/?process=login")


def login_view(request):
    return render(request, "pct/login.html")

def reports_view(request):
    return render(request, "pct/reports.html")


@login_required
def submit_report_view(request):
    profile, created = Profile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        form = ReportForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.submitted_by = profile
            report.save()
            
            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                action='other',
                description=f'Submitted report: {report.title}'
            )
            
            messages.success(request, 'Report submitted successfully!')
            return redirect('submit_report')
    else:
        form = ReportForm()
    
    # Get user's submitted reports
    my_reports = Report.objects.filter(submitted_by=profile).order_by('-created_at')
    
    context = {
        'form': form,
        'my_reports': my_reports,
    }
    return render(request, 'pct/submit_report.html', context)


@login_required
def admin_log_view(request):
    profile, created = Profile.objects.get_or_create(user=request.user)
    
    if not profile.role == 'admin':
        messages.error(request, 'Access denied. Admin only.')
        return redirect('home')
    
    # Get open reports (not resolved or closed)
    reports = Report.objects.filter(status='open')
    
    # Get recent activity logs
    activity_logs = ActivityLog.objects.all()[:50]  # Last 50 activities
    
    # Handle report actions
    if request.method == 'POST':
        report_id = request.POST.get('report_id')
        action = request.POST.get('action')
        
        try:
            report = Report.objects.get(id=report_id)
            if action == 'resolved':
                report.status = 'resolved'
                report.resolved_by = profile
                report.resolved_at = timezone.now()
                report.save()
                messages.success(request, 'Report marked as resolved.')
            elif action == 'closed':
                # Just close the modal - don't change status
                pass
        except Report.DoesNotExist:
            messages.error(request, 'Report not found.')
        
        return redirect('admin_log')
    
    context = {
        'reports': reports,
        'activity_logs': activity_logs,
    }
    return render(request, 'pct/admin_log.html', context)


def role_error_view(request):
    """Display error page when user tries to login with wrong role"""
    existing_role = request.GET.get('existing_role', 'student')
    attempted_role = request.GET.get('attempted_role', 'unknown')
    
    return render(request, "pct/role_error.html", {
        'existing_role': existing_role,
        'attempted_role': attempted_role
    })


def ban_error_view(request):
    """Display error page when a banned user tries to access the system"""
    ban_type = request.GET.get('ban_type', 'permanent')
    ban_expires_at = request.GET.get('ban_expires_at', None)
    ban_reason = request.GET.get('ban_reason', '')
    
    # Parse ban_expires_at if provided
    from django.utils.dateparse import parse_datetime
    ban_expires_at_parsed = None
    if ban_expires_at:
        ban_expires_at_parsed = parse_datetime(ban_expires_at)
    
    return render(request, "pct/ban_error.html", {
        'ban_type': ban_type,
        'ban_expires_at': ban_expires_at_parsed,
        'ban_reason': ban_reason
    })

@login_required
def home_view(request):
    profile, created = Profile.objects.get_or_create(user=request.user)
    
    # Check if user was banned during login (from signal)
    if 'user_banned' in request.session:
        ban_type = request.session.get('ban_type', 'permanent')
        ban_expires_at_str = request.session.get('ban_expires_at')
        ban_reason = request.session.get('ban_reason', '')
        
        # Clean up session
        del request.session['user_banned']
        del request.session['ban_type']
        if 'ban_expires_at' in request.session:
            del request.session['ban_expires_at']
        if 'ban_reason' in request.session:
            del request.session['ban_reason']
        
        # Logout the user
        logout(request)
        
        # Build redirect URL with ban information
        from urllib.parse import urlencode
        params = {
            'ban_type': ban_type,
            'ban_reason': ban_reason
        }
        if ban_expires_at_str:
            params['ban_expires_at'] = ban_expires_at_str
        
        return redirect(f'/ban-error/?{urlencode(params)}')
    
    # Check if user is banned (for already logged-in users)
    if profile.is_currently_banned():
        ban_type = profile.ban_type or 'permanent'
        ban_expires_at = profile.ban_expires_at
        ban_reason = profile.ban_reason or ''
        
        # Logout the user
        logout(request)
        
        # Build redirect URL with ban information
        from urllib.parse import urlencode
        params = {
            'ban_type': ban_type,
            'ban_reason': ban_reason
        }
        if ban_expires_at:
            params['ban_expires_at'] = ban_expires_at.isoformat()
        
        return redirect(f'/ban-error/?{urlencode(params)}')
    
    # Check if there's a role mismatch (user tried to login with different role)
    if 'role_mismatch' in request.session:
        existing_role = request.session.get('existing_role', profile.role or 'student')
        attempted_role = request.session.get('attempted_role', 'unknown')
        
        # Clean up session
        del request.session['role_mismatch']
        del request.session['existing_role']
        del request.session['attempted_role']
        
        # Redirect to error page with logout
        logout(request)
        return redirect(f'/role-error/?existing_role={existing_role}&attempted_role={attempted_role}')
    
    # Clean up any lingering chosen_role from session
    if 'chosen_role' in request.session:
        del request.session['chosen_role']
    
    role = (profile.role or "student").lower()
    now = timezone.now()

    # Upcoming reservations
    upcoming_room_reservations = (
        profile.room_reservations.filter(end_time__gte=now)
        .select_related("reviewed_by__user")
        .order_by("start_time")
    )

    # Invited trainings for notification banner
    invited_trainings = TrainingWaitlist.objects.filter(profile=profile, status="invited")

    if role == "admin":
        context = {
            "profile": profile,
            "invited_trainings": invited_trainings,
            "upcoming_room_reservations": upcoming_room_reservations,
        }
        return render(request, "pct/admin_home.html", context)

    elif role == "staff":
        student_trainings = (
            Training.objects.filter(student=profile)
            .select_related("staff", "level")
        )
        staff_trainings = (
            Training.objects.filter(staff=profile)
            .select_related("student", "level")
        )
        context = {
            "profile": profile,
            "invited_trainings": invited_trainings,
            "upcoming_trainings": student_trainings.filter(
                Q(time__gte=now) | Q(time__isnull=True)
            ).order_by(F("time").asc(nulls_last=True), "name"),
            "past_trainings": staff_trainings.filter(
                Q(time__gte=now) | Q(time__isnull=True)
            ).order_by(F("time").asc(nulls_last=True), "name"),
            "past_trainings": staff_trainings.filter(time__lt=now).order_by("-time"),
            "upcoming_room_reservations": upcoming_room_reservations,
        }
        return render(request, "pct/staff_home.html", context)

    else:  # student
        student_trainings = (
            Training.objects.filter(student=profile)
            .select_related("staff", "level")
        )
        context = {
            "profile": profile,
            "invited_trainings": invited_trainings,
            "upcoming_trainings": student_trainings.filter(
                Q(time__gte=now) | Q(time__isnull=True)
            ).order_by(F("time").asc(nulls_last=True), "name"),
            "past_trainings": student_trainings.filter(time__lt=now).order_by("-time"),
            "upcoming_room_reservations": upcoming_room_reservations,
        }
        return render(request, "pct/user_home.html", context)


@login_required
def reservations_view(request):
    profile, created = Profile.objects.get_or_create(user=request.user)

    if 'role_mismatch' in request.session:
        existing_role = request.session.get('existing_role', profile.role or 'student')
        attempted_role = request.session.get('attempted_role', 'unknown')
        del request.session['role_mismatch']
        del request.session['existing_role']
        del request.session['attempted_role']
        logout(request)
        return redirect(f'/role-error/?existing_role={existing_role}&attempted_role={attempted_role}')

    if 'chosen_role' in request.session:
        del request.session['chosen_role']

    role = (profile.role or "student").lower()
    room_reservation_form = RoomReservationForm()
    my_room_reservations = (
        profile.room_reservations.all()
        .select_related("reviewed_by__user")
        .order_by("-start_time", "-created_at")
    )
    staff_can_moderate_reservations = role in {"staff", "admin"}
    pending_room_reservations = RoomReservation.objects.none()
    all_room_reservations = RoomReservation.objects.none()
    if staff_can_moderate_reservations:
        pending_room_reservations = (
            RoomReservation.objects.filter(
                status=RoomReservation.StatusChoices.PENDING
            )
            .select_related("requester__user")
            .order_by("start_time")
        )
        all_room_reservations = (
            RoomReservation.objects.select_related("requester__user", "reviewed_by__user")
            .order_by("-start_time", "-created_at")
        )

    if request.method == "POST":
        form_type = request.POST.get("form_type")
        if form_type == "room_request":
            room_reservation_form = RoomReservationForm(request.POST)
            if room_reservation_form.is_valid():
                reservation = room_reservation_form.save(commit=False)
                reservation.requester = profile
                reservation.save()
                messages.success(
                    request,
                    "Room reservation request submitted! The staff will review it shortly.",
                )
                return redirect("reservations")
            messages.error(
                request,
                "Please correct the errors below to submit your room reservation request.",
            )
        elif form_type in {"approve_reservation", "deny_reservation"}:
            if not staff_can_moderate_reservations:
                messages.error(request, "You do not have permission to moderate reservations.")
                return redirect("reservations")

            reservation = get_object_or_404(
                RoomReservation, pk=request.POST.get("reservation_id")
            )
            new_status = (
                RoomReservation.StatusChoices.APPROVED
                if form_type == "approve_reservation"
                else RoomReservation.StatusChoices.DENIED
            )

            if reservation.status == new_status:
                messages.info(request, "This reservation is already up to date.")
                return redirect("reservations")

            reservation.status = new_status
            reservation.reviewed_by = profile
            reservation.reviewed_at = timezone.now()
            reservation.save()
            if new_status == RoomReservation.StatusChoices.APPROVED:
                messages.success(request, "Reservation approved.")
            else:
                messages.success(request, "Reservation denied.")
            return redirect("reservations")

    context = {
        "profile": profile,
        "room_reservation_form": room_reservation_form,
        "my_room_reservations": my_room_reservations,
        "pending_room_reservations": pending_room_reservations,
        "all_room_reservations": all_room_reservations,
        "staff_can_moderate_reservations": staff_can_moderate_reservations,
    }
    return render(request, "pct/reservations.html", context)


def edit_profile(request):
    profile = request.user.profile
    schools = School.objects.all().order_by("school_name")
    minors = Minor.objects.all()
    major1_options = Major.objects.none()
    major2_options = Major.objects.all().order_by("major_name")
    selected_school = None

    if request.method != "POST":
        if profile.major1:
            selected_school = profile.major1.school
            major1_options = Major.objects.filter(school=selected_school)
        elif profile.major2 and profile.major2.school:
            selected_school = profile.major2.school
            major1_options = Major.objects.filter(school=selected_school)

    else:
        selected_school_id = request.POST.get("school")

        if selected_school_id:
            selected_school = School.objects.get(id=selected_school_id)
            major1_options = Major.objects.filter(school=selected_school)

        if "save_profile" in request.POST:
            profile.major1_id = request.POST.get("major1") or None
            profile.major2_id = request.POST.get("major2") or None
            profile.minor1_id = request.POST.get("minor1") or None
            profile.minor2_id = request.POST.get("minor2") or None
            profile.save()
            return redirect("profile")

    return {
        "profile": profile,
        "schools": schools,
        "selected_school": selected_school,
        "major1_options": major1_options,
        "major2_options": major2_options,
        "minors": minors,
    }




@login_required
def profile_view(request):
    profile, created = Profile.objects.get_or_create(user=request.user)
    context = edit_profile(request)

    if isinstance(context, HttpResponseRedirect):
        return context

    context["profile"] = profile
    context["user"] = request.user
    
    """
    Unified profile view that renders role-specific pages:
    - Student: editable email + majors/minors
    - Staff/Admin: editable email only
    """
    
    # Check if there's a role mismatch (user tried to login with different role)
    if 'role_mismatch' in request.session:
        existing_role = request.session.get('existing_role', profile.role or 'student')
        attempted_role = request.session.get('attempted_role', 'unknown')
        
        # Clean up session
        del request.session['role_mismatch']
        del request.session['existing_role']
        del request.session['attempted_role']
        
        # Redirect to error page with logout
        logout(request)
        return redirect(f'/role-error/?existing_role={existing_role}&attempted_role={attempted_role}')
    
    # Clean up any lingering chosen_role from session
    if 'chosen_role' in request.session:
        del request.session['chosen_role']

    # Handle form updates
    if request.method == 'POST':
        # Handle delete account first (before other processing)
        if 'delete_account' in request.POST:
            user = request.user
            logout(request)
            # Delete the profile
            if hasattr(user, 'profile'):
                user.profile.delete()
            # Delete the user
            user.delete()
            messages.success(request, 'Your account has been deleted successfully.')
            return redirect('login')

        # Upload profile picture
        if 'upload_picture' in request.POST and 'profile_picture' in request.FILES:
            profile.profile_picture = request.FILES['profile_picture']
            profile.save()
            messages.success(request, 'Profile picture updated successfully!')

        # Update email (available to everyone)
        elif 'update_email' in request.POST:
            new_email = request.POST.get('email', '').strip()
            if new_email:
                profile.email = new_email
                profile.save()
                messages.success(request, 'Email updated successfully!')

        # Update academic info (students and staff)
        elif 'update_academic_info' in request.POST and profile.role in ('student', 'staff', 'team_member'):
            profile.major1_id = request.POST.get('major1') or None
            profile.major2_id = request.POST.get('major2') or None
            profile.minor1_id = request.POST.get('minor1') or None
            profile.minor2_id = request.POST.get('minor2') or None
            profile.save()
            messages.success(request, 'Academic information updated successfully!')

    # Render based on role
    role = (profile.role or "student").lower()
    
    # Ensure profile email is initialized with user email if empty
    if not profile.email and request.user.email:
        profile.email = request.user.email
        profile.save()

    if role == "admin":
        return render(request, "pct/admin_profile.html", context)
    elif role == "staff":
        return render(request, "pct/staff_profile.html", context)
    else:
        return render(request, "pct/student_profile.html", context)


def get_majors_by_school(request):
    school_id = request.GET.get('school_id')
    majors_qs = Major.objects.all().order_by("major_name")

    if school_id:
        majors_qs = majors_qs.filter(school_id=school_id)

    majors = [{'id': m.id, 'name': m.major_name} for m in majors_qs]
    return JsonResponse({'majors': majors})


@login_required
def manage_users_view(request):
    """View and manage users - Staff can manage students, Admin can manage staff and students"""
    profile, created = Profile.objects.get_or_create(user=request.user)
    
    # Check permissions
    if profile.role not in ['staff', 'team_member', 'admin']:
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('home')
    
    # Get users based on role
    if profile.role in ['staff', 'team_member']:
        target_roles = Profile.USER_ROLES
        users = User.objects.filter(profile__role__in=target_roles).select_related('profile').order_by('username')
    else:  # admin
        target_role = request.GET.get('filter_role', 'all')
        if target_role == 'staff':
            users = User.objects.filter(profile__role='staff').select_related('profile').order_by('username')
        elif target_role == 'student':
            users = User.objects.filter(profile__role='student').select_related('profile').order_by('username')
        elif target_role == 'team_member':
            users = User.objects.filter(profile__role='team_member').select_related('profile').order_by('username')
        else:
            users = User.objects.exclude(profile__role='admin').select_related('profile').order_by('username')
    
    # Handle user updates
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        target_user = get_object_or_404(User, id=user_id)
        target_profile = get_object_or_404(Profile, user=target_user)
        
        # Check if staff is trying to modify non-student
        if profile.role == 'staff' and target_profile.role not in Profile.USER_ROLES:
            messages.error(request, 'You can only modify student or team member accounts.')
            return redirect('manage_users')
        
        # Update role if permitted
        new_role = request.POST.get('role')
        if new_role and new_role in VALID_ROLES:
            # Check if admin is trying to change admin roles
            if profile.role == 'admin' and target_profile.role == 'admin' and new_role != 'admin':
                messages.error(request, 'Cannot modify admin accounts.')
                return redirect('manage_users')
            
            target_profile.role = new_role
            target_profile.save()
            messages.success(request, f'User {target_user.username}\'s role updated to {new_role.title()}.')

        # Toggle team lead flag (only for team members)
        if 'toggle_team_lead' in request.POST:
            if target_profile.role in ['team_member', 'student']:
                target_profile.is_team_lead = request.POST.get('is_team_lead') == '1'
                target_profile.save(update_fields=["is_team_lead"])
                messages.success(request, f"Updated team lead flag for {target_user.username}.")
        
        # Ban user (staff, team_member, admin)
        if 'ban_user' in request.POST and profile.role in ['admin', 'staff', 'team_member']:
            if target_profile.role == 'admin':
                messages.error(request, 'Cannot ban admin accounts.')
            else:
                ban_type = request.POST.get('ban_type')
                ban_reason = request.POST.get('ban_reason', '')
                
                if ban_type == 'permanent':
                    target_profile.is_banned = True
                    target_profile.ban_type = 'permanent'
                    target_profile.ban_expires_at = None
                    target_profile.banned_at = timezone.now()
                    target_profile.ban_reason = ban_reason
                    target_profile.save()
                    messages.success(request, f'User {target_user.username} has been permanently banned.')
                elif ban_type == 'temporary':
                    duration = int(request.POST.get('ban_duration', 1))
                    duration_unit = request.POST.get('ban_duration_unit', 'days')
                    
                    # Calculate expiry time
                    from datetime import timedelta
                    if duration_unit == 'hours':
                        expiry = timezone.now() + timedelta(hours=duration)
                    elif duration_unit == 'days':
                        expiry = timezone.now() + timedelta(days=duration)
                    elif duration_unit == 'months':
                        # Approximate: 30 days per month
                        expiry = timezone.now() + timedelta(days=duration * 30)
                    elif duration_unit == 'years':
                        # Approximate: 365 days per year
                        expiry = timezone.now() + timedelta(days=duration * 365)
                    else:
                        expiry = timezone.now() + timedelta(days=duration)
                    
                    target_profile.is_banned = True
                    target_profile.ban_type = 'temporary'
                    target_profile.ban_expires_at = expiry
                    target_profile.banned_at = timezone.now()
                    target_profile.ban_reason = ban_reason
                    target_profile.save()
                    messages.success(request, f'User {target_user.username} has been temporarily banned until {expiry.strftime("%Y-%m-%d %H:%M")}.')
                
                return redirect('manage_users')
        
        # Unban user (staff, team_member, admin)
        if 'unban_user' in request.POST and profile.role in ['admin', 'staff', 'team_member']:
            target_profile.is_banned = False
            target_profile.ban_type = None
            target_profile.ban_expires_at = None
            target_profile.banned_at = None
            target_profile.ban_reason = None
            target_profile.save()
            messages.success(request, f'User {target_user.username} has been unbanned.')
            return HttpResponseRedirect(reverse('manage_users'))
        
        # Delete user
        if 'delete_user' in request.POST:
            if target_profile.role == 'admin':
                messages.error(request, 'Cannot delete admin accounts.')
            else:
                target_user.delete()
                messages.success(request, f'User {target_user.username} has been deleted.')
                return redirect('manage_users')
    
    return render(request, "pct/manage_users.html", {
        'users': users,
        'current_user_role': profile.role,
        'filter_role': request.GET.get('filter_role', 'all')
    })

@login_required
def add_certifications(request):
    profile, created = Profile.objects.get_or_create(user=request.user)
    
    # Check permissions - staff and team members can access
    if profile.role not in ['staff', 'team_member']:
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('home')
    
    certifications = Certification.objects.filter(profile__isnull=True)
    # Only show students for certification assignment
    users = User.objects.filter(profile__role__in=Profile.USER_ROLES + ("staff",)).select_related('profile')

    # Get search terms from query string
    cert_search_query = request.GET.get('cert_search', '')
    user_search_query = request.GET.get('user_search', '')
    
    # Filter certifications by search
    if cert_search_query:
        certifications = certifications.filter(
            Q(type__name__icontains=cert_search_query) |
            Q(type__description__icontains=cert_search_query) |
            Q(level__level__icontains=cert_search_query)
        )
    
    # Filter users by search
    if user_search_query:
        users = users.filter(
            Q(username__icontains=user_search_query) |
            Q(first_name__icontains=user_search_query) |
            Q(last_name__icontains=user_search_query) |
            Q(profile__first_name__icontains=user_search_query) |
            Q(profile__last_name__icontains=user_search_query) |
            Q(email__icontains=user_search_query) |
            Q(profile__email__icontains=user_search_query)
        )
    
    # Handle POST requests
    if request.method == 'POST':
        # Initialize selected certifications list if not exists
        if 'selected_certification_ids' not in request.session:
            request.session['selected_certification_ids'] = []
        
        # Toggle certification selection
        if 'toggle_cert' in request.POST:
            cert_id = request.POST.get('cert_id')
            try:
                cert_id = int(cert_id)
                cert = Certification.objects.get(id=cert_id, profile__isnull=True)
                selected_ids = request.session.get('selected_certification_ids', [])
                
                if cert_id in selected_ids:
                    selected_ids.remove(cert_id)
                    messages.info(request, f'Deselected: {cert.type.name} - Level {cert.level.level}')
                else:
                    selected_ids.append(cert_id)
                    messages.success(request, f'Selected: {cert.type.name} - Level {cert.level.level}')
                
                request.session['selected_certification_ids'] = selected_ids
                request.session.modified = True
            except (Certification.DoesNotExist, ValueError):
                messages.error(request, 'Certification not found.')
        
        # Clear all selections
        elif 'clear_selections' in request.POST:
            request.session['selected_certification_ids'] = []
            request.session.modified = True
            messages.info(request, 'All selections cleared.')
        
        # Certify user with all selected certifications
        elif 'certify_user' in request.POST:
            user_id = request.POST.get('user_id')
            selected_ids = request.session.get('selected_certification_ids', [])
            
            if not selected_ids:
                messages.error(request, 'Please select at least one certification first.')
            else:
                try:
                    target_user = User.objects.get(id=user_id)
                    target_profile = target_user.profile
                    certs_added = []
                    certs_already_had = []
                    
                    for cert_id in selected_ids:
                        try:
                            cert_template = Certification.objects.get(id=cert_id, profile__isnull=True)
                            if target_profile.certificates.filter(
                                type=cert_template.type,
                                level=cert_template.level,
                            ).exists():
                                certs_already_had.append(
                                    f'{cert_template.type.name} - Level {cert_template.level.level}'
                                )
                            else:
                                Certification.objects.create(
                                    type=cert_template.type,
                                    level=cert_template.level,
                                    profile=target_profile,
                                )
                                certs_added.append(
                                    f'{cert_template.type.name} - Level {cert_template.level.level}'
                                )
                        except Certification.DoesNotExist:
                            continue
                    
                    if certs_added:
                        messages.success(request, f'Certified {target_profile.get_full_name()} with: {", ".join(certs_added)}')
                    if certs_already_had:
                        messages.warning(request, f'{target_profile.get_full_name()} already had: {", ".join(certs_already_had)}')
                    
                    # Clear selections after certifying
                    request.session['selected_certification_ids'] = []
                    request.session.modified = True
                except User.DoesNotExist:
                    messages.error(request, 'User not found.')
        
        # Change certification (remove old, select new)
        elif 'change_cert' in request.POST:
            cert_id = request.POST.get('cert_id')
            user_id = request.session.get('selected_user_id_for_change')
            old_cert_id = request.POST.get('old_cert_id')
            
            if user_id and old_cert_id:
                try:
                    target_user = User.objects.get(id=user_id)
                    target_profile = target_user.profile
                    old_cert = Certification.objects.get(id=old_cert_id, profile=target_profile)
                    new_cert = Certification.objects.get(id=cert_id, profile__isnull=True)
                    
                    if target_profile.certificates.filter(
                        type=new_cert.type,
                        level=new_cert.level,
                    ).exists():
                        messages.warning(
                            request,
                            f'{target_profile.get_full_name()} already has {new_cert.type.name} - Level {new_cert.level.level}',
                        )
                    else:
                        old_cert.delete()
                        Certification.objects.create(
                            type=new_cert.type,
                            level=new_cert.level,
                            profile=target_profile,
                        )
                        messages.success(
                            request,
                            f'Changed certification for {target_profile.get_full_name()} to {new_cert.type.name} - Level {new_cert.level.level}',
                        )
                    # Clear session
                    if 'selected_user_id_for_change' in request.session:
                        del request.session['selected_user_id_for_change']
                except (User.DoesNotExist, Certification.DoesNotExist):
                    messages.error(request, 'Error changing certification.')
        
        # Check if this is an AJAX request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Content-Type') == 'application/json'
        
        if is_ajax:
            # Return JSON response for AJAX requests (no page refresh)
            return JsonResponse({
                'success': True,
                'selected_count': len(request.session.get('selected_certification_ids', []))
            })
        else:
            # Preserve search queries in redirect for regular form submissions
            query_params = []
            if cert_search_query:
                query_params.append(f'cert_search={cert_search_query}')
            if user_search_query:
                query_params.append(f'user_search={user_search_query}')
            redirect_url = request.path
            if query_params:
                redirect_url += '?' + '&'.join(query_params)
            return redirect(redirect_url)
    
    # Get selected certifications for display
    selected_cert_ids = request.session.get('selected_certification_ids', [])
    selected_certs = (
        Certification.objects.filter(id__in=selected_cert_ids, profile__isnull=True)
        if selected_cert_ids
        else []
    )
    
    return render(request, "pct/add_certifications.html", {
        'certifications': certifications,
        'users': users,
        'selected_cert_ids': selected_cert_ids,
        'selected_certs': selected_certs,
        'cert_search_query': cert_search_query,
        'user_search_query': user_search_query,
    })


@login_required
def view_student_profile(request, user_id):
    """View a student's profile information"""
    profile, created = Profile.objects.get_or_create(user=request.user)
    
    # Check permissions - only staff, team members, and admin can view student profiles
    if profile.role not in ['staff', 'team_member', 'admin']:
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('home')
    
    try:
        student_user = User.objects.get(id=user_id)
        student_profile = student_user.profile
        
        # Verify it's a student
        if student_profile.role not in Profile.USER_ROLES:
            messages.error(request, 'You can only view student or team member profiles.')
            return redirect('add_certifications')
        
        return render(request, "pct/view_student_profile.html", {
            'student_profile': student_profile,
            'student_user': student_user,
        })
    except User.DoesNotExist:
        messages.error(request, 'Student not found.')
        return redirect('add_certifications')


@login_required
@require_http_methods(["POST"])
def remove_certification_api(request, user_id, cert_id):
    """API endpoint for removing a certification from a student"""
    profile, _ = Profile.objects.get_or_create(user=request.user)
    
    if profile.role not in ['staff', 'admin']:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        student_user = User.objects.get(id=user_id)
        student_profile = student_user.profile
        
        if student_profile.role not in Profile.USER_ROLES:
            return JsonResponse({'error': 'Can only remove certifications from students or team members'}, status=400)
        
        cert = Certification.objects.get(id=cert_id, profile=student_profile)
        cert.delete()
        return JsonResponse({
            'success': True,
            'message': f'Removed {cert.type.name} - Level {cert.level.level} from {student_profile.get_full_name()}'
        })
            
    except User.DoesNotExist:
        return JsonResponse({'error': 'Student not found'}, status=404)
    except Certification.DoesNotExist:
        return JsonResponse({'error': 'Certification not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_http_methods(["GET"])
def search_certifications_api(request):
    """API endpoint for real-time certification search"""
    profile, _ = Profile.objects.get_or_create(user=request.user)
    
    if profile.role not in ['staff', 'admin']:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    search_query = request.GET.get('q', '')
    certifications = Certification.objects.filter(profile__isnull=True)
    
    if search_query:
        certifications = certifications.filter(
            Q(type__name__icontains=search_query) |
            Q(type__description__icontains=search_query) |
            Q(level__level__icontains=search_query)
        )
    
    results = []
    for cert in certifications[:50]:  # Limit to 50 results
        results.append({
            'id': cert.id,
            'name': cert.type.name,
            'description': cert.type.description or '',
            'icon': cert.type.icon or 'fa-solid fa-certificate',
            'level': cert.level.level,
        })
    
    return JsonResponse({'certifications': results})


@login_required
@require_http_methods(["GET"])
def search_users_api(request):
    """API endpoint for real-time user search"""
    profile, _ = Profile.objects.get_or_create(user=request.user)
    
    if profile.role not in ['staff', 'admin']:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    search_query = request.GET.get('q', '')
    users = User.objects.filter(profile__role__in=Profile.USER_ROLES).select_related('profile')
    
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(profile__first_name__icontains=search_query) |
            Q(profile__last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(profile__email__icontains=search_query)
        )
    
    results = []
    for user in users[:50]:  # Limit to 50 results
        results.append({
            'id': user.id,
            'username': user.username,
            'name': user.profile.get_full_name(),
            'email': user.profile.get_email() or user.email or '',
        })
    
    return JsonResponse({'users': results})


@login_required
@require_http_methods(["POST"])
def create_certification_api(request):
    """API endpoint for creating a new certification"""
    profile, _ = Profile.objects.get_or_create(user=request.user)
    
    if profile.role not in ['staff', 'admin']:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        data = json.loads(request.body)
        title = data.get('title', '').strip()
        description = data.get('description', '').strip()
        icon = data.get('icon', '📜').strip()
        level = data.get('level')
        
        if not title:
            return JsonResponse({'error': 'Title is required'}, status=400)
        
        if not level or level not in [1, 2, 3]:
            return JsonResponse({'error': 'Valid level (1, 2, or 3) is required'}, status=400)
        
        # Get or create certification type
        cert_type, created = CertificationType.objects.get_or_create(
            name=title,
            defaults={
                'description': description,
                'icon': icon
            }
        )
        
        # Update description and icon if type already exists
        if not created:
            if description:
                cert_type.description = description
            if icon:
                cert_type.icon = icon
            cert_type.save()
        
        # Get or create certification level
        cert_level, _ = CertificationLevel.objects.get_or_create(level=level)
        
        # Create certification
        cert, created = Certification.objects.get_or_create(
            type=cert_type,
            level=cert_level
        )
        
        return JsonResponse({
            'success': True,
            'certification': {
                'id': cert.id,
                'name': cert.type.name,
                'description': cert.type.description or '',
                'icon': cert.type.icon or 'fa-solid fa-certificate',
                'level': cert.level.level,
            },
            'message': 'Certification created successfully' if created else 'Certification already exists'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def update_certification_api(request, cert_id):
    """API endpoint for updating a certification"""
    profile, _ = Profile.objects.get_or_create(user=request.user)
    
    if profile.role not in ['staff', 'admin']:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        cert = Certification.objects.get(id=cert_id)
        data = json.loads(request.body)
        title = data.get('title', '').strip()
        description = data.get('description', '').strip()
        icon = data.get('icon', '').strip()
        level = data.get('level')
        
        if title:
            cert.type.name = title
            cert.type.save()
        
        if description is not None:
            cert.type.description = description
            cert.type.save()
        
        if icon:
            cert.type.icon = icon
            cert.type.save()
        
        if level and level in [1, 2, 3]:
            cert_level, _ = CertificationLevel.objects.get_or_create(level=level)
            cert.level = cert_level
            cert.save()
        
        return JsonResponse({
            'success': True,
            'certification': {
                'id': cert.id,
                'name': cert.type.name,
                'description': cert.type.description or '',
                'icon': cert.type.icon or 'fa-solid fa-certificate',
                'level': cert.level.level,
            },
            'message': 'Certification updated successfully'
        })
        
    except Certification.DoesNotExist:
        return JsonResponse({'error': 'Certification not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

class TrainingCreateView(CreateView):
    model = Training
    form_class = TrainingForm
    template_name = "pct/training_form.html"
    success_url = reverse_lazy("staff-training-list")

    @method_decorator(login_required)
    @method_decorator(user_passes_test(lambda u: getattr(u.profile, "role", "") in ["staff", "team_member"]))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["staff_user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        training = self.object
        if training.time:
            week_start = _week_start_for_datetime(training.time)
            creator = getattr(self.request.user, "profile", None)
            schedule_week = _ensure_schedule_week(week_start, creator)
            if schedule_week.status != ScheduleWeek.Status.PUBLISHED:
                schedule_week.status = ScheduleWeek.Status.PUBLISHED
                schedule_week.published_at = timezone.now()
                schedule_week.save(update_fields=["status", "published_at", "updated_at"])
        return response

@login_required
@user_passes_test(lambda u: getattr(u.profile, "role", "") in ["staff", "team_member"])
def staff_training_list(request):
    now = timezone.now()
    my_trainings = (
        Training.objects.filter(staff=request.user.profile)
        .select_related("level", "student")
        .order_by(F("time").asc(nulls_last=True), "name")
    )
    available_trainings = (
        Training.objects.select_related("level", "staff")
        .filter(student__isnull=True)
        .filter(Q(time__gte=now) | Q(time__isnull=True))
        .order_by(F("time").asc(nulls_last=True), "name")
    )
    return render(
        request,
        "pct/staff_training_list.html",
        {
            "my_trainings": my_trainings,
            "available_trainings": available_trainings,
            "now": now,
        },
    )

@login_required
@user_passes_test(lambda u: getattr(u.profile, "role", "")in ["student", "staff", "team_member"])
def training_list(request):
    now = timezone.now()
    profile = request.user.profile
    any_levels, per_type_levels = _certificate_level_cache(profile)
    trainings = (
        Training.objects.select_related("staff", "level", "staff", "certification_type")
        .prefetch_related("waitlist__profile")
        .filter(Q(time__gte=now) | Q(time__isnull=True))
        .order_by(F("time").asc(nulls_last=True), "name")
    )
    trainings = list(trainings)
    for training in trainings:
        level_value = training.level.level
        prereq_level = level_value - 1 if level_value > 1 else None
        training.prereq_level = prereq_level
        training.prereq_type = training.certification_type
        training.requirement_text = _format_prereq_label(training, prereq_level) if prereq_level else None

        if level_value <= 1:
            meets_prereq = True
        elif training.certification_type_id:
            meets_prereq = prereq_level in per_type_levels.get(training.certification_type_id, set())
        else:
            meets_prereq = prereq_level in any_levels

        invited_entry = None
        is_waitlisted = False
        waitlist_status = None
        for entry in training.waitlist.all():
            if entry.profile_id == profile.id:
                is_waitlisted = True
                waitlist_status = entry.status
            if entry.status == "invited":
                invited_entry = entry
                break

        training.invited_entry = invited_entry
        training.invited_for_me = bool(invited_entry and invited_entry.profile_id == profile.id)
        waiting_for_other = bool(invited_entry and not training.invited_for_me)

        training.is_full = training.student_id is not None or waiting_for_other
        training.is_mine = training.student_id == profile.id
        training.is_waitlisted = is_waitlisted
        training.waitlist_status = waitlist_status
        schedule_week = _schedule_week_for_datetime(training.time) if training.time else None
        if training.time:
            schedule_published = schedule_week.is_published if schedule_week else True
        else:
            schedule_published = True
        training.schedule_week = schedule_week
        training.is_schedule_published = schedule_published
        training.can_signup = (
            meets_prereq
            and not training.is_full
            and not training.is_mine
            and schedule_published
        )
        if training.invited_for_me or training.is_waitlisted:
            training.can_signup = False
        training.lock_reason = None

        if training.is_mine:
            training.lock_reason = "You're registered"
        elif training.is_full:
            training.lock_reason = "Booked" if training.student_id else "Reserved for an invited student"
        elif not meets_prereq and training.requirement_text:
            training.lock_reason = f"Requires {training.requirement_text}"
        elif training.time and not schedule_published:
            training.lock_reason = "Schedule not published"
        elif training.invited_for_me:
            training.lock_reason = "You have an invitation for this training"
        elif training.is_waitlisted:
            training.lock_reason = "You're on the waitlist"

    return render(request, "pct/training_list.html", {"trainings": trainings})


@login_required
@user_passes_test(lambda u: getattr(u.profile, "role", "") in ["student", "staff", "team_member"])
def training_signup(request, pk):
    if request.method != "POST":
        messages.error(request, "Use the sign-up button to join a training.")
        return redirect("training-list")

    training = get_object_or_404(
        Training.objects.select_related("student", "staff"),
        pk=pk,
    )
    profile = request.user.profile
    required_level = training.level.level
    if required_level > 1 and not _student_has_prerequisite(profile, training):
        prerequisite_level = required_level - 1
        prereq_label = _format_prereq_label(training, prerequisite_level)
        messages.error(
            request,
            f"You need {prereq_label} before joining a level {required_level} training.",
        )
        return redirect("training-list")

    if training.student is not None:
        messages.error(request, "That training already has a student assigned.")
        return redirect("training-list")

    if training.time and training.time < timezone.now():
        messages.error(request, "That training has already taken place.")
        return redirect("training-list")

    invited_entry = training.waitlist.filter(status="invited").order_by("created_at").first()
    if invited_entry and invited_entry.profile_id != profile.id:
        messages.error(request, "This training is reserved for another student who was invited from the waitlist.")
        return redirect("training-list")

    if training.time:
        schedule_week = _schedule_week_for_datetime(training.time)
        if schedule_week and not schedule_week.is_published:
            messages.error(request, "This schedule is not published yet. Please check back after staff publishes it.")
            return redirect("training-list")

    profile = request.user.profile
    training.student = profile
    training.save(update_fields=["student"])
    if invited_entry and invited_entry.profile_id == profile.id:
        TrainingWaitlist.objects.filter(pk=invited_entry.pk).update(status="accepted")

    messages.success(request, f"You are signed up for {training.name}.")
    return redirect("training-list")


@login_required
@user_passes_test(lambda u: getattr(u.profile, "role", "") in ["student", "staff", "team_member"])
@require_http_methods(["POST"])
def training_cancel(request, pk):
    training = get_object_or_404(Training.objects.select_related("student"), pk=pk)
    profile = request.user.profile
    redirect_target = request.POST.get("next") or "home"

    if training.student_id != profile.id:
        messages.error(request, "You can only cancel trainings you are signed up for.")
        return redirect(redirect_target)

    if training.time:
        now = timezone.now()
        if training.time < now:
            messages.error(request, "You cannot cancel a training that has already occurred.")
            return redirect(redirect_target)
        if training.staff:
            existing = TrainingCancellationRequest.objects.filter(
                training=training,
                requester=profile,
                status=TrainingCancellationRequest.Status.PENDING,
            ).first()
            if existing:
                messages.info(request, "A cancellation request is already awaiting approval.")
                return redirect(redirect_target)
            TrainingCancellationRequest.objects.create(
                training=training,
                requester=profile,
                reason=request.POST.get("reason", "").strip() or None,
            )
            messages.success(
                request,
                "Cancellation request submitted. Staff will review it in the schedule release tab.",
            )
            return redirect(redirect_target)

    training.student = None
    training.save(update_fields=["student"])
    invited_entry = _invite_next_waitlisted(training)
    if invited_entry:
        messages.info(
            request,
            f"{invited_entry.profile.get_full_name()} has been invited to join {training.name}.",
        )
    messages.success(request, f"Canceled your reservation for {training.name}.")
    return redirect(redirect_target)

def about_view(request):
    return render(request, "pct/about.html")

def help_view(request):
    return render(request, "pct/help.html")

def contact_view(request):
    return render(request, "pct/contact.html")

#Calendar
# Utility: check if user is staff
def is_staff(user):
    return user.is_staff


TRAINING_BLOCK_DURATION = timedelta(hours=1)


def _user_has_staff_role(user):
    profile = getattr(user, "profile", None)
    if profile and profile.role in ("staff", "admin"):
        return True
    return user.is_staff


def _workblock_event_id(pk):
    return f"workblock-{pk}"


def _parse_workblock_id(event_id):
    if event_id is None:
        return None
    if isinstance(event_id, int):
        return event_id
    event_str = str(event_id)
    if event_str.startswith("workblock-"):
        try:
            return int(event_str.split("-", 1)[1])
        except (ValueError, TypeError):
            return None
    try:
        return int(event_str)
    except (ValueError, TypeError):
        return None

@method_decorator(login_required, name='dispatch')
class CalendarView(View):
    """
    Handles rendering the calendar page for users and staff.
    """
    def get(self, request, *args, **kwargs):
        staff_view = kwargs.get('staff_view', False)
        profile = getattr(request.user, "profile", None)
        is_staff_member = bool(profile and profile.role == "staff")
        is_team_member = bool(profile and profile.role in ["team_member", "staff"])
        return render(
            request,
            'pct/calendar.html',
            {
                "staff_view": staff_view,
                "is_staff_member": is_staff_member,
                "is_team_member": is_team_member,
            },
        )

@method_decorator(login_required, name='dispatch')
class EventsView(View):
    """
    Handles fetching, adding, updating, deleting calendar events.
    """
    # Fetch events
    def get(self, request):
        staff_view = request.GET.get("staff_view") == "1"
        if staff_view and _user_has_staff_role(request.user):
            events = WorkBlock.objects.all()
        else:
            events = WorkBlock.objects.filter(user=request.user)

        event_list = []
        for event in events:
            event_list.append({
                "id": _workblock_event_id(event.id),
                "title": event.title,
                "start": event.start.isoformat(),
                "end": event.end.isoformat(),
                "color": event.color,
                "description": event.description or "",
                "editable": True,
                "durationEditable": True,
                "startEditable": True,
                "extendedProps": {
                    "eventType": "workblock",
                    "canEdit": True,
                    "description": event.description or "",
                },
            })

        profile = getattr(request.user, "profile", None)
        trainings = Training.objects.select_related(
            "student__user", "staff__user", "level"
        ).filter(time__isnull=False)

        staff_only = request.GET.get("staff_only") == "1"
        if staff_only:
            if profile and profile.role == "staff":
                trainings = trainings.filter(staff=profile)
            else:
                trainings = Training.objects.none()

        mine_only = request.GET.get("mine_only") == "1"

        for training in trainings:
            schedule_week = _schedule_week_for_datetime(training.time)
            if schedule_week and not schedule_week.is_published:
                continue
            start_dt = training.time
            end_dt = training.time + TRAINING_BLOCK_DURATION
            student_name = training.student.get_full_name() if training.student else None
            staff_name = training.staff.get_full_name() if training.staff else None
            description = f"Machine: {training.machine}\nLevel {training.level.level}"
            if student_name:
                description += f"\nStudent: {student_name}"
            if staff_name:
                description += f"\nStaff: {staff_name}"

            color = "#16a085" if training.student else "#f39c12"

            event_list.append({
                "id": f"training-{training.id}",
                "title": f"Training: {training.name}",
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
                "color": color,
                "description": description,
                "editable": False,
                "durationEditable": False,
                "startEditable": False,
                "extendedProps": {
                    "eventType": "training",
                    "canEdit": False,
                    "machine": training.machine,
                    "description": description,
                    "student": student_name,
                    "staff": staff_name,
                    "level": training.level.level,
                },
            })

        # Shifts (published only)
        shifts = Shift.objects.select_related("assigned_to__user", "schedule_week").filter(
            schedule_week__status=ScheduleWeek.Status.PUBLISHED,
            assigned_to__isnull=False,
        )
        if mine_only and profile:
            shifts = shifts.filter(assigned_to=profile)
        for shift in shifts:
            assigned_name = shift.assigned_to.get_full_name() if shift.assigned_to else ""
            title = f"Shift: {shift.title}"
            desc_lines = [
                f"Location: {shift.location}",
                f"Assigned: {assigned_name}" if assigned_name else "Unassigned",
                f"Min staffing: {shift.min_staffing}",
            ]
            if shift.notes:
                desc_lines.append(f"Notes: {shift.notes}")
            description = "\n".join(desc_lines)
            color = "#5e8bff" if profile and shift.assigned_to_id == profile.id else "#7a88b8"
            event_list.append({
                "id": f"shift-{shift.id}",
                "title": title,
                "start": shift.start.isoformat(),
                "end": shift.end.isoformat(),
                "color": color,
                "editable": False,
                "durationEditable": False,
                "startEditable": False,
                "extendedProps": {
                    "eventType": "shift",
                    "location": shift.location,
                    "assigned_to": assigned_name,
                    "notes": shift.notes or "",
                },
            })

        # Room reservations (approved)
        reservations = RoomReservation.objects.select_related("requester__user").filter(
            status=RoomReservation.StatusChoices.APPROVED
        )
        if mine_only and profile:
            reservations = reservations.filter(requester=profile)
        elif not staff_view:
            reservations = reservations.filter(requester=request.user.profile)
        for res in reservations:
            event_list.append({
                "id": f"reservation-{res.id}",
                "title": f"Room: {res.get_room_display()}",
                "start": res.start_time.isoformat(),
                "end": res.end_time.isoformat(),
                "color": "#b565f5",
                "description": f"Affiliation: {res.affiliation}",
                "editable": False,
                "durationEditable": False,
                "startEditable": False,
                "extendedProps": {
                    "eventType": "reservation",
                    "affiliation": res.affiliation,
                    "requester": res.requester.get_full_name(),
                    "status": res.get_status_display(),
                },
            })

        return JsonResponse(event_list, safe=False)

    # Add event
    @method_decorator(csrf_exempt)
    def post(self, request):
        data = json.loads(request.body)
        action = data.get('action', 'add')  # could be 'add', 'update', 'delete'
        
        if action == 'add':
            WorkBlock.objects.create(
                user=request.user,
                title=data.get("title", "Work Block"),
                start=data["start"],
                end=data["end"],
                color=data.get("color", "#3788d8"),
                description=data.get("description", "")
            )
            return JsonResponse({"status": "success"})

        elif action == 'update':
            event_id = _parse_workblock_id(data.get('id'))
            if event_id is None:
                return JsonResponse({"status": "forbidden"}, status=403)
            try:
                event = WorkBlock.objects.get(id=event_id)
                if event.user != request.user and not request.user.is_staff:
                    return JsonResponse({"status": "forbidden"}, status=403)
                event.title = data.get("title", event.title)
                event.start = data.get("start", event.start)
                event.end = data.get("end", event.end)
                event.color = data.get("color", event.color)
                event.description = data.get("description", event.description)
                event.save()
                return JsonResponse({"status": "success"})
            except WorkBlock.DoesNotExist:
                return JsonResponse({"status": "not found"}, status=404)

        elif action == 'delete':
            event_id = _parse_workblock_id(data.get('id'))
            if event_id is None:
                return JsonResponse({"status": "forbidden"}, status=403)
            try:
                event = WorkBlock.objects.get(id=event_id)
                if event.user != request.user and not request.user.is_staff:
                    return JsonResponse({"status": "forbidden"}, status=403)
                event.delete()
                return JsonResponse({"status": "success"})
            except WorkBlock.DoesNotExist:
                return JsonResponse({"status": "not found"}, status=404)

        return JsonResponse({"status": "error"}, status=400)


@login_required
@user_passes_test(lambda u: getattr(u.profile, "role", "") in ["team_member", "staff", "admin"])
def schedule_overview(request):
    """Team members/lead/staff view: see shifts, add availability, request swaps."""
    profile, _ = Profile.objects.get_or_create(user=request.user)
    week_param = request.GET.get("week_start") or request.POST.get("week_start")
    week_start = _week_start_from_param(week_param)
    schedule_week = _ensure_schedule_week(week_start, profile if profile.role in ["staff", "admin"] else None)
    semester = _active_semester_for_date(week_start)
    week_end_date = schedule_week.week_start + timedelta(days=6)

    availability_form = AvailabilityForm(week=schedule_week, semester=semester)
    swap_form = SwapRequestForm()
    my_shifts_qs = (
        Shift.objects.filter(schedule_week=schedule_week, assigned_to=profile)
        .select_related("assigned_to__user")
        .prefetch_related("required_certifications")
        .order_by("start")
    )
    if profile.role not in ["staff", "admin"] and not schedule_week.is_published:
        my_shifts = Shift.objects.none()
    else:
        my_shifts = my_shifts_qs
    my_trainings_qs = (
        Training.objects.filter(
            staff=profile,
            time__date__gte=schedule_week.week_start,
            time__date__lt=schedule_week.week_start + timedelta(days=7),
        )
        .select_related("level", "certification_type", "student__user")
        .order_by("time", "name")
    )
    if profile.role not in ["staff", "admin"] and not schedule_week.is_published:
        my_trainings = Training.objects.none()
    else:
        my_trainings = my_trainings_qs

    my_availabilities = (
        Availability.objects.filter(week=schedule_week, profile=profile)
        .prefetch_related("skills")
        .order_by("start")
    )
    my_swap_requests = ShiftSwapRequest.objects.filter(requester=profile, shift__schedule_week=schedule_week)
    skill_choices = CertificationType.objects.order_by("name")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save_availability":
            availability_form = AvailabilityForm(request.POST, week=schedule_week, semester=semester)
            if availability_form.is_valid():
                availability = availability_form.save(commit=False)
                availability.profile = profile
                availability.week = schedule_week
                availability.save()
                availability_form.save_m2m()
                # replicate across semester if requested
                apply_semester = request.POST.get("apply_semester") == "1"
                copied_weeks = 0
                target_semester = semester or _active_semester_for_date(availability.start.date())
                if apply_semester:
                    if not target_semester:
                        messages.error(
                            request,
                            "Availability saved for this week, but no active semester is set to copy across.",
                        )
                        return redirect(f"{reverse('schedule')}?week_start={schedule_week.week_start}")
                    current_start = availability.start
                    current_end = availability.end
                    delta = timedelta(days=7)
                    cursor = schedule_week.week_start + delta
                    while cursor <= target_semester.end_date:
                        future_week = _ensure_schedule_week(cursor, profile if profile.role in ["staff", "admin"] else None)
                        future_start = current_start + (cursor - schedule_week.week_start)
                        future_end = current_end + (cursor - schedule_week.week_start)
                        if _is_holiday(target_semester, future_start.date()):
                            cursor += delta
                            continue
                        if not _within_open_hours(target_semester, future_start, future_end):
                            cursor += delta
                            continue
                        future_availability, created = Availability.objects.get_or_create(
                            profile=profile,
                            week=future_week,
                            start=future_start,
                            end=future_end,
                            defaults={"note": availability.note},
                        )
                        if created:
                            copied_weeks += 1
                            if availability.skills.exists():
                                future_availability.skills.set(availability.skills.all())
                        cursor += delta
                    if copied_weeks:
                        messages.success(
                            request,
                            f"Availability saved and applied to {copied_weeks} future week(s) in {target_semester.name}.",
                        )
                    else:
                        messages.success(
                            request,
                            "Availability saved for this week. No future weeks were updated (holidays, closed hours, or duplicate slots skipped).",
                        )
                    return redirect(f"{reverse('schedule')}?week_start={schedule_week.week_start}")
                messages.success(request, "Availability saved for this week.")
                return redirect(f"{reverse('schedule')}?week_start={schedule_week.week_start}")
            messages.error(request, "Please fix the errors in your availability.")
        elif action == "update_availability":
            slot = get_object_or_404(
                Availability, pk=request.POST.get("availability_id"), profile=profile, week=schedule_week
            )
            form = AvailabilityForm(request.POST, instance=slot, week=schedule_week, semester=semester)
            if form.is_valid():
                updated = form.save(commit=False)
                updated.profile = profile
                updated.week = schedule_week
                updated.save()
                form.save_m2m()
                messages.success(request, "Availability updated.")
                return redirect(f"{reverse('schedule')}?week_start={schedule_week.week_start}")
            availability_form = form
            messages.error(request, "Please fix the errors in your availability update.")
        elif action == "delete_availability":
            slot = get_object_or_404(
                Availability, pk=request.POST.get("availability_id"), profile=profile, week=schedule_week
            )
            slot.delete()
            messages.success(request, "Availability removed.")
            return redirect(f"{reverse('schedule')}?week_start={schedule_week.week_start}")
        elif action == "request_swap":
            shift_id = request.POST.get("shift_id")
            shift = get_object_or_404(Shift, pk=shift_id, schedule_week=schedule_week)
            if shift.assigned_to_id != profile.id:
                messages.error(request, "You can only request swaps for your own shifts.")
                return redirect(f"{reverse('schedule')}?week_start={schedule_week.week_start}")
            swap_form = SwapRequestForm(request.POST)
            if swap_form.is_valid():
                swap = swap_form.save(commit=False)
                swap.shift = shift
                swap.requester = profile
                swap.status = ShiftSwapRequest.Status.PENDING
                swap.save()
                messages.success(request, "Swap request submitted.")
                return redirect(f"{reverse('schedule')}?week_start={schedule_week.week_start}")
            messages.error(request, "Unable to submit swap request. Please fix the errors.")
        elif action == "cancel_swap":
            swap_id = request.POST.get("swap_id")
            swap = get_object_or_404(
                ShiftSwapRequest, pk=swap_id, requester=profile, shift__schedule_week=schedule_week
            )
            swap.status = ShiftSwapRequest.Status.CANCELLED
            swap.save(update_fields=["status"])
            messages.success(request, "Swap request cancelled.")
            return redirect(f"{reverse('schedule')}?week_start={schedule_week.week_start}")

    context = {
        "schedule_week": schedule_week,
        "availability_form": availability_form,
        "swap_form": swap_form,
        "my_shifts": my_shifts,
        "my_trainings": my_trainings,
        "my_availabilities": my_availabilities,
        "my_swap_requests": my_swap_requests,
        "week_end_date": week_end_date,
        "skill_choices": skill_choices,
        "active_semester": semester,
    }
    return render(request, "pct/schedule_overview.html", context)


@login_required
@user_passes_test(lambda u: getattr(u.profile, "role", "") in ["staff", "admin"])
def schedule_builder(request):
    """Staff/admin view: build weekly schedule, publish, review swaps."""
    profile = request.user.profile
    week_param = request.GET.get("week_start") or request.POST.get("week_start")
    week_start = _week_start_from_param(week_param)
    schedule_week = _ensure_schedule_week(week_start, profile)
    shift_form = ShiftForm(week=schedule_week)
    training_form = TrainingForm(staff_user=request.user)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_shift":
            shift_form = ShiftForm(request.POST, week=schedule_week)
            if shift_form.is_valid():
                shift = shift_form.save(commit=False)
                shift.schedule_week = schedule_week
                shift.created_by = profile
                shift.save()
                shift_form.save_m2m()
                messages.success(request, "Shift added.")
                return redirect(f"{reverse('schedule-builder')}?week_start={schedule_week.week_start}")
            messages.error(request, "Please fix the errors to add the shift.")
        elif action == "update_shift":
            shift = get_object_or_404(Shift, pk=request.POST.get("shift_id"), schedule_week=schedule_week)
            form = ShiftForm(request.POST, instance=shift, week=schedule_week)
            if form.is_valid():
                updated = form.save(commit=False)
                updated.schedule_week = schedule_week
                updated.created_by = shift.created_by or profile
                updated.save()
                form.save_m2m()
                messages.success(request, "Shift updated.")
                return redirect(f"{reverse('schedule-builder')}?week_start={schedule_week.week_start}")
            shift_form = form
            messages.error(request, "Please fix the errors to update the shift.")
        elif action == "delete_shift":
            shift = get_object_or_404(Shift, pk=request.POST.get("shift_id"), schedule_week=schedule_week)
            if schedule_week.is_published:
                messages.error(request, "Published schedules cannot have shifts deleted. Please unpublish or approve a change first.")
                return redirect(f"{reverse('schedule-builder')}?week_start={schedule_week.week_start}")
            shift.delete()
            messages.success(request, "Shift deleted.")
            return redirect(f"{reverse('schedule-builder')}?week_start={schedule_week.week_start}")
        elif action == "add_training":
            training_form = TrainingForm(request.POST, staff_user=request.user)
            if training_form.is_valid():
                training = training_form.save(commit=False)
                if not training.time:
                    training_form.add_error(None, "Time is required to schedule a training.")
                else:
                    end_of_week = schedule_week.week_start + timedelta(days=7)
                    if training.time.date() < schedule_week.week_start or training.time.date() >= end_of_week:
                        training_form.add_error(None, "Training must be scheduled within the selected week.")
                    else:
                        training.save()
                        training_form.save_m2m()
                        messages.success(request, "Training added to the schedule.")
                        return redirect(f"{reverse('schedule-builder')}?week_start={schedule_week.week_start}")
            messages.error(request, "Please fix the errors to add the training.")
        elif action == "delete_training":
            training = get_object_or_404(
                Training,
                pk=request.POST.get("training_id"),
                time__date__gte=schedule_week.week_start,
                time__date__lt=schedule_week.week_start + timedelta(days=7),
            )
            training.delete()
            messages.success(request, "Training removed from this week.")
            return redirect(f"{reverse('schedule-builder')}?week_start={schedule_week.week_start}")
        elif action == "publish":
            if schedule_week.status != ScheduleWeek.Status.PUBLISHED:
                schedule_week.status = ScheduleWeek.Status.PUBLISHED
                schedule_week.published_at = timezone.now()
                schedule_week.save(update_fields=["status", "published_at", "updated_at"])
                messages.success(request, "Schedule published to the team.")
            return redirect(f"{reverse('schedule-builder')}?week_start={schedule_week.week_start}")
        elif action == "unpublish":
            schedule_week.status = ScheduleWeek.Status.DRAFT
            schedule_week.save(update_fields=["status", "updated_at"])
            messages.info(request, "Schedule set back to draft.")
            return redirect(f"{reverse('schedule-builder')}?week_start={schedule_week.week_start}")
        elif action in {"approve_training_cancel", "deny_training_cancel"}:
            request_obj = get_object_or_404(
                TrainingCancellationRequest,
                pk=request.POST.get("cancel_request_id"),
                status=TrainingCancellationRequest.Status.PENDING,
            )
            new_status = (
                TrainingCancellationRequest.Status.APPROVED
                if action == "approve_training_cancel"
                else TrainingCancellationRequest.Status.DENIED
            )
            request_obj.status = new_status
            request_obj.reviewed_by = profile
            request_obj.reviewed_at = timezone.now()
            request_obj.save()

            if new_status == TrainingCancellationRequest.Status.APPROVED:
                training = request_obj.training
                training.student = None
                training.save(update_fields=["student"])
                invited_entry = _invite_next_waitlisted(training)
                messages.success(
                    request,
                    f"Approved cancellation for {training.name}. Student unassigned.",
                )
                if invited_entry:
                    messages.info(
                        request,
                        f"{invited_entry.profile.get_full_name()} has been invited to join {training.name}.",
                    )
            else:
                messages.info(request, "Cancellation request denied.")
            return redirect(f"{reverse('schedule-builder')}?week_start={schedule_week.week_start}")
        elif action in {"approve_swap", "deny_swap"}:
            swap = get_object_or_404(
                ShiftSwapRequest, pk=request.POST.get("swap_id"), shift__schedule_week=schedule_week
            )
            new_status = (
                ShiftSwapRequest.Status.APPROVED if action == "approve_swap" else ShiftSwapRequest.Status.DENIED
            )
            if new_status == ShiftSwapRequest.Status.APPROVED:
                original_assignee = swap.shift.assigned_to
                swap.shift.assigned_to = swap.proposed_to if swap.proposed_to else None
                try:
                    swap.shift.full_clean()
                    swap.shift.save(update_fields=["assigned_to"])
                except ValidationError as exc:
                    swap.shift.assigned_to = original_assignee
                    message_list = exc.message_dict.get("assigned_to", exc.messages)
                    messages.error(
                        request,
                        " ".join(message_list) if message_list else "Unable to approve swap.",
                    )
                    return redirect(f"{reverse('schedule-builder')}?week_start={schedule_week.week_start}")
            swap.status = new_status
            swap.reviewed_by = profile
            swap.reviewed_at = timezone.now()
            swap.response_note = request.POST.get("response_note", "")
            swap.save()
            messages.success(request, f"Swap request {new_status}.")
            return redirect(f"{reverse('schedule-builder')}?week_start={schedule_week.week_start}")

    week_availabilities = (
        Availability.objects.filter(week__week_start=schedule_week.week_start)
        .select_related("profile__user")
        .prefetch_related("skills")
        .order_by("start")
    )
    week_shifts = (
        Shift.objects.filter(schedule_week=schedule_week)
        .select_related("assigned_to__user")
        .prefetch_related("required_certifications")
        .order_by("start")
    )
    week_trainings = (
        Training.objects.select_related("student__user", "staff__user", "level", "certification_type")
        .filter(time__date__gte=schedule_week.week_start, time__date__lt=schedule_week.week_start + timedelta(days=7))
        .order_by("time", "name")
    )
    pending_swaps = (
        ShiftSwapRequest.objects.filter(shift__schedule_week=schedule_week, status=ShiftSwapRequest.Status.PENDING)
        .select_related("shift__assigned_to__user", "requester__user", "proposed_to__user")
        .order_by("-created_at")
    )
    pending_training_cancellations = (
        TrainingCancellationRequest.objects.filter(
            status=TrainingCancellationRequest.Status.PENDING,
            training__time__date__gte=schedule_week.week_start,
            training__time__date__lte=schedule_week.week_start + timedelta(days=6),
        )
        .select_related("training__student__user", "training__staff__user", "requester__user")
        .order_by("-created_at")
    )
    assignable_profiles = Profile.objects.filter(role__in=["team_member", "student", "staff"]).select_related("user")
    cert_choices = CertificationType.objects.order_by("name")

    context = {
        "schedule_week": schedule_week,
        "shift_form": shift_form,
        "training_form": training_form,
        "week_availabilities": week_availabilities,
        "week_shifts": week_shifts,
        "week_trainings": week_trainings,
        "pending_swaps": pending_swaps,
        "pending_training_cancellations": pending_training_cancellations,
        "assignable_profiles": assignable_profiles,
        "cert_choices": cert_choices,
        "room_choices": RoomReservation.RoomChoices.choices,
    }
    return render(request, "pct/schedule_builder.html", context)


@login_required
@user_passes_test(lambda u: getattr(u.profile, "role", "") in ["staff", "admin"])
def semester_settings(request):
    active_semester = Semester.objects.filter(is_active=True).order_by("-start_date").first()
    semester_form = SemesterForm()
    open_hour_form = OpenHourForm(initial={"semester": active_semester})
    holiday_form = HolidayForm(initial={"semester": active_semester})

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create_semester":
            semester_form = SemesterForm(request.POST)
            if semester_form.is_valid():
                semester = semester_form.save()
                if semester.is_active:
                    Semester.objects.exclude(pk=semester.pk).update(is_active=False)
                messages.success(request, "Semester saved.")
                return redirect("semester-settings")
            messages.error(request, "Please fix the errors for the semester.")
        elif action == "set_active":
            semester = get_object_or_404(Semester, pk=request.POST.get("semester_id"))
            Semester.objects.exclude(pk=semester.pk).update(is_active=False)
            semester.is_active = True
            semester.save(update_fields=["is_active"])
            messages.success(request, f"{semester.name} set as active.")
            return redirect("semester-settings")
        elif action == "unset_active":
            semester = get_object_or_404(Semester, pk=request.POST.get("semester_id"))
            semester.is_active = False
            semester.save(update_fields=["is_active"])
            messages.info(request, f"{semester.name} is no longer active.")
            return redirect("semester-settings")
        elif action == "add_open_hour":
            open_hour_form = OpenHourForm(request.POST)
            if open_hour_form.is_valid():
                open_hour_form.save()
                messages.success(request, "Open hours added.")
                return redirect("semester-settings")
            messages.error(request, "Please fix the open hours form.")
        elif action == "delete_open_hour":
            entry = get_object_or_404(OpenHour, pk=request.POST.get("open_hour_id"))
            entry.delete()
            messages.success(request, "Open hours removed.")
            return redirect("semester-settings")
        elif action == "add_holiday":
            holiday_form = HolidayForm(request.POST)
            if holiday_form.is_valid():
                holiday_form.save()
                messages.success(request, "Holiday added.")
                return redirect("semester-settings")
            messages.error(request, "Please fix the holiday form.")
        elif action == "delete_holiday":
            holiday = get_object_or_404(Holiday, pk=request.POST.get("holiday_id"))
            holiday.delete()
            messages.success(request, "Holiday removed.")
            return redirect("semester-settings")

    semesters = Semester.objects.all().order_by("-start_date")
    open_hours = (
        OpenHour.objects.select_related("semester")
        .order_by("semester__start_date", "weekday", "open_time")
    )
    holidays = Holiday.objects.select_related("semester").order_by("semester__start_date", "date")

    return render(
        request,
        "pct/semester_settings.html",
        {
            "semesters": semesters,
            "open_hours": open_hours,
            "holidays": holidays,
            "active_semester": active_semester,
            "semester_form": semester_form,
            "open_hour_form": open_hour_form,
            "holiday_form": holiday_form,
        },
    )
    
class TrainingWaitlistBase(View):
    def get_training(self, training_id):
        return get_object_or_404(Training, id=training_id)

    def get_profile(self, request, profile_id=None):
        if profile_id:
            return get_object_or_404(Profile, id=profile_id)
        return request.user.profile


@method_decorator(login_required, name="dispatch")
class RegisterTrainingView(TrainingWaitlistBase):
    def post(self, request, training_id):
        training = self.get_training(training_id)
        profile = self.get_profile(request)

        if training.student:
            TrainingWaitlist.objects.get_or_create(training=training, profile=profile)
            messages.info(request, "Training is full. You’ve been added to the waitlist.")
        else:
            training.student = profile
            training.save()
            messages.success(request, "You’re registered for the training!")

        return redirect("home")


@login_required
def cancel_training(request, training_id):
    training = get_object_or_404(Training, id=training_id)
    profile = request.user.profile

    if training.student == profile:
        training.student = None
        training.save()
        invited_entry = _invite_next_waitlisted(training)
        if invited_entry:
            messages.info(
                request,
                f"{invited_entry.profile.get_full_name()} has been invited to join {training.name}.",
            )
        messages.success(request, "Your reservation has been cancelled.")
    return redirect("home")



@method_decorator(login_required, name="dispatch")
class ConfirmTrainingView(TrainingWaitlistBase):
    def post(self, request, training_id, profile_id):
        training = self.get_training(training_id)
        profile = self.get_profile(request, profile_id)

        if not training.student:
            training.student = profile
            training.save()
            TrainingWaitlist.objects.filter(training=training, profile=profile).update(status="accepted")
            messages.success(request, "You’re now registered!")
        else:
            messages.error(request, "Sorry, the spot was already taken.")

        return redirect("home")


@method_decorator(login_required, name="dispatch")
class DeclineTrainingView(TrainingWaitlistBase):
    def post(self, request, training_id, profile_id):
        TrainingWaitlist.objects.filter(training_id=training_id, profile_id=profile_id).update(status="declined")
        messages.info(request, "You declined the training invitation.")
        return redirect("home")

@login_required
def join_waitlist(request, training_id):
    training = get_object_or_404(Training, id=training_id)
    profile = request.user.profile

    # Prevent duplicates
    if TrainingWaitlist.objects.filter(training=training, profile=profile).exists():
        messages.info(request, "You are already on the waitlist for this training.")
    else:
        TrainingWaitlist.objects.create(training=training, profile=profile)
        messages.success(request, f"You have been added to the waitlist for {training.name}.")

    return redirect("home")


@login_required
def leave_waitlist(request, training_id):
    training = get_object_or_404(Training, id=training_id)
    profile = request.user.profile

    entry = TrainingWaitlist.objects.filter(training=training, profile=profile).first()
    if not entry:
        messages.info(request, "You are not on the waitlist for this training.")
        return redirect("home")

    was_invited = entry.status == "invited"
    entry.delete()
    messages.success(request, f"You have left the waitlist for {training.name}.")

    if was_invited:
        next_entry = _invite_next_waitlisted(training)
        if next_entry:
            messages.info(
                request,
                f"{next_entry.profile.get_full_name()} has been invited to join {training.name}.",
            )

    return redirect("home")

@login_required
def respond_invitation(request, waitlist_id):
    entry = get_object_or_404(TrainingWaitlist, id=waitlist_id, profile=request.user.profile)

    if entry.status != "invited":
        messages.info(request, "This invitation is no longer available.")
        return redirect("home")

    response = request.POST.get("response")
    if response == "accept":
        # Assign training to user if still available
        training = entry.training
        if not training.is_full():
            training.student = entry.profile
            training.save()
            entry.status = "accepted"
            messages.success(request, f"You are now booked for {training.name}.")
        else:
            messages.error(request, "Sorry, the training is already full.")
    elif response == "decline":
        entry.status = "declined"
        messages.info(request, f"You declined the invitation for {entry.training.name}.")

    entry.save()
    if entry.status == "declined":
        invited_entry = _invite_next_waitlisted(entry.training)
        if invited_entry:
            messages.info(
                request,
                f"{invited_entry.profile.get_full_name()} has been invited to join {entry.training.name}.",
            )
    return redirect("home")

@login_required
def user_home(request):
    profile = request.user.profile
    now = timezone.now()

    # Upcoming room reservations for this user
    upcoming_room_reservations = (
        profile.room_reservations.filter(end_time__gte=now)
        .select_related("reviewed_by__user")
        .order_by("start_time")
    )

    # All upcoming trainings (not just ones booked by this user)
    upcoming_trainings = (
        Training.objects.filter(time__gte=now)
        .select_related("staff", "level")
        .prefetch_related("waitlist__profile")
        .order_by("time")
    )
    for training in upcoming_trainings:
        has_invited_hold = False
        is_waitlisted = False
        waitlist_status = None
        for entry in training.waitlist.all():
            if entry.status == "invited":
                has_invited_hold = True
            if entry.profile_id == profile.id:
                is_waitlisted = True
                waitlist_status = entry.status
        training.is_full_for_display = bool(training.student_id or has_invited_hold)
        training.is_waitlisted_for_user = is_waitlisted
        training.waitlist_status_for_user = waitlist_status

    # Past trainings
    past_trainings = (
        Training.objects.filter(time__lt=now)
        .select_related("staff", "level")
        .order_by("-time")
    )

    # Any invitations for this user
    invited_trainings = TrainingWaitlist.objects.filter(profile=profile, status="invited")

    context = {
        "profile": profile,
        "upcoming_room_reservations": upcoming_room_reservations,
        "upcoming_trainings": upcoming_trainings,
        "past_trainings": past_trainings,
        "invited_trainings": invited_trainings,
    }
    # Branch by role
    if profile.role == "staff":
        # staff context
        return render(request, "pct/staff_home.html", context)
    elif profile.role == "team_member":
        # team member context
        return render(request, "pct/staff_home.html", context)
    else:
        # student (or default) context
        return render(request, "pct/user_home.html", context)
