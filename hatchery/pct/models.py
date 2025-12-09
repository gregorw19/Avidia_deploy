from datetime import timedelta

from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone

# Create your models here.

class School(models.Model):
    school_name = models.CharField(max_length=100)
    def __str__(self):
        return self.school_name
    
class Major(models.Model):
    major_name = models.CharField(max_length=100)

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='majors')
    def __str__(self):
        return f"{self.major_name}({self.school.school_name})"

class Minor(models.Model):
    minor_name = models.CharField(max_length=255, blank=True, default="")

    # major = models.ForeignKey(Major, on_delete=models.CASCADE, blank=True, null=True)

    def __str__(self):
        return f"{self.minor_name} "
    
class Profile(models.Model):
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('staff', 'Staff'),
        ('admin', 'Admin'),
        ('team_member', 'Team Member'),
    ]
    USER_ROLES = ("student", "team_member")
    
    user = models.OneToOneField(User,on_delete=models.CASCADE) #one user to one profile

    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=None, blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True)
    is_team_lead = models.BooleanField(default=False)


    major1 = models.ForeignKey(Major, on_delete=models.SET_NULL, blank=False, null=True, related_name = 'primary_major_profiles') # These are false b/c each person needs at least one major
    major2 = models.ForeignKey(Major, on_delete=models.SET_NULL, default = None, blank=True, null=True, related_name = 'secondary_major_profiles')
    minor1 = models.ForeignKey(Minor, on_delete=models.SET_NULL, default = None, blank=True, null=True, related_name = 'primary_minor_profiles')
    minor2 = models.ForeignKey(Minor, on_delete=models.SET_NULL, default = None, blank=True, null=True, related_name = 'secondary_minor_profiles')

    email = models.CharField(max_length=100, blank=True, null=True)
    #certifications = models.ManyToManyField('Certification', blank=True, related_name="profiles")
    
    # Ban fields
    is_banned = models.BooleanField(default=False)
    ban_type = models.CharField(max_length=20, choices=[('temporary', 'Temporary'), ('permanent', 'Permanent')], blank=True, null=True)
    ban_expires_at = models.DateTimeField(blank=True, null=True)
    banned_at = models.DateTimeField(blank=True, null=True)
    ban_reason = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"{self.user.username}'s profile"

    @property
    def is_user_role(self):
        """Return True when the role should behave like a general user/student."""
        return (self.role or "").lower() in self.USER_ROLES
    
    def get_full_name(self):
        """Get the user's full name"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.user.first_name and self.user.last_name:
            return f"{self.user.first_name} {self.user.last_name}"
        else:
            return self.user.username
    
    def get_email(self):
        """Get the user's email"""
        if self.email:
            return self.email
        return self.user.email
    
    def is_currently_banned(self):
        """Check if user is currently banned (considering expiry for temporary bans)"""
        if not self.is_banned:
            return False
        if self.ban_type == 'permanent':
            return True
        if self.ban_type == 'temporary' and self.ban_expires_at:
            from django.utils import timezone
            return timezone.now() < self.ban_expires_at
        return False
    

class ActivityLog(models.Model):
    ACTION_CHOICES = [
        ('booking', 'Booking'),
        ('certification', 'Certification'),
        ('login', 'Login'),
        ('reservation', 'Reservation'),
        ('training', 'Training'),
        ('other', 'Other'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activity_logs')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.action}"


class Report(models.Model):
    CATEGORY_CHOICES = [
        ('website', 'Website'),
        ('reservation', 'Reservation'),
        ('training', 'Training'),
        ('machine', 'Machine'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('open', 'Open'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]

    title = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    resolved_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_by = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='reports_submitted')
    resolved_by = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True, related_name='reports_resolved')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

class CertificationType(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    icon = models.CharField(max_length=100, default='fa-solid fa-certificate', help_text='Font Awesome icon class (e.g., fa-solid fa-print)')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name

class CertificationLevel(models.Model):
    LEVEL_CHOICES = [
        (1, 'Level 1'),
        (2, 'Level 2'),
        (3, 'Level 3'),
    ]
    level = models.IntegerField(blank=False, null=False, choices=LEVEL_CHOICES)
    
    def __str__(self):
        return f"Level {self.level}"

class Certification(models.Model):
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="certificates", null=True, blank=True) #just added this line extension: 
    type = models.ForeignKey(CertificationType, on_delete=models.PROTECT)
    level = models.ForeignKey(CertificationLevel, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        owner = self.profile.user.username if self.profile and self.profile.user_id else "unassigned"
        return f"{self.type.name} - level {self.level.level} ({owner})"

class Training(models.Model):
    name = models.CharField(max_length = 200)
    machine = models.CharField(max_length = 100)
    level = models.ForeignKey(CertificationLevel, on_delete=models.PROTECT)
    certification_type = models.ForeignKey(
        CertificationType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="trainings",
        help_text="Select which certification track this session advances.",
    )
    student = models.ForeignKey(
        Profile,
        on_delete=models.SET_NULL, null=True,
        blank=True, related_name="trainings_booked",
        limit_choices_to={"role__in": list(Profile.USER_ROLES) + ["staff"]},
        )
    staff = models.ForeignKey(
        Profile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trainings_led',
        limit_choices_to={'role__in': ('staff', 'team_member')},
    )

    time = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.name} ({self.machine})"
    
    capacity = models.PositiveIntegerField(default=1) 

    def is_full(self):
        return self.student is not None

class TrainingCancellationRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        DENIED = "denied", "Denied"

    training = models.ForeignKey(Training, on_delete=models.CASCADE, related_name="cancellation_requests")
    requester = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="training_cancellations")
    reason = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True, related_name="training_cancellations_reviewed")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("training", "requester", "status")

    def __str__(self):
        return f"Cancellation for {self.training} by {self.requester.get_full_name()}"


