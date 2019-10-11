from qiskit.providers.jobstatus import JobStatus, JOB_FINAL_STATES
from enum import Enum

# noinspection PyArgumentList
QStatus = Enum(value="JobStatus",
               names={
                   "REQUESTED": 'received job request, waiting for thread to start',
                   "CONSTRUCTING_CIRCUIT": 'constructing circuit for job',
                   "FINDING_BACKEND": 'looking for capable backend for job',
                   "REQUEST_EXECUTE": 'transpiling and assembling server',
                   **{i.name: i.value for i in JobStatus}
               })


Q_FINAL_STATES = JOB_FINAL_STATES


def from_job_status(job_status: JobStatus):
    for status in QStatus:
        if status.value == job_status.value:
            return status
    raise ValueError("Cannot convert JobStatus '{}' to QState".format(job_status))
