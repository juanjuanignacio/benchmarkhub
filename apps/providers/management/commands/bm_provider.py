"""
Manage LLM providers from the command line.

Examples:
    python manage.py bm_provider list
    python manage.py bm_provider add ollama Ollama --type ollama --url http://localhost:11434
    python manage.py bm_provider add my-openai "OpenAI" --type openai --key sk-...
    python manage.py bm_provider test ollama --model llama3.2
    python manage.py bm_provider models ollama
    python manage.py bm_provider delete old-provider
"""
import re

from django.core.management.base import BaseCommand, CommandError

from apps.providers.models import Provider

PROVIDER_TYPES = ['ollama', 'openai', 'anthropic', 'vllm', 'gemini', 'groq', 'mistral', 'cohere', 'together']


class Command(BaseCommand):
    help = 'Manage LLM providers'

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest='action', required=True)

        # list
        subparsers.add_parser('list', help='List all providers')

        # add
        p_add = subparsers.add_parser('add', help='Add a new provider')
        p_add.add_argument('slug', help='Unique slug (e.g. my-ollama)')
        p_add.add_argument('name', help='Display name')
        p_add.add_argument('--type', required=True, choices=PROVIDER_TYPES,
                           dest='provider_type', help='Provider type')
        p_add.add_argument('--url', default='', help='Base URL')
        p_add.add_argument('--key', default='', help='API key')
        p_add.add_argument('--default-model', default='', help='Default model name')

        # test
        p_test = subparsers.add_parser('test', help='Test a provider connection')
        p_test.add_argument('slug', help='Provider slug')
        p_test.add_argument('--model', default='', help='Model to test with')

        # models
        p_models = subparsers.add_parser('models', help='List available models from a provider')
        p_models.add_argument('slug', help='Provider slug')

        # delete
        p_del = subparsers.add_parser('delete', help='Delete a provider')
        p_del.add_argument('slug', help='Provider slug')

    def handle(self, *args, **options):
        action = options['action']
        if action == 'list':
            self._list()
        elif action == 'add':
            self._add(options)
        elif action == 'test':
            self._test(options)
        elif action == 'models':
            self._models(options)
        elif action == 'delete':
            self._delete(options)

    def _list(self):
        providers = Provider.objects.order_by('provider_type', 'name')
        if not providers:
            self.stdout.write('No providers configured.')
            self.stdout.write('Add one: python manage.py bm_provider add <slug> <name> --type ollama --url ...')
            return
        fmt = '{:<22} {:<12} {:<8} {}'
        self.stdout.write(self.style.SUCCESS(fmt.format('SLUG', 'TYPE', 'STATUS', 'NAME / URL')))
        self.stdout.write('-' * 65)
        for p in providers:
            status = self.style.SUCCESS('active') if p.is_active else self.style.WARNING('inactive')
            url = p.base_url[:30] if p.base_url else ''
            self.stdout.write(fmt.format(p.slug[:22], p.provider_type[:12], status, f'{p.name} ({url})'))

    def _add(self, options):
        slug = options['slug']
        if not re.match(r'^[a-z0-9][a-z0-9\-]*$', slug):
            raise CommandError(
                f"Slug '{slug}' is invalid. Use only lowercase letters, digits, hyphens."
            )
        if Provider.objects.filter(slug=slug).exists():
            raise CommandError(f"Provider '{slug}' already exists.")

        provider = Provider.objects.create(
            slug=slug,
            name=options['name'],
            provider_type=options['provider_type'],
            base_url=options['url'],
            api_key=options['key'],
            default_model=options['default_model'],
            is_active=True,
        )
        self.stdout.write(self.style.SUCCESS(
            f'Provider "{provider.name}" added (slug: {slug})'
        ))
        self.stdout.write(
            f'Test it: python manage.py bm_provider test {slug}'
        )

    def _test(self, options):
        try:
            provider = Provider.objects.get(slug=options['slug'])
        except Provider.DoesNotExist:
            raise CommandError(f"Provider '{options['slug']}' not found.")

        self.stdout.write(f'Testing {provider.name}...')
        try:
            from apps.providers.backends import get_backend
            backend = get_backend(provider)
            model = options['model'] or provider.default_model or ''
            result = backend.test_connection(model=model)
            if result.get('success'):
                self.stdout.write(self.style.SUCCESS(
                    f'Connection OK — response time: {result.get("response_time", "?")}ms'
                ))
                if result.get('models'):
                    self.stdout.write(f'Available models: {", ".join(result["models"][:10])}')
            else:
                self.stdout.write(self.style.ERROR(
                    f'Connection FAILED: {result.get("error", "unknown error")}'
                ))
        except Exception as e:
            raise CommandError(f'Error testing provider: {e}')

    def _models(self, options):
        try:
            provider = Provider.objects.get(slug=options['slug'])
        except Provider.DoesNotExist:
            raise CommandError(f"Provider '{options['slug']}' not found.")

        try:
            from apps.providers.backends import get_backend
            backend = get_backend(provider)
            models = backend.list_models()
            if not models:
                self.stdout.write('No models found.')
                return
            self.stdout.write(self.style.SUCCESS(f'Models from {provider.name}:'))
            for m in models:
                self.stdout.write(f'  {m}')
        except Exception as e:
            raise CommandError(f'Error listing models: {e}')

    def _delete(self, options):
        try:
            provider = Provider.objects.get(slug=options['slug'])
        except Provider.DoesNotExist:
            raise CommandError(f"Provider '{options['slug']}' not found.")
        name = provider.name
        provider.delete()
        self.stdout.write(self.style.SUCCESS(f'Provider "{name}" deleted.'))
