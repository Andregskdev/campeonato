from dataclasses import dataclass, field
from datetime import datetime
import uuid
from models.equipe import Equipe
from models.jogador import Jogador

@dataclass
class Escalacao:
    """Escalação de uma equipe em um jogo"""
    titulares: list = field(default_factory=list)  # Lista de IDs de jogadores
    reservas: list = field(default_factory=list)   # Lista de IDs de jogadores
    id: str = field(default_factory=lambda: str(uuid.uuid4()), kw_only=True)

    def to_dict(self) -> dict:
        return {
            'titulares': self.titulares,
            'reservas': self.reservas,
            'id': self.id
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)

@dataclass
class Gol:
    """Registro de um gol marcado"""
    jogador_id: str
    jogador_nome: str
    equipe_id: str
    minuto: int
    id: str = field(default_factory=lambda: str(uuid.uuid4()), kw_only=True)

    def to_dict(self) -> dict:
        return {
            'jogador_id': self.jogador_id,
            'jogador_nome': self.jogador_nome,
            'equipe_id': self.equipe_id,
            'minuto': self.minuto,
            'id': self.id
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)

@dataclass
class Jogo:
    mandante: Equipe
    visitante: Equipe
    data: datetime
    local: str
    placar_mandante: int = 0
    placar_visitante: int = 0
    finalizada: bool = False
    status: str = "Agendada"  # Agendada, Ao vivo, Finalizada, Cancelada
    publico: int = 0
    observacoes: str = ""
    escalacao_mandante: Escalacao = field(default_factory=Escalacao)
    escalacao_visitante: Escalacao = field(default_factory=Escalacao)
    gols: list = field(default_factory=list)  # Lista de Gol
    id: str = field(default_factory=lambda: str(uuid.uuid4()), kw_only=True)

    def finalizar_partida(self, g_mandante: int, g_visitante: int) -> None:
        if self.finalizada:
            return
            
        self.placar_mandante = g_mandante
        self.placar_visitante = g_visitante
        
        # Atualiza estatísticas das equipes
        self.mandante.gols_marcados += g_mandante
        self.mandante.gols_sofridos += g_visitante
        self.visitante.gols_marcados += g_visitante
        self.visitante.gols_sofridos += g_mandante

        if g_mandante > g_visitante:
            self.mandante.vitorias += 1
            self.visitante.derrotas += 1
        elif g_visitante > g_mandante:
            self.visitante.vitorias += 1
            self.mandante.derrotas += 1
        else:
            self.mandante.empates += 1
            self.visitante.empates += 1
        
        self.finalizada = True
        self.status = "Finalizada"

    def to_dict(self) -> dict:
        return {
            'mandante': self.mandante.to_dict(),
            'visitante': self.visitante.to_dict(),
            'data': self.data.isoformat(),
            'local': self.local,
            'placar_mandante': self.placar_mandante,
            'placar_visitante': self.placar_visitante,
            'finalizada': self.finalizada,
            'status': self.status,
            'publico': self.publico,
            'observacoes': self.observacoes,
            'escalacao_mandante': self.escalacao_mandante.to_dict(),
            'escalacao_visitante': self.escalacao_visitante.to_dict(),
            'gols': [g.to_dict() for g in self.gols],
            'id': self.id
        }

    @classmethod
    def from_dict(cls, data: dict):
        data['mandante'] = Equipe.from_dict(data['mandante'])
        data['visitante'] = Equipe.from_dict(data['visitante'])
        data['data'] = datetime.fromisoformat(data['data'])
        # Compatibilidade com dados antigos
        data.setdefault('status', 'Finalizada' if data.get('finalizada') else 'Agendada')
        data.setdefault('publico', 0)
        data.setdefault('observacoes', '')
        
        # Escalações
        escal_mand = data.get('escalacao_mandante', {})
        escal_visit = data.get('escalacao_visitante', {})
        data['escalacao_mandante'] = Escalacao.from_dict(escal_mand) if escal_mand else Escalacao()
        data['escalacao_visitante'] = Escalacao.from_dict(escal_visit) if escal_visit else Escalacao()
        
        # Gols
        data['gols'] = [Gol.from_dict(g) for g in data.get('gols', [])]
        
        return cls(**data)