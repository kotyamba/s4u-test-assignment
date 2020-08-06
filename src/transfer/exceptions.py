class TransferException(Exception):
    pass


class InsufficientBalance(TransferException):
    pass


class NegativeAmountException(TransferException):
    pass


class DeleteEntityException(TransferException):
    pass
