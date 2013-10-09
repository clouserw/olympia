from django.core.management.base import BaseCommand

from celeryutils import task

import amo
from amo.decorators import write
from amo.utils import chunked
from comm.models import CommunicationNote, CommunicationThread
from devhub.models import ActivityLog, AppLog

import mkt.constants.comm as cmb


class Command(BaseCommand):
    help = ('Migrates ActivityLog objects to CommunicationNote objects. '
            'Meant for one time run only.')

    def handle(self, *args, **options):
        activity_ids = AppLog.objects.values_list('activity_log', flat=True)
        logs = (ActivityLog.objects.filter(
            pk__in=list(activity_ids), action__in=amo.LOG_REVIEW_QUEUE)
            .order_by('created'))

        for log_chunk in chunked(logs, 100):
            _migrate_activity_log.delay(log_chunk)


@task
@write
def _migrate_activity_log(logs, **kwargs):
    """For migrate_activity_log.py script."""
    for log in logs:
        action = _action_map(log.action)

        # Filter or create_comm_note.
        thread, tc = CommunicationThread.objects.get_or_create(
            addon=log.arguments[0], version=log.arguments[1])

        note, nc = CommunicationNote.objects.get_or_create(
            thread=thread, note_type=action, author=log.user,
            body=log.details.get('comments', ''),
            # Developers should not see escalate/reviewer comments.
            read_permission_developer=action not in (cmb.ESCALATION,
                                                     cmb.REVIEWER_COMMENT))
        if nc:
            note.update(created=log.created)


def _action_map(activity_action):
    """Maps ActivityLog action ids to Commbadge note types."""
    return {
        amo.LOG.APPROVE_VERSION.id: cmb.APPROVAL,
        amo.LOG.APPROVE_VERSION_WAITING.id: cmb.APPROVAL,
        amo.LOG.REJECT_VERSION.id: cmb.REJECTION,
        amo.LOG.APP_DISABLED.id: cmb.DISABLED,
        amo.LOG.REQUEST_INFORMATION.id: cmb.MORE_INFO_REQUIRED,
        amo.LOG.ESCALATE_VERSION.id: cmb.ESCALATION,
        amo.LOG.ESCALATION_CLEARED.id: cmb.ESCALATION,
        amo.LOG.ESCALATED_HIGH_ABUSE.id: cmb.ESCALATION,
        amo.LOG.ESCALATED_HIGH_REFUNDS.id: cmb.ESCALATION,
        amo.LOG.COMMENT_VERSION.id: cmb.REVIEWER_COMMENT,
        amo.LOG.WEBAPP_RESUBMIT.id: cmb.RESUBMISSION,
    }.get(activity_action, cmb.NO_ACTION)
