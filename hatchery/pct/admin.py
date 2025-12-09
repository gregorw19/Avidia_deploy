from django.contrib import admin
from .models import (
    Profile,
    Certification,
    CertificationType,
    CertificationLevel,
    Training,
    TrainingCancellationRequest,
    RoomReservation,
    ScheduleWeek,
    Availability,
    Shift,
    ShiftSwapRequest,
    Semester,
    OpenHour,
    Holiday,
)

# Register your models here.

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'first_name', 'last_name', 'role', 'email']
    list_filter = ['role']
    search_fields = ['user__username', 'first_name', 'last_name', 'email']

@admin.register(Certification)
class CertificationAdmin(admin.ModelAdmin):
    list_display = ['type', 'level', 'created_at']
    list_filter = ['type', 'level']
    search_fields = ['type__name']

@admin.register(CertificationType)
class CertificationTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'description']
    search_fields = ['name']

@admin.register(CertificationLevel)
class CertificationLevelAdmin(admin.ModelAdmin):
    list_display = ['level']
    search_fields = ['level']

@admin.register(Training)
class TrainingAdmin(admin.ModelAdmin):
    list_display = ("name", "machine", "level", "staff", "student")
    search_fields = ("name", "machine", "staff__user__username", "student__user__username")
    autocomplete_fields = ("staff", "student")
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "staff":
            kwargs["queryset"] = Profile.objects.filter(role="staff")
        elif db_field.name == "student":
            kwargs["queryset"] = Profile.objects.filter(role__in=Profile.USER_ROLES)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(TrainingCancellationRequest)
class TrainingCancellationRequestAdmin(admin.ModelAdmin):
    list_display = ("training", "requester", "status", "created_at", "reviewed_by")
    list_filter = ("status",)
    search_fields = ("training__name", "requester__user__username")
    autocomplete_fields = ("training", "requester", "reviewed_by")

@admin.register(RoomReservation)
class RoomReservationAdmin(admin.ModelAdmin):
    list_display = (
        "room",
        "start_time",
        "end_time",
        "requester",
        "is_exclusive_request",
        "affiliation",
        "status",
        "reviewed_by",
    )
    list_filter = ("room", "status")
    search_fields = (
        "requester__user__username",
        "requester__first_name",
        "requester__last_name",
        "affiliation",
    )
    autocomplete_fields = ("requester", "reviewed_by")


@admin.register(ScheduleWeek)
class ScheduleWeekAdmin(admin.ModelAdmin):
    list_display = ("week_start", "status", "published_at", "created_by")
    list_filter = ("status",)
    search_fields = ("week_start",)


@admin.register(Availability)
class AvailabilityAdmin(admin.ModelAdmin):
    list_display = ("profile", "week", "start", "end")
    list_filter = ("week__week_start",)
    autocomplete_fields = ("profile", "week")


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ("title", "schedule_week", "location", "start", "end", "assigned_to", "min_staffing")
    list_filter = ("schedule_week__week_start", "location")
    autocomplete_fields = ("assigned_to", "created_by", "schedule_week")
    search_fields = ("title", "location", "assigned_to__user__username", "schedule_week__week_start")


@admin.register(ShiftSwapRequest)
class ShiftSwapRequestAdmin(admin.ModelAdmin):
    list_display = ("shift", "requester", "proposed_to", "status", "created_at")
    list_filter = ("status",)
    autocomplete_fields = ("shift", "requester", "proposed_to", "reviewed_by")


@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(OpenHour)
class OpenHourAdmin(admin.ModelAdmin):
    list_display = ("semester", "weekday", "open_time", "close_time")
    list_filter = ("semester", "weekday")
    autocomplete_fields = ("semester",)


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ("semester", "date", "name")
    list_filter = ("semester",)
    search_fields = ("name",)
    autocomplete_fields = ("semester",)
