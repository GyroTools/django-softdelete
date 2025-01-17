from __future__ import unicode_literals

import django

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import query, CASCADE
from django.db import models
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.contenttypes.models import ContentType
from six import python_2_unicode_compatible

from softdelete.settings import send_delete_signal

try:
    from django.contrib.contenttypes.fields import GenericForeignKey
except ImportError:
    from django.contrib.contenttypes.generic import GenericForeignKey
from django.contrib.auth.models import Group, Permission
from django.utils import timezone
import logging
from softdelete.signals import *

try:
    USE_SOFTDELETE_GROUP = settings.USE_SOFTDELETE_GROUP
except:
    USE_SOFTDELETE_GROUP = False


def _determine_change_set(obj, create=True, user=None):
    try:
        qs = SoftDeleteRecord.objects.filter(content_type=ContentType.objects.get_for_model(obj),
                                             object_id=str(obj.pk)).latest('created_date').changeset
        logging.debug("Found changeset via latest recordset")
    except:
        try:
            qs = ChangeSet.objects.filter(content_type=ContentType.objects.get_for_model(obj),
                                          object_id=str(obj.pk),
                                          user=user).latest('created_date')
            logging.debug("Found changeset")
        except:
            if create:
                qs = ChangeSet.objects.create(content_type=ContentType.objects.get_for_model(obj),
                                              object_id=str(obj.pk),
                                              user=user)
                logging.debug("Creating changeset")
            else:
                logging.debug("Raising ObjectDoesNotExist")
                raise ObjectDoesNotExist
    return qs


def _get_pks(queryset, changesets=None):
    changesets = changesets or {}
    changesets_pks = list(changesets.keys())
    changesets_pks = [str(pk) for pk in changesets_pks]
    pks = list(queryset.values_list('pk', flat=True))
    pks = [str(pk) for pk in pks]
    new_pks = list(set(pks) - set(changesets_pks))
    return pks, new_pks


def _get_existing_changesets(queryset, changesets=None, user=None):
    _, new_pks = _get_pks(queryset, changesets=changesets)

    existing_changesets = ChangeSet.objects.filter(content_type=ContentType.objects.get_for_model(queryset.model),
                                                   object_id__in=new_pks, user=user)
    for ecs in existing_changesets:
        changesets[ecs.object_id] = ecs

    return changesets


def _determine_change_set_for_queryset(queryset, cs=None, changesets=None, user=None):
    changesets = changesets or {}
    converted_changesets = {str(key): value for key, value in changesets.items()}
    changesets = converted_changesets

    pks, new_pks = _get_pks(queryset, changesets=changesets)

    content_type = ContentType.objects.get_for_model(queryset.model)
    existing_records_cs = SoftDeleteRecord.objects.filter(content_type=content_type,
                                                           object_id__in=pks).select_related('changeset')
    existing_records = [r.id for r in existing_records_cs]

    if cs:
        changesets = {pk: cs for pk in pks}
        return changesets, existing_records

    if not new_pks or len(new_pks) == 0:
        return changesets, existing_records

    for r in existing_records_cs:
        changesets[r.object_id] = r.changeset

    _get_existing_changesets(queryset, changesets, user=user)

    changesets_to_create = []
    for obj in queryset:
        if not str(obj.pk) in changesets:
            changesets_to_create.append(ChangeSet(content_type=ContentType.objects.get_for_model(obj),
                                                  object_id=str(obj.pk), user=user))

    ChangeSet.objects.bulk_create(changesets_to_create)

    _get_existing_changesets(queryset, changesets, user=user)

    return changesets, existing_records


