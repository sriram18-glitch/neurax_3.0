from __future__ import annotations


class EconomicsError(Exception):
    def __init__(self, code: str, message: str, detail: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail

    def to_dict(self) -> dict:
        return {"error": True, "code": self.code, "message": self.message, "detail": self.detail}
