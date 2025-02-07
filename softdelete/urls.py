from django.urls import re_path

from softdelete.views import *

urlpatterns = [
    re_path(r'^changeset/(?P<changeset_pk>\d+?)/undelete/$',
        ChangeSetUpdate.as_view(),
        name="softdelete.changeset.undelete"),
    re_path(r'^changeset/(?P<changeset_pk>\d+?)/$',
        ChangeSetDetail.as_view(),
        name="softdelete.changeset.view"),
    re_path(r'^changeset/$',
        ChangeSetList.as_view(),
        name="softdelete.changeset.list"),
]

import sys
if 'test' in sys.argv:
    from django.contrib import admin
    admin.autodiscover()
    urlpatterns.append(re_path(r'^admin/', admin.site.urls))
