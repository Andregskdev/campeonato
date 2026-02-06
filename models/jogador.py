from dataclasses import dataclass, field, asdict
import uuid

@dataclass
class Jogador:
    nome: str
    numero: int
    posicao: str
    gols: int = 0
    id: str = field(default_factory=lambda: str(uuid.uuid4()), kw_only=True)

    def get_dados(self) -> str:
        return f"{self.numero} - {self.nome} ({self.posicao}) - Gols: {self.gols}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)