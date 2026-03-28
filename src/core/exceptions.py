"""Shared exceptions across all modules."""


class DomainError(Exception):
    """Base domain error."""
    
    def __init__(self, message: str, code: str = "DOMAIN_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class NotFoundError(DomainError):
    """Resource not found."""
    
    def __init__(self, resource: str, identifier: str):
        super().__init__(
            message=f"{resource} with id '{identifier}' not found",
            code="NOT_FOUND"
        )


class ValidationError(DomainError):
    """Validation failed."""
    
    def __init__(self, message: str):
        super().__init__(message=message, code="VALIDATION_ERROR")


class ConflictError(DomainError):
    """Resource conflict."""
    
    def __init__(self, message: str):
        super().__init__(message=message, code="CONFLICT")


class CouponError(DomainError):
    """Coupon-related error."""
    pass


class RuleError(DomainError):
    """Rule engine error."""
    pass


class CheckoutError(DomainError):
    """Checkout-related error."""
    pass