class SoftDeleteQuerySet(query.QuerySet):
    def all_with_deleted(self):
        qs = super(SoftDeleteQuerySet, self).all()
        qs.__class__ = SoftDeleteQuerySet
        return qs

    def _handle_cascade(self, queryset, changesets):
        # Retrieve related fields once
        instance = queryset.first()
        all_related = [
            f for f in instance._meta.get_fields()
            if (f.one_to_many or f.one_to_one)
               and f.auto_created and not f.concrete
        ]

        # Handle related objects in bulk
        for related_field in all_related:
            self._do_delete(queryset, changesets, related_field)

        logging.debug("FINISHED SOFT DELETING RELATED OBJECTS FOR QUERYSET")

    def _do_delete(self, queryset, changesets, related, force_policy=None):
        rel = related.get_accessor_name()

        relation_policy = queryset.model.softdelete_relation_policy.get(rel)
        if force_policy:
            relation_policy = force_policy

        # if the policy for this relation is set to SOFT_DELETE
        # we should just end processing of this relation
        if relation_policy == SoftDeleteObject.DO_NOTHING:
            return

            # Get related manager name
            related_manager_name = related.get_accessor_name()

            if related.one_to_one:
                # For one-to-one relationships, handle each related object individually
                related_objects = [getattr(instance, related_manager_name) for instance in queryset if
                                   hasattr(instance, related_manager_name)]
                for obj in related_objects:
                    if relation_policy == self.SET_NULL:
                        setattr(obj, related.field.name, None)
                        obj.save()
                    else:
                        if isinstance(obj, SoftDeleteObject):
                            obj.delete(changeset=changeset, force_policy=force_policy)
                        else:
                            obj.delete()
            elif related.one_to_many:
                # For one-to-many relationships, handle related objects in bulk
                related_queryset = related.related_model.objects.filter(**{related.field.name + '__in': queryset})
                if relation_policy == self.SET_NULL:
                    related_queryset.update(**{related.field.name: None})
                else:
                    if issubclass(related.related_model, SoftDeleteObject):
                        related_queryset.delete(changeset=changeset, force_policy=force_policy)
                    else:
                        related_queryset.delete()

        for instance in queryset:
            if not hasattr(instance, rel):
                continue

            cs = changesets[str(instance.pk)]
            delete_kwargs = {'changeset': cs}
            if force_policy:
                delete_kwargs['force_policy'] = force_policy

            if related.one_to_one:
                obj = getattr(instance, rel)
                if relation_policy == SoftDeleteObject.SET_NULL:
                    setattr(obj, related.field.name, None)
                    obj.save()
                else:
                    if isinstance(obj, SoftDeleteObject):
                        obj.delete(**delete_kwargs)
                    else:
                        obj.delete()
            elif related.one_to_many:
                if relation_policy == SoftDeleteObject.SET_NULL:
                    getattr(instance, rel).all().update(**{related.field.name: None})
                else:
                    qs = getattr(instance, rel).all()
                    if isinstance(qs, SoftDeleteQuerySet):
                        qs.delete(**delete_kwargs)
                    else:
                        qs.delete()

    def delete(self, using='default', *args, **kwargs):
        if not len(self):
            return

        # if we are forcing a hard delete, we should not create any records. Just call the default queryset delete
        # method
        policy = kwargs.get('force_policy', SoftDeleteObject.softdelete_policy)
        if policy == SoftDeleteObject.HARD_DELETE:
            pre_delete_queryset.send(sender=self.model,
                                          queryset=self,
                                          using=using)
            kwargs.pop('force_policy', None)
            super().delete()
            post_delete_queryset.send(sender=self.model,
                                 queryset=self,
                                 using=using)
            return

        already_deleted = self.filter(deleted_at__isnull=False)
        to_delete = self.filter(deleted_at=None)

        user = kwargs.get('user', None)
        cs = kwargs.get('changeset')
        changesets = kwargs.get('changesets')
        logging.debug("STARTING QUERYSET SOFT-DELETE: %s. %s", self, len(self))

        # mb: bulk create all records first, then delete all objects
        changesets, existing_records = _determine_change_set_for_queryset(to_delete, cs=cs, changesets=changesets, user=user)

        pre_soft_delete_queryset.send(sender=self.model,
                                      queryset=self,
                                      changesets=changesets,
                                      using=using)

        records_to_create = []
        for obj in to_delete:
            if not obj.pk in existing_records:
                cur_cs = cs or changesets[str(obj.pk)]
                records_to_create.append(SoftDeleteRecord(changeset=cur_cs,
                                         content_type=ContentType.objects.get_for_model(obj),
                                         object_id=str(obj.pk)))
        SoftDeleteRecord.objects.bulk_create(records_to_create)

        # handle cascade delete
        if policy == SoftDeleteObject.SOFT_DELETE_CASCADE:
            self._handle_cascade(to_delete, changesets)

        to_delete.update(deleted_at=timezone.now())

        if already_deleted.count() > 0:
            changesets_to_delete = ChangeSet.objects.get(
                content_type=ContentType.objects.get_for_model(self),
                object_id=list(already_deleted.values_list('pk', flat=True)),
                user=user)
            changesets_to_delete.delete()
            already_deleted.delete(force_policy=SoftDeleteObject.HARD_DELETE)

        post_soft_delete_queryset.send(sender=self.model,
                                       queryset=self,
                                       changesets=changesets,
                                       using=using)

    def undelete(self, using='default', *args, **kwargs):
        logging.debug("UNDELETING %s", self)
        for obj in self:
            cs = _determine_change_set(obj)
            cs.undelete()
        logging.debug("FINISHED UNDELETING %s", self)


