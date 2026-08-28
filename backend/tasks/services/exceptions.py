"""Task service layer exceptions."""


class TaskBindingError(Exception):
    """Raised by task binding service functions on validation/lookup failures.

    Carries a ``status_code`` so the view layer can map service errors to
    HTTP responses without inspecting the exception type. Used by
    ``execute_task`` / ``bind_task_accounts`` / ``clone_pipeline_for_user``
    / ``get_user_pipeline`` to isolate cross-app model lookups (TD-265).

    The optional ``extra`` dict lets the service layer forward context
    (e.g. the existing ``pipeline_id`` on a 409 conflict) so the view
    can preserve the original response shape without re-querying the
    cross-app model.
    """

    def __init__(self, message, status_code=400, extra=None):
        self.message = message
        self.status_code = status_code
        self.extra = extra or {}
        super().__init__(message)
