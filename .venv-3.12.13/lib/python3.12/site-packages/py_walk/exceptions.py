class PyWalkException(Exception):
    """PyWalk base exeption."""

    pass


class PyWalkError(PyWalkException):
    """Base exeption for PyWalk errors."""

    pass


class PyWalkInputError(PyWalkError):
    """Invalid user provided data."""

    pass


class PyWalkInternalError(PyWalkError):
    """Exeption for internal, unexpected errors."""

    pass
