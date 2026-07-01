from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView, TemplateView
from apps.benchmarks.dashboard import dashboard_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(url='/dashboard/', permanent=False)),
    path('dashboard/', dashboard_view, name='dashboard'),
    path('benchmarks/', include('apps.benchmarks.urls', namespace='benchmarks')),
    path('providers/', include('apps.providers.urls', namespace='providers')),
    path('runs/', include('apps.runs.urls', namespace='runs')),
    path('api/v1/', include('apps.runs.api_urls')),
    path('api/docs/', TemplateView.as_view(template_name='api_docs.html'), name='api_docs'),
    path('howto/', TemplateView.as_view(template_name='howto.html'), name='howto'),
]

# Serve media files (benchmark images/audio) in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
