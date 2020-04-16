from django.dispatch import Signal

pre_soft_delete = Signal(providing_args=['instance', 'changeset'])
post_soft_delete = Signal(providing_args=['instance', 'changeset'])
pre_undelete = Signal(providing_args=['instance', 'soft_delete_model'])
post_undelete = Signal(providing_args=['instance'])
