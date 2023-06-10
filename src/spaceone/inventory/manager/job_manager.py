import abc
import logging

from datetime import datetime, timedelta

from spaceone.core.manager import BaseManager
from spaceone.inventory.model.job_model import Job
from spaceone.inventory.error import *

_LOGGER = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 2000


class JobManager(BaseManager):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.job_model: Job = self.locator.get_model('Job')

    def create_job(self, collector_vo, params):
        """ Create Job for collect method
        Args:
            collector_vo: collector model
            params(dict): {
                'collector_id': str,
                'secret_id': str,
                'domain_id': str
            }
        Returns: job_vo
        """
        job_params = params.copy()
        job_params['collector'] = collector_vo
        return self.job_model.create(job_params)

    def update(self, job_id, params, domain_id):
        job_vo = self.get_job(job_id, domain_id)
        return self.update_job_by_vo(params, job_vo)

    def delete(self, job_id, domain_id):
        job_vo = self.get_job(job_id, domain_id)
        job_vo.delete()

    def get_job(self, job_id, domain_id, only=None):
        return self.job_model.get(job_id=job_id, domain_id=domain_id, only=only)

    def list_jobs(self, query):
        return self.job_model.query(**query)

    def analyze_jobs(self, query):
        return self.job_model.analyze(**query)

    def stat_jobs(self, query):
        return self.job_model.stat(**query)

    def decrease_remained_tasks(self, job_id, domain_id):
        job_vo: Job = self.get_job(job_id, domain_id)
        return self.decrease_remained_tasks_by_vo(job_vo)

    def decrease_remained_tasks_by_vo(self, job_vo: Job):
        job_vo = job_vo.decrement('remained_tasks')

        if job_vo.remained_tasks == 0:
            if job_vo.mark_error == 0:
                self.make_success_by_vo(job_vo)
            else:
                self.make_error_by_vo(job_vo)

        if job_vo.remained_tasks < 0:
            _LOGGER.debug(f'[decrease_remained_tasks] {job_vo.job_id}, {job_vo.remained_tasks}')
            raise ERROR_JOB_UPDATE(param='remained_tasks')

        return job_vo

    def add_error(self, job_id, domain_id, error_code, msg, additional=None):
        """
        error_info (dict): {
            'error_code': str,
            'message': str,
            'additional': dict
        }
        """

        message = repr(msg)
        error_info = {'error_code': error_code, 'message': message[:MAX_MESSAGE_LENGTH]}

        if additional:
            error_info['additional'] = additional

        job_vo = self.get_job(job_id, domain_id)
        job_vo.append('errors', error_info)
        self.mark_error_by_vo(job_vo)
        return job_vo

    def update_job_timeout_by_hour(self, hour, status, domain_id):
        created_at = datetime.utcnow() - timedelta(hours=hour)
        query = {
            'filter': [
                {'k': 'created_at', 'v': created_at, 'o': 'lt'},
                {'k': 'domain_id', 'v': domain_id, 'o': 'eq'},
                {'k': 'status', 'v': ['CREATED', 'IN_PROGRESS'], 'o': 'in'}
            ]
        }

        jobs, total_count = self.list_jobs(query)
        for job in jobs:
            self.make_timeout_by_vo(job)

    def make_inprogress_by_vo(self, job_vo):
        job_state_machine = JobStateMachine(job_vo)
        job_state_machine.inprogress()
        self._update_job_status_by_vo(job_vo, job_state_machine.get_status())

    def make_success_by_vo(self, job_vo):
        job_state_machine = JobStateMachine(job_vo)
        job_state_machine.success()
        self._update_job_status_by_vo(job_vo, job_state_machine.get_status())

    def make_canceled_by_vo(self, job_vo):
        job_state_machine = JobStateMachine(job_vo)
        job_state_machine.canceled()
        self._update_job_status_by_vo(job_vo, job_state_machine.get_status())

    def make_error_by_vo(self, job_vo):
        job_state_machine = JobStateMachine(job_vo)
        job_state_machine.error()
        self._update_job_status_by_vo(job_vo, job_state_machine.get_status())

    def make_timeout_by_vo(self, job_vo):
        job_state_machine = JobStateMachine(job_vo)
        job_state_machine.timeout()
        self._update_job_status_by_vo(job_vo, job_state_machine.get_status())

    ###################
    # Update by job_id
    ###################
    def make_inprogress(self, job_id, domain_id):
        job_vo = self.get_job(job_id, domain_id)
        job_state_machine = JobStateMachine(job_vo)
        job_state_machine.inprogress()
        self._update_job_status_by_vo(job_vo, job_state_machine.get_status())

    def make_success(self, job_id, domain_id):
        job_vo = self.get_job(job_id, domain_id)
        job_state_machine = JobStateMachine(job_vo)
        job_state_machine.success()
        self._update_job_status_by_vo(job_vo, job_state_machine.get_status())

    def make_canceled(self, job_id, domain_id):
        job_vo = self.get_job(job_id, domain_id)
        job_state_machine = JobStateMachine(job_vo)
        job_state_machine.canceled()
        self._update_job_status_by_vo(job_vo, job_state_machine.get_status())

    def make_error(self, job_id, domain_id):
        job_vo = self.get_job(job_id, domain_id)
        job_state_machine = JobStateMachine(job_vo)
        job_state_machine.error()
        self._update_job_status_by_vo(job_vo, job_state_machine.get_status())

    def make_timeout(self, job_id, domain_id):
        job_vo = self.get_job(job_id, domain_id)
        job_state_machine = JobStateMachine(job_vo)
        job_state_machine.timeout()
        self._update_job_status_by_vo(job_vo, job_state_machine.get_status())

    def is_canceled(self, job_id, domain_id):
        job_vo = self.get_job(job_id, domain_id)
        job_state_machine = JobStateMachine(job_vo)
        if job_state_machine.get_status() == CANCELED:
            return True
        return False

    def check_cancel(self, job_id, domain_id):
        job_vo = self.get_job(job_id, domain_id)
        job_state_machine = JobStateMachine(job_vo)
        job_status = job_state_machine.get_status()

        if job_status == CANCELED or job_status == TIMEOUT:
            return True
        return False

    def mark_error(self, job_id, domain_id):
        job_vo = self.get_job(job_id, domain_id)
        job_vo.update({'mark_error': 1})

    @staticmethod
    def mark_error_by_vo(job_vo):
        job_vo.update({'mark_error': 1})

    @staticmethod
    def delete_job_by_vo(job_vo):
        job_vo.delete()

    @staticmethod
    def _update_job_status_by_vo(job_vo, status):
        params = {'status': status}
        if status in ['SUCCESS', 'TIMEOUT', 'ERROR', 'CANCELED']:
            params.update({'finished_at': datetime.utcnow()})

        _LOGGER.debug(f'[update_job_status] job_id: {job_vo.job_id}, status: {status}')
        return job_vo.update(params)

    @staticmethod
    def update_job_by_vo(params, job_vo: Job):
        return job_vo.update(params)


