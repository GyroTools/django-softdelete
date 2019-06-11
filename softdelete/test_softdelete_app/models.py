from django.db import models
from django.contrib import admin

from softdelete.models import *
from softdelete.admin import *

class TestModelOne(SoftDeleteObject):
    extra_bool = models.BooleanField(default=False)
    
class TestModelTwo(SoftDeleteObject):
    extra_int = models.IntegerField()
    tmo = models.ForeignKey(TestModelOne, related_name='tmts', on_delete=models.CASCADE)
    
class TestModelThree(SoftDeleteObject):
    tmos = models.ManyToManyField(TestModelOne, through='TestModelThrough')
    extra_int = models.IntegerField(blank=True, null=True)

class TestModelThrough(SoftDeleteObject):
    tmo1 = models.ForeignKey(TestModelOne, related_name="left_side", on_delete=models.CASCADE)
    tmo3 = models.ForeignKey(TestModelThree, related_name='right_side', on_delete=models.CASCADE)

class TestModelSafeDeleteCascade(SoftDeleteObject):
    softdelete_policy = SoftDeleteObject.SOFT_DELETE_CASCADE
    extra_int = models.IntegerField()

class TestModelSoftDelete(SoftDeleteObject):
    softdelete_policy = SoftDeleteObject.SOFT_DELETE
    parent = models.ForeignKey(TestModelSafeDeleteCascade, related_name='x', on_delete=models.CASCADE)

class TestModelSoftDeleteOnRelationLevelParent(SoftDeleteObject):
    softdelete_relation_policy = {
        'x': SoftDeleteObject.DO_NOTHING,
        'z': SoftDeleteObject.SET_NULL
    }
    extra_int = models.IntegerField()

class TestModelSoftDeleteOnRelationLevelChild(SoftDeleteObject):
    parent = models.ForeignKey(
        TestModelSoftDeleteOnRelationLevelParent,
        related_name='x', on_delete=models.CASCADE
    )

class TestModelSoftDeleteOnRelationLevelSecondChild(SoftDeleteObject):
    parent = models.ForeignKey(
        TestModelSoftDeleteOnRelationLevelParent,
        related_name='y', on_delete=models.CASCADE
    )

class TestModelSoftDeleteOnRelationLevelChildSetNull(SoftDeleteObject):
    parent = models.ForeignKey(
        TestModelSoftDeleteOnRelationLevelParent,
        blank=True, null=True,
        related_name='z',
        on_delete = models.CASCADE
    )

class TestModelOneToOneRelationWithNonSoftDeleteObject(models.Model):
    one_to_one = models.OneToOneField(
        TestModelSoftDeleteOnRelationLevelParent,
        related_name='xyz', on_delete=models.CASCADE
    )


class TestModelDefault(SoftDeleteObject):
    parent = models.ForeignKey(TestModelSoftDelete, related_name='y')


admin.site.register(TestModelOne, SoftDeleteObjectAdmin)
admin.site.register(TestModelTwo, SoftDeleteObjectAdmin)
admin.site.register(TestModelThree, SoftDeleteObjectAdmin)
admin.site.register(TestModelThrough, SoftDeleteObjectAdmin)
admin.site.register(TestModelSafeDeleteCascade, SoftDeleteObjectAdmin)
admin.site.register(TestModelSoftDelete, SoftDeleteObjectAdmin)
admin.site.register(TestModelDefault, SoftDeleteObjectAdmin)
admin.site.register(TestModelSoftDeleteOnRelationLevelParent, SoftDeleteObjectAdmin)
admin.site.register(TestModelSoftDeleteOnRelationLevelChild, SoftDeleteObjectAdmin)
admin.site.register(TestModelSoftDeleteOnRelationLevelSecondChild, SoftDeleteObjectAdmin)
