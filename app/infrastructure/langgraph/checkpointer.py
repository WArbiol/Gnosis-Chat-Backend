import os
from langgraph.checkpoint.memory import MemorySaver

class CheckpointerFactory:
    """Factory para resolver o checkpointer do LangGraph conforme o ambiente.
    
    Por padrão para o MVP, utiliza o MemorySaver para simplificar a infraestrutura.
    Pode ser estendido para carregar o PostgresSaver se configurado.
    """

    _instance = None

    @classmethod
    def get_checkpointer(cls):
        # Se o grafo estiver rodando dentro do LangGraph API/Studio/Cloud,
        # retornamos None para que a persistência nativa do Studio assuma o controle.
        if any(k.startswith("LANGGRAPH_") for k in os.environ.keys()):
            return None

        if cls._instance is None:
            # MemorySaver persistido na RAM do processo do FastAPI
            cls._instance = MemorySaver()
        return cls._instance
