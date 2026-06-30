class DomainException(Exception):
    """Classe base para todas as exceções de domínio do sistema."""
    pass

class QuotaExceededException(DomainException):
    """Exceção lançada quando o usuário ultrapassa o limite de cota do seu plano."""
    
    def __init__(self, message: str, code: str = "LIMIT_EXCEEDED") -> None:
        super().__init__(message)
        self.code = code
