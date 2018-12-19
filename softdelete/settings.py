from django.conf import settings

_default = {
    'SEND_DELETE_SIGNAL': True
}


def send_delete_signal():
    """
    If true the pre_delete and post_delete signals will be sent in case of a soft delete and an hard delete. 
    If false the pre_delete and post_delete signals will only be sent in case of a hard delete.

    """
    try:
        return settings.SOFTDELETE['SEND_DELETE_SIGNAL']
    except:
        return _default['SEND_DELETE_SIGNAL']
