"""Safe, structured B errors; never expose provider bodies or reasoning."""
class CreativeError(Exception):
    def __init__(self, message, code="INPUT_INVALID", issues=None):
        super().__init__(message)
        self.code = code
        self.issues = issues or []

    def public(self):
        return {"code": self.code, "message": str(self), "issues": self.issues,
                "retryable": self.code in ("MODEL_TIMEOUT", "MODEL_UNAVAILABLE", "OUTPUT_INVALID")}
