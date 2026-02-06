from dataclasses import dataclass, field
from typing import List
import uuid
from models.partida import Jogo
from models.equipe import Equipe
from utils.exceptions import EquipeNaoEncontrada

@dataclass
class Fase:
    nome: str
    ordem: int
    tipo: str = "Corridos"  # Corridos ou Mata-mata
    grupo: str = ""  # Vazio ou "A", "B", "C", etc.
    jogos: List[Jogo] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4()), kw_only=True)

    def adicionar_jogo(self, jogo: Jogo) -> None:
        self.jogos.append(jogo)

    def to_dict(self) -> dict:
        return {
            'nome': self.nome,
            'ordem': self.ordem,
            'tipo': self.tipo,
            'grupo': self.grupo,
            'jogos': [j.to_dict() for j in self.jogos],
            'id': self.id
        }

    @classmethod
    def from_dict(cls, data: dict):
        data['jogos'] = [Jogo.from_dict(j_data) for j_data in data.get('jogos', [])]
        data.setdefault('tipo', 'Corridos')
        data.setdefault('grupo', '')
        return cls(**data)

@dataclass
class Campeonato:
    nome: str
    ano: int
    tipo: str = "Pontos corridos"  # Pontos corridos ou Mata-mata
    fases: List[Fase] = field(default_factory=list)
    equipes_inscritas: List[Equipe] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4()), kw_only=True)

    def obter_classificacao(self) -> List[Equipe]:
        """Ordena por Pontos, Vitórias, Saldo de Gols e Gols Marcados."""
        return sorted(
            self.equipes_inscritas,
            key=lambda e: (e.pontos, e.vitorias, e.saldo_gols, e.gols_marcados),
            reverse=True
        )

    def cadastrar_equipe(self, equipe: Equipe) -> None:
        self.equipes_inscritas.append(equipe)

    def adicionar_fase(self, fase: Fase) -> None:
        self.fases.append(fase)

    def remover_equipe(self, equipe_id: str) -> None:
        equipe = next((e for e in self.equipes_inscritas if e.id == equipe_id), None)
        if not equipe:
            raise EquipeNaoEncontrada(f"Equipe ID {equipe_id} não encontrada.")
        self.equipes_inscritas.remove(equipe)

    def to_dict(self) -> dict:
        return {
            'nome': self.nome,
            'ano': self.ano,
            'tipo': self.tipo,
            'fases': [f.to_dict() for f in self.fases],
            'equipes_inscritas': [e.to_dict() for e in self.equipes_inscritas],
            'id': self.id
        }

    @classmethod
    def from_dict(cls, data: dict):
        data['fases'] = [Fase.from_dict(f_data) for f_data in data.get('fases', [])]
        data['equipes_inscritas'] = [Equipe.from_dict(e_data) for e_data in data.get('equipes_inscritas', [])]
        data.setdefault('tipo', 'Pontos corridos')
        return cls(**data)