class RoomReservation(models.Model):
    class RoomChoices(models.TextChoices):
        HATCH_FRONT = "second_hatch_front", "Second Floor • Hatch Front"
        HATCH_BACK = "second_hatch_back", "Second Floor • Hatch Back"
        PROTO_STUDIO = "third_proto_studio", "Third Floor • Prototyping Studio"
        PROTO_SHOP = "third_proto_shop", "Third Floor • Prototyping Shop"

    class StatusChoices(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        DENIED = "denied", "Denied"

    requester = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="room_reservations",
    )
    room = models.CharField(max_length=32, choices=RoomChoices.choices)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    affiliation = models.CharField(max_length=255, help_text="Class or organization")
    is_exclusive_request = models.BooleanField(
        default=False,
        help_text="Mark when the requester needs exclusive classroom/station access for a course/event.",
    )
    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDING,
    )
    reviewed_by = models.ForeignKey(
        Profile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="room_reservations_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_time", "-created_at"]

    def clean(self):
        super().clean()
        if self.end_time and self.start_time:
            if self.end_time <= self.start_time:
                raise ValidationError("End time must be after the start time.")
            if self.start_time.date() != self.end_time.date():
                raise ValidationError("Reservations must start and end on the same day.")
            overlapping = (
                RoomReservation.objects.exclude(pk=self.pk)
                .exclude(status=self.StatusChoices.DENIED)
                .filter(
                    room=self.room,
                    start_time__lt=self.end_time,
                    end_time__gt=self.start_time,
                )
            )
            if overlapping.exists():
                raise ValidationError(
                    {"start_time": "This room is already reserved during the selected time."}
                )

    def __str__(self):
        return (
            f"{self.get_room_display()} on {self.start_time:%Y-%m-%d} "
            f"from {self.start_time:%H:%M} to {self.end_time:%H:%M}"
        )
class WorkBlock(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=100, default="Work Block")
    start = models.DateTimeField()
    end = models.DateTimeField()
    color = models.CharField(max_length=20, default="#3788d8") 
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.user.username}: {self.title} ({self.start}-{self.end})"


class ScheduleWeek(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    week_start = models.DateField(help_text="Use the Monday of the week.")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True, related_name="weeks_created")
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-week_start"]
        unique_together = ("week_start",)

    def __str__(self):
        return f"Week of {self.week_start}"

    @property
    def is_published(self):
        return self.status == self.Status.PUBLISHED


class Availability(models.Model):
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="availabilities")
    week = models.ForeignKey(ScheduleWeek, on_delete=models.CASCADE, related_name="availabilities")
    start = models.DateTimeField()
    end = models.DateTimeField()
    skills = models.ManyToManyField(CertificationType, blank=True, related_name="availabilities")
    note = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start"]

    def __str__(self):
        return f"{self.profile.get_full_name()} available {self.start} - {self.end}"