class SoftDeleteManager(models.Manager):

    def _get_base_queryset(self):
        '''
        Convenience method for grabbing the base query set. Accounts for the
        deprecation of get_query_set in Django 18.
        '''

        if django.VERSION >= (1, 8, 0, 'final', 0):
            return super(SoftDeleteManager, self).get_queryset()
        else:
            return super(SoftDeleteManager, self).get_query_set()

    def _get_self_queryset(self):
        '''
        Convenience method for grabbing the query set. Accounts for the
        deprecation of get_query_set in Django 18.
        '''

        if django.VERSION >= (1, 8, 0, 'final', 0):
            return self.get_queryset()
        else:
            return self.get_query_set()

    def get_query_set(self):
        qs = super(SoftDeleteManager, self).get_query_set().filter(
            deleted_at__isnull=True)
        qs.__class__ = SoftDeleteQuerySet
        return qs

    def get_queryset(self):
        qs = super(SoftDeleteManager, self).get_queryset().filter(
            deleted_at__isnull=True)
        qs.__class__ = SoftDeleteQuerySet
        return qs

    def all_with_deleted(self, prt=False):
        if hasattr(self, 'core_filters'):  # it's a RelatedManager
            qs = self._get_base_queryset().filter(**self.core_filters)
        else:
            qs = self._get_base_queryset()
        qs.__class__ = SoftDeleteQuerySet
        return qs

    def deleted_set(self):
        qs = self._get_base_queryset().filter(deleted_at__isnull=0)
        qs.__class__ = SoftDeleteQuerySet
        return qs

    def get(self, *args, **kwargs):
        return self._get_self_queryset().get(*args, **kwargs)

    def filter(self, *args, **kwargs):
        qs = self._get_self_queryset().filter(*args, **kwargs)
        qs.__class__ = SoftDeleteQuerySet
        return qs


