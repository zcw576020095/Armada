from .models import Cluster
from .views import _visible_clusters


def cluster_context(request):
    # 全站下拉列表只展示当前用户可见的集群（管理员看全部，普通用户按已分配权限过滤）
    if request.user.is_authenticated:
        clusters = _visible_clusters(request.user)
    else:
        clusters = Cluster.objects.none()

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
