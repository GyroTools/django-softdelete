from django.dispatch import Signal

pre_soft_delete = Signal(providing_args=['instance', 'changeset'])
post_soft_delete = Signal(providing_args=['instance', 'changeset'])
pre_undelete = Signal(providing_args=['instance'])
post_undelete = Signal(providing_args=['instance'])
