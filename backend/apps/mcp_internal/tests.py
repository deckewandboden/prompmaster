import json

from django.core.management import call_command
from django.test import Client, TestCase

from apps.core.security import token_pair
from apps.integrations.models import ServiceAccount
from apps.prompts.models import PromptVersion


class InternalMcpTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_prompt_catalog', verbosity=0)
        cls.raw, hashed = token_pair()
        cls.account = ServiceAccount.objects.create(
            name='mcp-tests', token_hash=hashed, scopes=['prompt.read', 'prompt.draft', 'prompt.test', 'ops.read']
        )

    def setUp(self):
        self.client = Client(HTTP_AUTHORIZATION=f'Bearer {self.raw}')

    def rpc(self, method, params=None, request_id=1, **extra):
        body = {'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params or {}}
        return self.client.post('/api/v1/mcp/', data=json.dumps(body), content_type='application/json', **extra)

    def test_health_requires_token_and_reports_exact_catalog(self):
        self.assertEqual(Client().get('/api/v1/mcp/health/').status_code, 401)
        response = self.client.get('/api/v1/mcp/health/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['definitions'], 194)
        self.assertFalse(data['publish_tool'])
        self.assertFalse(data['delete_tool'])

    def test_initialize_and_tools_list(self):
        response = self.rpc('initialize')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['result']['protocolVersion'], '2025-03-26')
        tools = self.rpc('tools/list').json()['result']['tools']
        self.assertEqual({tool['name'] for tool in tools}, {'prompt.read', 'prompt.draft', 'prompt.test'})

    def test_sse_transport_is_supported(self):
        response = self.rpc('ping', HTTP_ACCEPT='text/event-stream')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/event-stream'))

    def test_publish_and_delete_are_not_exposed(self):
        for name in ('prompt.publish', 'prompt.delete'):
            response = self.rpc('tools/call', {'name': name, 'arguments': {}})
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()['error']['code'], -32601)

    def test_read_draft_and_test_tools(self):
        read = self.rpc('tools/call', {'name': 'prompt.read', 'arguments': {'task_id': 'PM20-001'}})
        self.assertEqual(read.status_code, 200)
        self.assertFalse(read.json()['result']['isError'])

        draft = self.rpc('tools/call', {'name': 'prompt.draft', 'arguments': {'task_id': 'PM20-001'}})
        payload = json.loads(draft.json()['result']['content'][0]['text'])
        self.assertTrue(payload['human_review_required'])
        version = PromptVersion.objects.get(pk=payload['version_id'])
        self.assertEqual(version.lifecycle, 'DRAFT')

        tested = self.rpc('tools/call', {'name': 'prompt.test', 'arguments': {'version_id': str(version.id)}})
        result = json.loads(tested.json()['result']['content'][0]['text'])
        self.assertTrue(result['ok'])
        self.assertEqual(result['total'], 1)
