from src.agents.strategy.errors import ContractValidationError
from src.contracts.campaign import now


class CampaignHistory:
    def __init__(self, campaigns, images):
        self.campaigns, self.images = campaigns, images
        self.repository = campaigns.repository

    def _busy(self, task):
        return task['task_id'] in self.campaigns.active or task['status'] in ('pending', 'running') or any(job['status'] in ('pending', 'running') for job in task.get('image_jobs', []))

    def _archive(self, task):
        if task.get('deleted_at'):
            return
        stamp = now()
        self.repository.update(task['task_id'], lambda current: current.update(deleted_at=stamp, updated_at=stamp))

    def archive(self, task_id, owner):
        with self.images.lock, self.campaigns.lock:
            task = self.repository.get(task_id, owner, include_deleted=True)
            if self._busy(task):
                raise ContractValidationError('任务或图片仍在生成，请等待结束后再删除；删除不会取消供应商计费')
            self._archive(task)
            return {'status': 'archived', 'task_ids': [task_id]}

    def clear(self, owner):
        with self.images.lock, self.campaigns.lock:
            archived, skipped = [], []
            for task in self.repository.list(owner, limit=None):
                if self._busy(task):
                    skipped.append(task['task_id'])
                else:
                    self._archive(task)
                    archived.append(task['task_id'])
            return {'status': 'archived', 'task_ids': archived, 'skipped_ids': skipped}

    def restore(self, task_id, owner):
        with self.images.lock, self.campaigns.lock:
            self.repository.get(task_id, owner, include_deleted=True)
            def update(task):
                task.pop('deleted_at', None)
                task['updated_at'] = now()
            self.repository.update(task_id, update)
            return self.campaigns.get(task_id, owner)