class SoftDeleteObject(models.Model):
    SOFT_DELETE = 0
    SOFT_DELETE_CASCADE = 1
    DO_NOTHING = 2
    SET_NULL = 3
    HARD_DELETE = 4

    softdelete_policy = SOFT_DELETE_CASCADE

    # In some cases we want to disable cascade for only some relations
    # in this case we should use relation name as key and a DO_NOTHING or
    # SOFT_DELETE_CASCADE as a policy for only this one relation
    # example:
    # softdelete_relation_policy = {'buns': DO_NOTHING}
    softdelete_relation_policy = {}

    deleted_at = models.DateTimeField(blank=True, null=True, default=None)
    objects = SoftDeleteManager()

    class Meta:
        abstract = True
        permissions = (
            ('can_undelete', 'Can undelete this object'),
            )

    def __init__(self, *args, **kwargs):
        super(SoftDeleteObject, self).__init__(*args, **kwargs)
        self.__dirty = False

    def get_deleted(self):
        return self.deleted_at is not None

    def set_deleted(self, d):
        """Called via the admin interface (if user checks the "deleted" checkox)"""
        if d and not self.deleted_at:
            self.__dirty = True
            self.deleted_at = timezone.now()
        elif not d and self.deleted_at:
            self.__dirty = True
            self.deleted_at = None

    deleted = property(get_deleted, set_deleted)

    def _do_delete(self, changeset, related, force_policy=None):
        rel = related.get_accessor_name()

        relation_policy = self.softdelete_relation_policy.get(rel)
        if force_policy:
            relation_policy = force_policy

        # if the policy for this relation is set to SOFT_DELETE
        # we should just end processing of this relation
        if relation_policy == self.DO_NOTHING:
            return

        # Sometimes there is nothing to delete
        if not hasattr(self, rel):
            return

        delete_kwargs = {
            'changeset': changeset
        }
        if force_policy:
            delete_kwargs['force_policy'] = force_policy

        if related.one_to_one:
            obj = getattr(self, rel)
            if relation_policy == self.SET_NULL:
                setattr(obj, related.field.name, None)
                obj.save()
            else:
                if isinstance(obj, SoftDeleteObject):
                    obj.delete(**delete_kwargs)
                else:
                    obj.delete()
        elif related.one_to_many:
            if relation_policy == self.SET_NULL:
                getattr(self, rel).all().update(**{related.field.name: None})
            else:
                qs = getattr(self, rel).all()
                if isinstance(qs, SoftDeleteQuerySet):
                    qs.delete(**delete_kwargs)
                else:
                    qs.delete()

    def delete(self, *args, **kwargs):
        """
        Delete this instance.

        If deleted_at is not set a soft delete will be done.

        kwargs:
            force_policy: override the softdelete_policy (only affect in case of a soft delete)
            user: bind the ChangeSet to the given user model.
            changeset: use the given ChangeSet to add SoftDeleteRecords (only affect in case of a soft delete)
        """
        policy = kwargs.get('force_policy', self.softdelete_policy)
        user = kwargs.get('user', None)

        if policy in [self.HARD_DELETE]:
            logging.debug("HARD DELETEING forced by policy type %s, %s", type(self), self)
            kwargs.pop('user', None)
            kwargs.pop('force_policy', None)
            super(SoftDeleteObject, self).delete(*args, **kwargs)

        elif self.deleted_at:
            logging.debug("HARD DELETEING type %s, %s", type(self), self)
            try:
                cs = ChangeSet.objects.get(
                    content_type=ContentType.objects.get_for_model(self),
                    object_id=self.pk,
                    user=user)
                cs.delete()
                kwargs.pop('user', None)
                super(SoftDeleteObject, self).delete(*args, **kwargs)
            except Exception as e:
                try:
                    cs = kwargs.get('changeset') or _determine_change_set(self, user=user)
                    rs = SoftDeleteRecord.objects.get(
                        changeset=cs,
                        content_type=ContentType.objects.get_for_model(self),
                        object_id=self.pk)
                    if rs.changeset.soft_delete_records.count() == 1:
                        cs.delete()
                    else:
                        rs.delete()
                    super(SoftDeleteObject, self).delete(*args, **kwargs)
                except Exception as e:
                    logging.error(f'Failed to delete object: {self}: {e}')
                except:
                    logging.error(f'Failed to delete object: {self}: ')
        elif policy in [self.SOFT_DELETE, self.SOFT_DELETE_CASCADE]:
            using = kwargs.get('using', settings.DATABASES['default'])
            cs = kwargs.get('changeset') or _determine_change_set(self, user=user)

            if send_delete_signal():
                models.signals.pre_delete.send(sender=self.__class__,
                                               instance=self,
                                               using=using)
            pre_soft_delete.send(sender=self.__class__,
                                 instance=self,
                                 changeset=cs,
                                 using=using)
            logging.debug('SOFT DELETING type: %s, %s', type(self), self)

            SoftDeleteRecord.objects.get_or_create(
                changeset=cs,
                content_type=ContentType.objects.get_for_model(self),
                object_id=self.pk)
            self.deleted_at = timezone.now()
            self.save()

            if policy == self.SOFT_DELETE_CASCADE:
                all_related = [
                    f for f in self._meta.get_fields()
                    if (f.one_to_many or f.one_to_one)
                    and f.auto_created and not f.concrete
                ]
                for x in all_related:
                    self._do_delete(cs, x)
                logging.debug("FINISHED SOFT DELETING RELATED %s", self)

                if send_delete_signal():
                    models.signals.post_delete.send(sender=self.__class__,
                                                    instance=self,
                                                    using=using)
                post_soft_delete.send(sender=self.__class__,
                                      instance=self,
                                      changeset=cs,
                                      using=using)

    def _do_undelete(self, soft_delete_model, using='default'):
        pre_undelete.send(sender=self.__class__,
                          instance=self,
                          soft_delete_model=soft_delete_model,
                          using=using)
        self.deleted_at = None
        self.save()
        post_undelete.send(sender=self.__class__,
                           instance=self,
                           using=using)

    def undelete(self, using='default', *args, **kwargs):
        logging.debug('UNDELETING %s' % self)
        user = kwargs.get('user', None)
        cs = kwargs.get('changeset') or _determine_change_set(self, False, user=user)
        cs.undelete(using)
        logging.debug('FINISHED UNDELETING RELATED %s', self)

    def save(self, **kwargs):
        super(SoftDeleteObject, self).save(**kwargs)
        if self.__dirty:
            self.__dirty = False
            if not self.deleted:
                self.undelete()
            else:
                self.delete()


