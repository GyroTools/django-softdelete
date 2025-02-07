from django.dispatch import Signal

pre_soft_delete = Signal()
post_soft_delete = Signal()
pre_undelete = Signal()
post_undelete = Signal()
pre_soft_delete_queryset = Signal()
post_soft_delete_queryset = Signal()
pre_delete_queryset = Signal()
post_delete_queryset = Signal()
