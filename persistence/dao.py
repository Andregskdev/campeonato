from abc import ABC, abstractmethod
from typing import List
import json
import os
from models.campeonato import Campeonato


class CampeonatoDAO(ABC):
    @abstractmethod
    def salvar(self, campeonato: Campeonato) -> None:
        pass

    @abstractmethod
    def listar_todos(self) -> List[Campeonato]:
        pass
    
    @abstractmethod
    def excluir(self, id: str) -> bool:
        pass

    @abstractmethod
    def buscar_por_id(self, id: str) -> Campeonato | None:
        pass


class CampeonatoFileDAO(CampeonatoDAO):
    def __init__(self, path: str = 'data/campeonatos.json'):
        self.path = path
        self._db = {} # Cache em memória
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._load()

    def _load(self):
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                raw_list = json.load(f)
                for camp_dict in raw_list:
                    camp = Campeonato.from_dict(camp_dict)
                    self._db[camp.id] = camp
        except (json.JSONDecodeError, FileNotFoundError):
            self._db = {}

    def _save(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump([c.to_dict() for c in self._db.values()], f, ensure_ascii=False, indent=2)

    def salvar(self, campeonato: Campeonato) -> None:
        self._db[campeonato.id] = campeonato
        self._save()
        print(f"[BD] Campeonato '{campeonato.nome}' salvo em {self.path}.")

    def listar_todos(self) -> List[Campeonato]:
        return list(self._db.values())

    def excluir(self, id: str) -> bool:
        if id in self._db:
            del self._db[id]
            self._save()
            return True
        return False
        
    def buscar_por_id(self, id: str) -> Campeonato | None:
        return self._db.get(id)
    
    def reload(self):
        """Recarrega os dados do arquivo, útil quando o cache do Streamlit precisa ser atualizado."""
        self._load()