class Shift(models.Model):
    schedule_week = models.ForeignKey(ScheduleWeek, on_delete=models.CASCADE, related_name="shifts")
    title = models.CharField(max_length=150)
    location = models.CharField(max_length=150)
    start = models.DateTimeField()
    end = models.DateTimeField()
    min_staffing = models.PositiveIntegerField(default=1)
    assigned_to = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True, related_name="shifts")
    created_by = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True, related_name="shifts_created")
    required_certifications = models.ManyToManyField(CertificationType, blank=True, related_name="shifts")
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start"]

    def __str__(self):
        return f"{self.title} @ {self.start}"

    @property
    def is_published(self):
        return self.schedule_week.is_published

    @staticmethod
    def weekly_assigned_duration(week, assignee, exclude_shift_id=None):
        """Return total duration already assigned to assignee for the week."""
        if not week or not assignee:
            return timedelta()
        shifts = Shift.objects.filter(schedule_week=week, assigned_to=assignee)
        if exclude_shift_id:
            shifts = shifts.exclude(pk=exclude_shift_id)
        total = shifts.annotate(
            duration=models.ExpressionWrapper(
                models.F("end") - models.F("start"),
                output_field=models.DurationField(),
            )
        ).aggregate(total=models.Sum("duration"))["total"]
        return total or timedelta()

    def clean(self):
        super().clean()
        if self.start and self.end:
            local_start = timezone.localtime(self.start) if timezone.is_aware(self.start) else self.start
            local_end = timezone.localtime(self.end) if timezone.is_aware(self.end) else self.end

            start_semester = (
                Semester.objects.filter(
                    is_active=True,
                    start_date__lte=local_start.date(),
                    end_date__gte=local_start.date(),
                )
                .order_by("-start_date")
                .first()
            )
            end_semester = (
                Semester.objects.filter(
                    is_active=True,
                    start_date__lte=local_end.date(),
                    end_date__gte=local_end.date(),
                )
                .order_by("-start_date")
                .first()
            )
            if not start_semester or not end_semester or start_semester.pk != end_semester.pk:
                message = "Shift must start and end within an active semester."
                raise ValidationError({"start": message, "end": message})

            semester = start_semester
            if semester.holidays.filter(date=local_start.date()).exists():
                raise ValidationError({"start": f"{local_start.date()} is marked as a holiday for {semester.name}."})

            open_hours = semester.open_hours.filter(
                weekday=local_start.weekday(),
                open_time__lte=local_start.time(),
                close_time__gte=local_end.time(),
            )
            if not open_hours.exists():
                raise ValidationError({"start": f"This shift is outside the open hours for {semester.name}."})

        if (
            self.assigned_to
            and self.assigned_to.role == "team_member"
            and self.schedule_week
            and self.start
            and self.end
        ):
            current_duration = self.weekly_assigned_duration(
                self.schedule_week, self.assigned_to, exclude_shift_id=self.pk
            )
            projected_total = current_duration + (self.end - self.start)
            if projected_total > timedelta(hours=20):
                raise ValidationError({
                    "assigned_to": f"{self.assigned_to.get_full_name()} would exceed 20 hours for this week."
                })
        # Enforce known locations
        if self.location and self.location not in RoomReservation.RoomChoices.values:
            raise ValidationError({"location": "Select a valid location."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ShiftSwapRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        DENIED = "denied", "Denied"
        CANCELLED = "cancelled", "Cancelled"

    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name="swap_requests")
    requester = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="swap_requests_made")
    proposed_to = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True, related_name="swap_requests_received")
    is_give_up = models.BooleanField(default=False, help_text="Set when requester is giving up the shift without a proposed partner.")
    reason = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True, related_name="swap_requests_reviewed")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    response_note = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Swap request for {self.shift} by {self.requester.get_full_name()}"


class Semester(models.Model):
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return self.name


class OpenHour(models.Model):
    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"

    semester = models.ForeignKey(Semester, on_delete=models.CASCADE, related_name="open_hours")
    weekday = models.IntegerField(choices=Weekday.choices)
    open_time = models.TimeField()
    close_time = models.TimeField()

    class Meta:
        ordering = ["weekday", "open_time"]
        unique_together = ("semester", "weekday", "open_time", "close_time")

    def __str__(self):
        return f"{self.get_weekday_display()}: {self.open_time} - {self.close_time}"


class Holiday(models.Model):
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE, related_name="holidays")
    date = models.DateField()
    name = models.CharField(max_length=150)

    class Meta:
        ordering = ["date"]
        unique_together = ("semester", "date")

    def __str__(self):
        return f"{self.name} ({self.date})"
class TrainingWaitlist(models.Model):
    training = models.ForeignKey(Training, on_delete=models.CASCADE, related_name="waitlist")
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="waitlist_entries")
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ("waiting", "Waiting"),
            ("invited", "Invited"),
            ("accepted", "Accepted"),
            ("declined", "Declined"),
        ],
        default="waiting",
    )

    class Meta:
        unique_together = ('training', 'profile')
        ordering = ['created_at']

    def __str__(self):
        return f"{self.profile.get_full_name()} waiting for {self.training.name}"
