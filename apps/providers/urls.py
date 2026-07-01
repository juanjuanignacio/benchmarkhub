from django.urls import path
from . import views

app_name = 'providers'

urlpatterns = [
    path('', views.ProviderListView.as_view(), name='list'),
    path('create/', views.ProviderCreateView.as_view(), name='create'),
    path('<int:pk>/', views.ProviderDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.ProviderUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', views.ProviderDeleteView.as_view(), name='delete'),
    path('<int:pk>/test/', views.test_provider_view, name='test'),
    path('<int:pk>/models/', views.list_models_view, name='list_models'),
]