CREATED = 'CREATED'
INPROGRESS = 'IN_PROGRESS'
CANCELED = 'CANCELED'
SUCCESS = 'SUCCESS'
ERROR = 'ERROR'
TIMEOUT = 'TIMEOUT'


class JobState(metaclass=abc.ABCMeta):
    def __init__(self):
        self.handle()

    @abc.abstractmethod
    def handle(self):
        pass


class InprogressState(JobState):
    def handle(self):
        pass

    def __str__(self):
        return INPROGRESS


class CreatedState(JobState):
    def handle(self):
        pass

    def __str__(self):
        return CREATED


class CanceledState(JobState):
    def handle(self):
        pass

    def __str__(self):
        return CANCELED


class SuccessState(JobState):
    def handle(self):
        pass

    def __str__(self):
        return SUCCESS


class ErrorState(JobState):
    def handle(self):
        pass

    def __str__(self):
        return ERROR


class TimeoutState(JobState):
    def handle(self):
        pass

    def __str__(self):
        return TIMEOUT


STATE_DIC = {
    'CREATED': CreatedState(),
    'IN_PROGRESS': InprogressState(),
    'CANCELED': CanceledState(),
    'SUCCESS': SuccessState(),
    'ERROR': ErrorState(),
    'TIMEOUT': TimeoutState()
}


class JobStateMachine():
    def __init__(self, job_vo):
        self.job_id = job_vo.job_id
        self._status = STATE_DIC[job_vo.status]

    def inprogress(self):
        if isinstance(self._status, (CreatedState, InprogressState, SuccessState)):
            # if collect is synchronous mode,
            # Job status can change: Inprogress -> Succcess -> Inprogress -> Success ...
            self._status = InprogressState()
        elif isinstance(self._status, (ErrorState)):
            pass
        else:
            raise ERROR_JOB_STATE_CHANGE(action='INPROGRESS', job_id=self.job_id, status=str(self._status))
        return self.get_status()

    def canceled(self):
        if isinstance(self._status, (CreatedState, InprogressState)):
            self._status = CanceledState()
        else:
            raise ERROR_JOB_STATE_CHANGE(action='CANCELED', job_id=self.job_id, status=str(self._status))
        return self.get_status()

    def success(self):
        if isinstance(self._status, (CreatedState, InprogressState, SuccessState)):
            # if collect is synchronous mode
            # Job status can change: Finished -> Finished
            self._status = SuccessState()
        elif isinstance(self._status, (ErrorState)):
            pass
        else:
            raise ERROR_JOB_STATE_CHANGE(action='SUCCESS', job_id=self.job_id, status=str(self._status))
        return self.get_status()

    def timeout(self):
        if isinstance(self._status, (CreatedState, InprogressState)):
            self._status = TimeoutState()
        else:
            raise ERROR_JOB_STATE_CHANGE(action='TIMEOUT', job_id=self.job_id, status=str(self._status))
        return self.get_status()

    def error(self):
        self._status = ErrorState()
        return self.get_status()

    def get_status(self):
        return str(self._status)
