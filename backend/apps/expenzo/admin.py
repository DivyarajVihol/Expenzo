from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import UserProfile, EmailVerificationToken


# ── Inline for UserProfile on User admin ────────────────────────────────────
class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name = 'Profile'
    verbose_name_plural = 'Profile'
    fields = (
        'is_email_verified',
        'signup_method',
        'google_picture_url',
        'phone',
        'country',
        'bio',
        'savings_target',
        'savings_current',
    )
    readonly_fields = ('signup_method',)


# ── Extended User admin ──────────────────────────────────────────────────────
class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = (
        'email',
        'username',
        'get_is_email_verified',
        'get_signup_method',
        'is_active',
        'date_joined',
        'last_login',
    )
    list_filter = (
        'is_active',
        'profile__is_email_verified',
        'profile__signup_method',
    )
    search_fields = ('email', 'username', 'first_name')
    ordering = ('-date_joined',)

    @admin.display(description='Email Verified', boolean=True)
    def get_is_email_verified(self, obj):
        try:
            return obj.profile.is_email_verified
        except UserProfile.DoesNotExist:
            return False

    @admin.display(description='Signup Method')
    def get_signup_method(self, obj):
        try:
            return obj.profile.get_signup_method_display()
        except UserProfile.DoesNotExist:
            return '—'


# ── EmailVerificationToken admin ─────────────────────────────────────────────
@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'token', 'created_at', 'is_used', 'is_expired_display')
    list_filter = ('is_used',)
    search_fields = ('user__email', 'user__username')
    readonly_fields = ('token', 'created_at', 'is_used')
    ordering = ('-created_at',)

    @admin.display(description='Expired', boolean=True)
    def is_expired_display(self, obj):
        return obj.is_expired()


# Re-register User with the extended admin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
