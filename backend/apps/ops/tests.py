from unittest.mock import patch

from django.test import SimpleTestCase

from .metrics import snapshot


class MonitoringScopeTests(SimpleTestCase):
    @patch('apps.ops.metrics.query_labels')
    @patch('apps.ops.metrics.query_value')
    def test_snapshot_separates_vm_and_container_metrics(self, query_value, query_labels):
        values = {
            '100-(avg(rate(node_cpu_seconds_total{mode="idle"}[1m]))*100)': 12.5,
            '100-(avg(rate(node_cpu_seconds_total{mode="idle"}[10m]))*100)': 10.0,
            'node_memory_MemTotal_bytes': 16 * 1024**3,
            'node_memory_MemAvailable_bytes': 9 * 1024**3,
            'node_filesystem_size_bytes{mountpoint="/",fstype!~"tmpfs|overlay|squashfs"}': 500 * 1024**3,
            'node_filesystem_avail_bytes{mountpoint="/",fstype!~"tmpfs|overlay|squashfs"}': 300 * 1024**3,
            'node_filesystem_files{mountpoint="/",fstype!~"tmpfs|overlay|squashfs"}': 10000,
            'node_filesystem_files_free{mountpoint="/",fstype!~"tmpfs|overlay|squashfs"}': 9500,
            'time()-node_boot_time_seconds': 3600,
            'node_load1': 0.5,
            'node_load5': 0.4,
            'node_load15': 0.3,
            'count(container_last_seen{image!=""})': 12,
            'sum(container_memory_working_set_bytes{image!=""})': 3 * 1024**3,
            'sum(rate(container_cpu_usage_seconds_total{image!=""}[1m]))': 1.25,
        }
        query_value.side_effect = lambda expression: values.get(expression)

        def labels(expression):
            if expression == 'node_uname_info':
                return {
                    'nodename': 'promptmaster-vm',
                    'release': '6.8.0',
                    'sysname': 'Linux',
                    'machine': 'x86_64',
                }
            if expression == 'cadvisor_version_info':
                return {'dockerVersion': '28.0.0'}
            return {}

        query_labels.side_effect = labels

        data = snapshot()

        self.assertEqual(data['scope'], 'vm')
        self.assertEqual(data['scope_label'], 'Docker-Host-VM')
        self.assertEqual(data['memory_total'], 16 * 1024**3)
        self.assertEqual(data['memory_available'], 9 * 1024**3)
        self.assertEqual(data['memory_used'], 7 * 1024**3)
        self.assertAlmostEqual(data['memory_percent'], 43.75)
        self.assertEqual(data['disk_used'], 200 * 1024**3)
        self.assertAlmostEqual(data['inode_percent'], 5.0)
        self.assertEqual(data['container_count'], 12)
        self.assertEqual(data['container_memory_used'], 3 * 1024**3)
        self.assertEqual(data['container_cpu_cores'], 1.25)
        self.assertEqual(data['host']['hostname'], 'promptmaster-vm')
        self.assertEqual(data['docker_version'], '28.0.0')
