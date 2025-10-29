"""
Custom exceptions for parser module
"""


class LoginPageException(Exception):
    """Raised when login page is detected during parsing"""
    pass


class OctoProfileStartException(Exception):
    """Raised when Octo profile fails to start"""
    pass


class OctoProfileAlreadyStartedException(Exception):
    """Raised when Octo profile is already started"""
    pass


class NoNewTransactionsException(Exception):
    """Raised when no new transactions are found"""
    pass

