from .models import Cluster


def cluster_context(request):
    clusters = Cluster.objects.all()
    active_cluster_id = request.session.get('active_cluster_id')
    active_cluster = None
    if active_cluster_id:
        try:
            active_cluster = Cluster.objects.get(pk=active_cluster_id)
        except Cluster.DoesNotExist:
            del request.session['active_cluster_id']
    return {
        'all_clusters': clusters,
        'active_cluster': active_cluster,
    }
