from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from pct import views as v

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', v.login_view, name='login'),
    path('', include('pct.urls')),
    path('accounts/', include('allauth.urls')),
    path('', lambda request: redirect('login')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
