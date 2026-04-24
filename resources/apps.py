from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class ResourcesConfig(AppConfig):
    name = 'resources'

    def ready(self):
        import os
        if os.environ.get('RUN_MAIN') == 'true' or 'runserver' not in os.sys.argv:
            self._start_sync_services()

    def _start_sync_services(self):
        try:
            from clusters.models import Cluster
            from resources.sync_service import start_sync_for_cluster

            for cluster in Cluster.objects.filter(status='online'):
                try:
                    start_sync_for_cluster(cluster)
                    logger.info(f'Sync service started for cluster: {cluster.name}')
                except Exception as e:
                    logger.error(f'Failed to start sync for {cluster.name}: {e}')
        except Exception as e:
            logger.error(f'Failed to initialize sync services: {e}')
