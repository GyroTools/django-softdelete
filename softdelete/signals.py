from django.dispatch import Signal

pre_soft_delete = Signal(providing_args=['instance', 'changeset'])
post_soft_delete = Signal(providing_args=['instance', 'changeset'])
pre_undelete = Signal(providing_args=['instance', 'soft_delete_model'])
post_undelete = Signal(providing_args=['instance'])
pre_soft_delete_queryset = Signal(providing_args=['queryset', 'changesets'])
post_soft_delete_queryset = Signal(providing_args=['queryset', 'changesets'])
pre_delete_queryset = Signal(providing_args=['queryset'])
post_delete_queryset = Signal(providing_args=['queryset'])