class ChangeSetManager(models.Manager):
    def for_user(self, user):
        return self.filter(user=user)


@python_2_unicode_compatible
class ChangeSet(models.Model):
    created_date = models.DateTimeField(default=timezone.now)
    content_type = models.ForeignKey(ContentType, on_delete=CASCADE)
    object_id = models.CharField(max_length=100)
    record = GenericForeignKey('content_type', 'object_id')

    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, blank=True, null=True)

    class Meta:
        index_together = [
            ("content_type", "object_id"),
        ]

    objects = ChangeSetManager()

    def get_content(self):
        model_class = self.content_type.model_class()
        if isinstance(model_class.objects, SoftDeleteManager):
            return model_class.objects.all_with_deleted().get(pk=self.object_id)
        return model_class.objects.get(pk=self.object_id)

    def set_content(self, obj):
        self.record = obj

    def undelete(self, using='default'):
        logging.debug("CHANGESET UNDELETE: %s" % self)
        try:
            self.content._do_undelete(self, using)
        except Exception as e:
            #  ToDo: Is there a general DoesNotExists Exception?
            logging.warn(f'CHANGESET UNDELETE: Failed to delete changeset content: {e}')

        for related in self.soft_delete_records.all():
            related.undelete(using)

        self.delete()
        logging.debug("FINISHED CHANGESET UNDELETE: %s", self)

    def __str__(self):
        return 'Changeset: %s, %s' % (self.created_date, self.record)

    content = property(get_content, set_content)

@python_2_unicode_compatible
class SoftDeleteRecord(models.Model):
    changeset = models.ForeignKey(ChangeSet, related_name='soft_delete_records', on_delete=CASCADE)
    created_date = models.DateTimeField(default=timezone.now)
    content_type = models.ForeignKey(ContentType, on_delete=CASCADE)
    object_id = models.CharField(max_length=100)
    record = GenericForeignKey('content_type', 'object_id')

    class Meta:
        ordering = ('id', )
        unique_together = (('changeset', 'content_type', 'object_id'),)
        index_together = [
            ("content_type", "object_id"),
        ]

    def get_content(self):
        model_class = self.content_type.model_class()
        if isinstance(model_class.objects, SoftDeleteManager):
            return model_class.objects.all_with_deleted().get(pk=self.object_id)
        return model_class.objects.get(pk=self.object_id)

    def set_content(self, obj):
        self.record = obj

    def undelete(self, using='default'):
        try:
            self.content._do_undelete(self, using)
        except Exception:
            logging.warn(f'SoftDeleteRecord UNDELETE: Failed to delete SoftDeleteRecord content: {e}')

    def __str__(self):
        return u'SoftDeleteRecord: (%s), (%s/%s), %s' % (
            self.content,
            self.content_type,
            self.object_id,
            self.changeset.created_date)

    content = property(get_content, set_content)


def assign_permissions(user_or_group):
    for model in ['ChangeSet', 'SoftDeleteRecord']:
        ct = ContentType.objects.get(app_label="softdelete",
                                     model=model.lower())
        p, pc = Permission.objects.get_or_create(
            name="Can undelete a soft-deleted object",
            codename="can_undelete",
            content_type=ct)
        permissions = [p]
        for permission in ['add_%s' % model.lower(),
                           'change_%s' % model.lower(),
                           'delete_%s' % model.lower(),
                           'can_undelete']:
            for perm_obj in Permission.objects.filter(codename=permission):
                permissions.append(perm_obj)
        perm_list = getattr(user_or_group, 'permissions',
                            getattr(user_or_group, 'user_permissions'))
        [perm_list.add(x) for x in permissions]
        user_or_group.save()
    return user_or_group


def create_group():
    if USE_SOFTDELETE_GROUP:
        gr, cr = Group.objects.get_or_create(name='Softdelete User')
        if cr:
            assign_permissions(gr)
        return gr
