import logging

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView, DeleteView, DetailView, ListView, UpdateView
)

from .models import Provider, ProviderTest

logger = logging.getLogger(__name__)


class ProviderListView(ListView):
    model = Provider
    template_name = 'providers/list.html'
    context_object_name = 'providers'

    def get_queryset(self):
        return Provider.objects.prefetch_related('tests').all()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Attach most recent test to each provider
        for p in ctx['providers']:
            p.last_test = p.tests.first()
        return ctx


class ProviderCreateView(CreateView):
    model = Provider
    template_name = 'providers/create.html'
    fields = ['name', 'provider_type', 'base_url', 'api_key', 'default_model', 'is_active', 'extra_params']
    success_url = reverse_lazy('providers:list')

    def form_valid(self, form):
        messages.success(self.request, f'Provider "{form.instance.name}" created successfully.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Create Provider'
        return ctx


class ProviderUpdateView(UpdateView):
    model = Provider
    template_name = 'providers/create.html'
    fields = ['name', 'provider_type', 'base_url', 'api_key', 'default_model', 'is_active', 'extra_params']
    success_url = reverse_lazy('providers:list')

    def form_valid(self, form):
        messages.success(self.request, f'Provider "{form.instance.name}" updated successfully.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Edit Provider'
        return ctx


class ProviderDeleteView(DeleteView):
    model = Provider
    template_name = 'providers/confirm_delete.html'
    success_url = reverse_lazy('providers:list')

    def form_valid(self, form):
        name = self.object.name
        messages.success(self.request, f'Provider "{name}" deleted.')
        return super().form_valid(form)


class ProviderDetailView(DetailView):
    model = Provider
    template_name = 'providers/detail.html'
    context_object_name = 'provider'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['recent_tests'] = self.object.tests.all()[:10]
        return ctx


def test_provider_view(request, pk):
    """AJAX POST to test provider connection."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    provider = get_object_or_404(Provider, pk=pk)
    try:
        backend = provider.get_backend()
        result = backend.test_connection()

        ProviderTest.objects.create(
            provider=provider,
            model_name=provider.default_model or '',
            status='success' if result['success'] else 'failed',
            response_time=result.get('response_time'),
            error_message=result.get('error') or '',
        )

        return JsonResponse({
            'success': result['success'],
            'error': result.get('error'),
            'response_time': result.get('response_time'),
            'response': result.get('response', ''),
            'models': result.get('models', []),
        })
    except Exception as e:
        ProviderTest.objects.create(
            provider=provider,
            model_name=provider.default_model or '',
            status='failed',
            error_message=str(e),
        )
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def list_models_view(request, pk):
    """AJAX GET to list available models."""
    provider = get_object_or_404(Provider, pk=pk)
    try:
        backend = provider.get_backend()
        models = backend.list_models()
        return JsonResponse({'models': models})
    except Exception as e:
        return JsonResponse({'models': [], 'error': str(e)}, status=500)
