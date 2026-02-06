class AppError(Exception):
    """Classe base para exceções da aplicação."""
    pass

class EquipeNaoEncontrada(AppError):
    """Lançada quando uma equipe não é encontrada."""
    pass

class JogadorNaoEncontrado(AppError):
    """Lançada quando um jogador não é encontrado."""
    pass

class PartidaNaoEncontrada(AppError):
    """Lançada quando uma partida não é encontrada."""
    pass
