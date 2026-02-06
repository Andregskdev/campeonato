from dataclasses import dataclass, field, asdict
from typing import List
import uuid
from models.jogador import Jogador
from utils.exceptions import JogadorNaoEncontrado

@dataclass
class Equipe:
    nome: str
    tecnico: str
    elenco: List[Jogador] = field(default_factory=list)
    vitorias: int = 0
    empates: int = 0
    derrotas: int = 0
    gols_marcados: int = 0
    gols_sofridos: int = 0
    id: str = field(default_factory=lambda: str(uuid.uuid4()), kw_only=True)

    @property
    def pontos(self) -> int:
        return (self.vitorias * 3) + (self.empates * 1)

    @property
    def saldo_gols(self) -> int:
        return self.gols_marcados - self.gols_sofridos

    @property
    def elenco_dict(self) -> dict:
        """Retorna dicionário de jogadores indexados por ID"""
        return {j.id: j for j in self.elenco}

    def contratar_jogador(self, jogador: Jogador) -> None:
        self.elenco.append(jogador)

    def buscar_jogador_por_id(self, jogador_id: str) -> Jogador | None:
        return next((j for j in self.elenco if j.id == jogador_id), None)

    def remover_jogador(self, jogador_id: str) -> None:
        jogador = self.buscar_jogador_por_id(jogador_id)
        if not jogador:
            raise JogadorNaoEncontrado(f"Jogador com ID {jogador_id} não encontrado.")
        self.elenco.remove(jogador)

    def to_dict(self) -> dict:
        d = asdict(self)
        # Adicionamos propriedades calculadas no dict para visualização no JSON
        d['pontos'] = self.pontos
        d['saldo_gols'] = self.saldo_gols
        return d

    @classmethod
    def from_dict(cls, data: dict):
        # Removemos chaves calculadas para não dar erro no construtor
        data.pop('pontos', None)
        data.pop('saldo_gols', None)
        elenco = [Jogador.from_dict(j_data) for j_data in data.get('elenco', [])]
        data['elenco'] = elenco
        return cls(**data)