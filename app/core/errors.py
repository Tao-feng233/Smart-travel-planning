"""Business/data failures shared by tools, planners and HTTP orchestration."""


class DataError(Exception):
    def __init__(self, message, context=None):
        super().__init__(message)
        self.context = context
