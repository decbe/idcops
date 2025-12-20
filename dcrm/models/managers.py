from mptt.managers import TreeManager, TreeQuerySet

from django.db.models import Manager, Q, QuerySet


class BaseTreeQuerySet(TreeQuerySet):
    """Base queryset with datacenter and sharing filtering capabilities"""

    def by_user(self, user):
        """Filter queryset based on user's datacenter access"""
        if user.is_superuser:
            return self

        dc_id = getattr(user, "data_center_id", None)
        if not dc_id:
            return self.none()

        return self.filter(data_center_id=dc_id)

    def shared_only(self):
        """Get only shared resources"""
        return self.filter(shared=True)


class BaseTreeManager(TreeManager.from_queryset(BaseTreeQuerySet)):

    def __init__(self):
        super().__init__()
        self._current_user = None

    def get_queryset(self):
        """
        Get a queryset with appropriate filters and select_related applied
            Ensures that this manager always returns nodes in tree order.
        """
        qs = BaseTreeQuerySet(self.model, using=self._db)

        if self._current_user and not self._current_user.is_superuser:
            qs = qs.by_user(self._current_user)

        if hasattr(self.model, "data_center"):
            qs = qs.select_related("data_center")

        return qs.order_by(self.tree_id_attr, self.left_attr)

    def set_user(self, user):
        """Set current user context"""
        self._current_user = user
        return self

    def shared_only(self):
        """Get only shared resources"""
        return self.get_queryset().shared_only()

    def datacenter_only(self):
        """Get only current datacenter resources (excluding shared)"""
        if not self._current_user:
            return self.none()

        dc_id = getattr(self._current_user, "data_center_id", None)
        if not dc_id:
            return self.none()

        return self.filter(data_center_id=dc_id, shared=False)

    def bulk_create(self, objs, **kwargs):
        """Bulk create with automatic datacenter setting"""
        if self._current_user:
            dc = getattr(self._current_user, "data_center", None)
            if dc:
                for obj in objs:
                    if not getattr(obj, "data_center", None):
                        setattr(obj, "data_center", dc)

        return super().bulk_create(objs, **kwargs)


class BaseQuerySet(QuerySet):
    """Base queryset with datacenter and sharing filtering capabilities"""

    def by_user(self, user):
        """Filter queryset based on user's datacenter access"""
        if user.is_superuser:
            return self

        dc_id = getattr(user, "data_center_id", None)
        if not dc_id:
            return self.none()

        if hasattr(self.model, "shared"):
            return self.filter(Q(data_center_id=dc_id) | Q(shared=True))
        return self.filter(data_center_id=dc_id)

    def shared_only(self):
        """Return only shared resources"""
        return self.filter(shared=True)


class BaseModelManager(Manager.from_queryset(BaseQuerySet)):
    """
    Base model manager with datacenter filtering and user context capabilities.
    Provides:
    - Datacenter filtering
    - Shared resource filtering
    - User context
    """

    def __init__(self):
        super().__init__()
        self._current_user = None

    def get_queryset(self):
        """Get a queryset with user context"""
        qs = super().get_queryset()

        if self._current_user and not self._current_user.is_superuser:
            qs = qs.by_user(self._current_user)

        return qs

    def set_user(self, user):
        """Set current user context"""
        self._current_user = user
        return self
