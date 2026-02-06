import json
import csv
import io
from datetime import datetime, date

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

from models.campeonato import Campeonato, Fase
from models.equipe import Equipe
from models.jogador import Jogador
from models.partida import Jogo, Escalacao, Gol
from persistence.dao import CampeonatoFileDAO

st.set_page_config(page_title="Gestão de Campeonatos", layout="wide")

# Inicializar DAO sem cache para evitar problemas com exclusões
if 'dao' not in st.session_state:
    st.session_state.dao = CampeonatoFileDAO()

dao = st.session_state.dao

def get_camp_tipo(camp_obj):
    return getattr(camp_obj, "tipo", "Pontos corridos")

def ensure_campeonato_tipo():
    for c in dao.listar_todos():
        if not hasattr(c, "tipo") or not c.tipo:
            c.tipo = "Pontos corridos"
            dao.salvar(c)

def exibir_bracket_mmata_mata(camp):
    """Exibe a estrutura de eliminatória (bracket) para campeonatos mata-mata."""
    if not camp.fases:
        st.info("Nenhuma fase criada.")
        return
    
    # Ordenar fases por ordem
    fases = sorted(camp.fases, key=lambda f: f.ordem)
    
    st.subheader("🏆 Tabela de Eliminatória")
    
    for fase in fases:
        st.write(f"#### {fase.nome}")
        
        if not fase.jogos:
            st.info(f"Nenhum jogo em {fase.nome}")
            continue
        
        # Criar colunas para exibir os jogos
        cols = st.columns(len(fase.jogos) if len(fase.jogos) <= 4 else 4)
        
        for idx, jogo in enumerate(fase.jogos):
            col = cols[idx % len(cols)]
            with col:
                # Container para cada jogo
                with st.container(border=True):
                    st.write(f"**{jogo.mandante.nome}**")
                    
                    if jogo.finalizada:
                        st.write(f"**{jogo.placar_mandante} x {jogo.placar_visitante}**")
                        # Destaque ao vencedor
                        if jogo.placar_mandante > jogo.placar_visitante:
                            st.success(f"✅ {jogo.mandante.nome} avançou")
                        elif jogo.placar_visitante > jogo.placar_mandante:
                            st.success(f"✅ {jogo.visitante.nome} avançou")
                        else:
                            st.warning("⚠️ Jogo empatado")
                    else:
                        st.write("vs")
                        st.caption("⏳ Pendente")
                    
                    st.write(f"**{jogo.visitante.nome}**")
                    st.caption(f"📍 {jogo.local}")
        
        st.divider()

REGRAS_ESCALACAO = {
    "titulares_exatos": 11,
    "reservas_max": 12,
    "total_max": 23,
    "goleiro_min_titular": 1,
}

def validar_escalacao(equipe: Equipe, titulares: list, reservas: list, rotulo: str) -> list:
    erros = []
    if len(titulares) != REGRAS_ESCALACAO["titulares_exatos"]:
        erros.append(f"⚠️ {rotulo}: é obrigatório ter exatamente {REGRAS_ESCALACAO['titulares_exatos']} titulares.")
    if len(reservas) > REGRAS_ESCALACAO["reservas_max"]:
        erros.append(f"⚠️ {rotulo}: no máximo {REGRAS_ESCALACAO['reservas_max']} reservas.")
    if len(titulares) + len(reservas) > REGRAS_ESCALACAO["total_max"]:
        erros.append(f"⚠️ {rotulo}: total de relacionados não pode passar de {REGRAS_ESCALACAO['total_max']}.")
    goleiros_titulares = [j for j in titulares if j.posicao == "Goleiro"]
    if len(goleiros_titulares) < REGRAS_ESCALACAO["goleiro_min_titular"]:
        erros.append(f"⚠️ {rotulo}: é obrigatório 1 goleiro entre os titulares.")
    if len(set(j.id for j in titulares + reservas)) != (len(titulares) + len(reservas)):
        erros.append(f"⚠️ {rotulo}: há jogadores duplicados na escalação.")
    return erros

def obter_jogos_com_fase(camp_obj: Campeonato):
    jogos = []
    for fase in camp_obj.fases:
        for jogo in fase.jogos:
            jogos.append((fase, jogo))
    return jogos

ensure_campeonato_tipo()

with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_role = None

def render_login():
    st.sidebar.title("Login")
    usuario = st.sidebar.selectbox("Usuário", list(config['users'].keys()), key="user_select")
    senha = st.sidebar.text_input("Senha", type="password")
    if st.sidebar.button("Entrar"):
        user_data = config['users'].get(usuario)
        if user_data:
            # Compatibilidade com config antigo (strings) e novo (dicts)
            user_senha = user_data.get('senha', user_data) if isinstance(user_data, dict) else user_data
            user_role = user_data.get('role', 'admin') if isinstance(user_data, dict) else 'admin'
            
            if senha == user_senha:
                st.session_state.logged_in = True
                st.session_state.user_role = user_role
                st.session_state.username = usuario
                st.rerun()
            else:
                st.sidebar.error("Senha inválida")
        else:
            st.sidebar.error("Usuário não encontrado")

def is_admin():
    return st.session_state.get('user_role') == 'admin'

def ensure_jogo_gols():
    """Garante que todos os jogos tenham o atributo 'gols'"""
    for camp in dao.listar_todos():
        for fase in camp.fases:
            for jogo in fase.jogos:
                if not hasattr(jogo, 'gols') or jogo.gols is None:
                    jogo.gols = []
                if not hasattr(jogo, 'escalacao_mandante') or jogo.escalacao_mandante is None:
                    jogo.escalacao_mandante = Escalacao()
                if not hasattr(jogo, 'escalacao_visitante') or jogo.escalacao_visitante is None:
                    jogo.escalacao_visitante = Escalacao()
        dao.salvar(camp)

if not st.session_state.logged_in:
    render_login()
    st.info("Faça login na barra lateral para acessar o sistema.")
    st.stop()

if 'campeonato_id' not in st.session_state:
    st.session_state.campeonato_id = None

def get_campeonato():
    campeonatos = dao.listar_todos()
    if not campeonatos:
        camp = Campeonato(config['default_campeonato']['nome'], config['default_campeonato']['ano'])
        dao.salvar(camp)
        st.session_state.campeonato_id = camp.id
        return camp
    
    if st.session_state.campeonato_id:
        camp = dao.buscar_por_id(st.session_state.campeonato_id)
        if camp:
            return camp
    
    st.session_state.campeonato_id = campeonatos[0].id
    return campeonatos[0]

camp = get_campeonato()

st.sidebar.markdown("---")
st.sidebar.subheader("Campeonato Ativo")
todos_camps = dao.listar_todos()

# Garantir que todos os jogos têm gols
ensure_jogo_gols()

if len(todos_camps) > 1:
    camp_selecionado = st.sidebar.selectbox(
        "Selecionar",
        todos_camps,
        format_func=lambda c: f"{c.nome} ({c.ano}) - {get_camp_tipo(c)}",
        index=next((i for i, c in enumerate(todos_camps) if c.id == camp.id), 0),
        key="select_camp"
    )
    if camp_selecionado.id != camp.id:
        st.session_state.campeonato_id = camp_selecionado.id
        st.rerun()
else:
    st.sidebar.write(f"**{camp.nome} ({camp.ano}) - {get_camp_tipo(camp)}**")
st.sidebar.markdown("---")

st.title(f"🏆 {camp.nome} - {camp.ano}")

# Dashboard
with st.expander("📊 Dashboard", expanded=True):
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("Equipes", len(camp.equipes_inscritas))
    with col2:
        total_jogos = sum(len(f.jogos) for f in camp.fases)
        st.metric("Total Jogos", total_jogos)
    with col3:
        jogos_fin = sum(1 for f in camp.fases for j in f.jogos if j.finalizada)
        st.metric("Finalizados", jogos_fin)
    with col4:
        total_gols = sum(e.gols_marcados for e in camp.equipes_inscritas)
        st.metric("Gols", total_gols)
    with col5:
        if camp.equipes_inscritas:
            lider = camp.obter_classificacao()[0]
            st.metric("Líder", lider.nome[:15], f"{lider.pontos}pts")

# Menu diferente para visitantes e admins
if is_admin():
    menu = ["Classificação", "Estatísticas", "Pesquisa", "Equipes", "Jogadores", "Gerenciar Partidas", "Fases/Grupos", "Campeonatos"]
else:
    menu = ["Classificação", "Estatísticas", "Pesquisa", "Equipes", "Jogadores"]

choice = st.sidebar.radio("Menu", menu)

if choice == "Classificação":
    st.subheader("📊 Tabela de Classificação")
    st.caption("Critérios: pontos, vitórias, saldo de gols e gols marcados.")
    
    # Se for mata-mata, exibir bracket
    if get_camp_tipo(camp) == "Mata-mata":
        exibir_bracket_mmata_mata(camp)
    else:
        # Exibir tabela de pontos corridos
        equipes = camp.obter_classificacao()
        if not equipes:
            st.warning("Nenhuma equipe cadastrada.")
        else:
            # Gráfico de pontos
            col1, col2 = st.columns([2, 1])
        
        with col1:
            data = [
                {
                    "Posição": i,
                    "Equipe": e.nome,
                    "Pontos": e.pontos,
                    "Vitórias": e.vitorias,
                    "Empates": e.empates,
                    "Derrotas": e.derrotas,
                    "Saldo de Gols": e.saldo_gols,
                }
                for i, e in enumerate(equipes, 1)
            ]
            st.dataframe(data, use_container_width=True, hide_index=True)
        
        with col2:
            st.metric("Total de Equipes", len(equipes))
            if equipes:
                st.metric("Líder", equipes[0].nome)
                st.metric("Pontos do Líder", equipes[0].pontos)

elif choice == "Estatísticas":
    st.subheader("📈 Estatísticas do Campeonato")
    
    if not camp.equipes_inscritas:
        st.info("Nenhum dado disponível.")
    else:
        # Ajustar abas se for mata-mata
        if get_camp_tipo(camp) == "Mata-mata":
            tab1, tab2 = st.tabs(["Geral", "Calendário"])
        else:
            tab1, tab2, tab3, tab4, tab5 = st.tabs(["Geral", "Ataque", "Defesa", "Desempenho", "Calendário"])
        
        with tab1:
            col1, col2, col3, col4 = st.columns(4)
            total_jogos = sum(len(f.jogos) for f in camp.fases)
            jogos_finalizados = sum(1 for f in camp.fases for j in f.jogos if j.finalizada)
            total_gols = sum(e.gols_marcados for e in camp.equipes_inscritas)
            
            with col1:
                st.metric("Total de Jogos", total_jogos)
            with col2:
                st.metric("Jogos Finalizados", jogos_finalizados)
            with col3:
                st.metric("Gols Marcados", total_gols)
            with col4:
                media_gols = round(total_gols / jogos_finalizados, 2) if jogos_finalizados > 0 else 0
                st.metric("Média Gols/Jogo", media_gols)
        
        if get_camp_tipo(camp) != "Mata-mata":
            with tab2:
                st.subheader("Melhores Ataques")
                ataque = sorted(camp.equipes_inscritas, key=lambda e: e.gols_marcados, reverse=True)[:5]
                for i, e in enumerate(ataque, 1):
                    st.write(f"{i}. **{e.nome}** - {e.gols_marcados} gols")
                
                # Gráfico
                fig = go.Figure(data=[
                    go.Bar(x=[e.nome for e in ataque], y=[e.gols_marcados for e in ataque],
                           marker_color='lightgreen')
                ])
                fig.update_layout(title="Top 5 - Gols Marcados", xaxis_title="Equipe", yaxis_title="Gols")
                st.plotly_chart(fig, use_container_width=True)
            
            with tab3:
                st.subheader("Melhores Defesas")
                defesa = sorted(camp.equipes_inscritas, key=lambda e: e.gols_sofridos)[:5]
                for i, e in enumerate(defesa, 1):
                    st.write(f"{i}. **{e.nome}** - {e.gols_sofridos} gols sofridos")
                
                # Gráfico
                fig = go.Figure(data=[
                    go.Bar(x=[e.nome for e in defesa], y=[e.gols_sofridos for e in defesa],
                           marker_color='lightcoral')
                ])
                fig.update_layout(title="Top 5 - Menos Gols Sofridos", xaxis_title="Equipe", yaxis_title="Gols Sofridos")
                st.plotly_chart(fig, use_container_width=True)
            
            with tab4:
                st.subheader("Comparação Gols Marcados vs Sofridos")
                fig = go.Figure()
                equipes_graf = camp.equipes_inscritas[:10]  # Top 10
                
                fig.add_trace(go.Bar(
                    name='Gols Marcados',
                    x=[e.nome for e in equipes_graf],
                    y=[e.gols_marcados for e in equipes_graf],
                    marker_color='green'
                ))
                fig.add_trace(go.Bar(
                    name='Gols Sofridos',
                    x=[e.nome for e in equipes_graf],
                    y=[e.gols_sofridos for e in equipes_graf],
                    marker_color='red'
                ))
                
                fig.update_layout(barmode='group', xaxis_title="Equipe", yaxis_title="Gols")
                st.plotly_chart(fig, use_container_width=True)
        
        if get_camp_tipo(camp) == "Mata-mata":
            with tab2:
                st.subheader("📅 Calendário de Eliminatória")

                jogos_com_fase = obter_jogos_com_fase(camp)
                if not jogos_com_fase:
                    st.info("Nenhuma partida criada.")
                else:
                    datas = [j.data.date() for _, j in jogos_com_fase]
                    data_min = min(datas) if datas else date.today()
                    data_max = max(datas) if datas else date.today()

                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        fases_disponiveis = ["Todas"] + [f.nome for f in camp.fases]
                        fase_filtro = st.selectbox("Fase", fases_disponiveis, key="cal_mm_fase")
                    with col2:
                        status_filtro = st.selectbox("Status", ["Todos", "Finalizadas", "Pendentes", "Ao vivo", "Canceladas"], key="cal_mm_status")
                    with col3:
                        equipe_filtro = st.selectbox(
                            "Equipe",
                            ["Todas"] + camp.equipes_inscritas,
                            format_func=lambda e: e if isinstance(e, str) else e.nome,
                            key="cal_mm_equipe"
                        )
                    with col4:
                        periodo = st.date_input("Período", value=(data_min, data_max), key="cal_mm_periodo")

                    if isinstance(periodo, date):
                        data_ini, data_fim = periodo, periodo
                    else:
                        data_ini, data_fim = periodo

                    jogos_filtrados = []
                    for fase, jogo in jogos_com_fase:
                        if fase_filtro != "Todas" and fase.nome != fase_filtro:
                            continue
                        if status_filtro == "Finalizadas" and not jogo.finalizada:
                            continue
                        if status_filtro == "Pendentes" and jogo.finalizada:
                            continue
                        if status_filtro == "Ao vivo" and jogo.status != "Ao vivo":
                            continue
                        if status_filtro == "Canceladas" and jogo.status != "Cancelada":
                            continue
                        if equipe_filtro != "Todas" and jogo.mandante.id != equipe_filtro.id and jogo.visitante.id != equipe_filtro.id:
                            continue
                        data_jogo = jogo.data.date()
                        if data_jogo < data_ini or data_jogo > data_fim:
                            continue
                        jogos_filtrados.append((fase, jogo))

                    if not jogos_filtrados:
                        st.info("Nenhuma partida encontrada com os filtros selecionados.")
                    else:
                        for fase, jogo in sorted(jogos_filtrados, key=lambda x: x[1].data):
                            with st.container():
                                col1, col2, col3 = st.columns([2, 1, 2])
                                with col1:
                                    st.markdown(f"### {jogo.mandante.nome}")
                                with col2:
                                    if jogo.finalizada:
                                        st.markdown(f"### **{jogo.placar_mandante} x {jogo.placar_visitante}**")
                                        st.caption("✅ Finalizada")
                                    else:
                                        st.markdown("### **vs**")
                                        st.caption("⏳ Pendente")
                                with col3:
                                    st.markdown(f"### {jogo.visitante.nome}")
                                st.caption(f"📍 {jogo.local} | 📆 {jogo.data.strftime('%d/%m/%Y')}")
                                st.caption(f"🏟️ Fase: {fase.nome}")
                                st.divider()

                st.subheader("🔰 Chaveamento")
                exibir_bracket_mmata_mata(camp)
        else:
            with tab5:
                st.subheader("📅 Calendário de Jogos")

                jogos_com_fase = obter_jogos_com_fase(camp)
                if not jogos_com_fase:
                    st.info("Nenhuma partida criada.")
                else:
                    datas = [j.data.date() for _, j in jogos_com_fase]
                    data_min = min(datas) if datas else date.today()
                    data_max = max(datas) if datas else date.today()

                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        fases_disponiveis = ["Todas"] + [f.nome for f in camp.fases]
                        fase_filtro = st.selectbox("Fase", fases_disponiveis, key="cal_fase")
                    with col2:
                        status_filtro = st.selectbox("Status", ["Todos", "Finalizadas", "Pendentes", "Ao vivo", "Canceladas"], key="cal_status")
                    with col3:
                        equipe_filtro = st.selectbox(
                            "Equipe",
                            ["Todas"] + camp.equipes_inscritas,
                            format_func=lambda e: e if isinstance(e, str) else e.nome,
                            key="cal_equipe"
                        )
                    with col4:
                        periodo = st.date_input("Período", value=(data_min, data_max), key="cal_periodo")

                    if isinstance(periodo, date):
                        data_ini, data_fim = periodo, periodo
                    else:
                        data_ini, data_fim = periodo

                    jogos_filtrados = []
                    for fase, jogo in jogos_com_fase:
                        if fase_filtro != "Todas" and fase.nome != fase_filtro:
                            continue
                        if status_filtro == "Finalizadas" and not jogo.finalizada:
                            continue
                        if status_filtro == "Pendentes" and jogo.finalizada:
                            continue
                        if status_filtro == "Ao vivo" and jogo.status != "Ao vivo":
                            continue
                        if status_filtro == "Canceladas" and jogo.status != "Cancelada":
                            continue
                        if equipe_filtro != "Todas" and jogo.mandante.id != equipe_filtro.id and jogo.visitante.id != equipe_filtro.id:
                            continue
                        data_jogo = jogo.data.date()
                        if data_jogo < data_ini or data_jogo > data_fim:
                            continue
                        jogos_filtrados.append((fase, jogo))

                    if not jogos_filtrados:
                        st.info("Nenhuma partida encontrada com os filtros selecionados.")
                    else:
                        for fase, jogo in sorted(jogos_filtrados, key=lambda x: x[1].data):
                            with st.container():
                                col1, col2, col3 = st.columns([2, 1, 2])
                                with col1:
                                    st.markdown(f"### {jogo.mandante.nome}")
                                with col2:
                                    if jogo.finalizada:
                                        st.markdown(f"### **{jogo.placar_mandante} x {jogo.placar_visitante}**")
                                        st.caption("✅ Finalizada")
                                    else:
                                        st.markdown("### **vs**")
                                        st.caption("⏳ Pendente")
                                with col3:
                                    st.markdown(f"### {jogo.visitante.nome}")
                                st.caption(f"📍 {jogo.local} | 📆 {jogo.data.strftime('%d/%m/%Y')}")
                                st.caption(f"🏟️ Fase: {fase.nome}")
                                st.divider()

elif choice == "Pesquisa":
    st.subheader("🔍 Pesquisar")
    
    tab1, tab2 = st.tabs(["Equipes", "Jogadores"])
    
    with tab1:
        termo = st.text_input("Buscar equipe por nome", key="pesq_equipe", placeholder="Digite o nome da equipe...")
        
        if termo:
            resultados = [e for e in camp.equipes_inscritas if termo.lower() in e.nome.lower()]
            
            if not resultados:
                st.info(f"Nenhuma equipe encontrada com '{termo}'")
            else:
                for equipe in resultados:
                    with st.container():
                        col1, col2, col3 = st.columns([2, 1, 1])
                        with col1:
                            st.write(f"### {equipe.nome}")
                            st.caption(f"Técnico: {equipe.tecnico}")
                        with col2:
                            st.metric("Pontos", equipe.pontos)
                            st.metric("Jogadores", len(equipe.elenco))
                        with col3:
                            st.metric("Vitórias", equipe.vitorias)
                            st.metric("Saldo", equipe.saldo_gols)
                        st.divider()
        else:
            st.info("Digite o nome de uma equipe para buscar")
    
    with tab2:
        termo = st.text_input("Buscar jogador por nome", key="pesq_jogador", placeholder="Digite o nome do jogador...")
        
        if termo:
            resultados = []
            for equipe in camp.equipes_inscritas:
                for jogador in equipe.elenco:
                    if termo.lower() in jogador.nome.lower():
                        resultados.append((equipe, jogador))
            
            if not resultados:
                st.info(f"Nenhum jogador encontrado com '{termo}'")
            else:
                for equipe, jogador in resultados:
                    with st.container():
                        col1, col2, col3 = st.columns([2, 1, 1])
                        with col1:
                            st.write(f"**{jogador.nome}** (#{jogador.numero})")
                            st.caption(f"Posição: {jogador.posicao} | Equipe: {equipe.nome}")
                        with col2:
                            st.metric("Gols", jogador.gols)
                        with col3:
                            st.warning("⚠️ Ação destrutiva")
                            confirma_rem = st.checkbox("Confirmar remoção", key=f"rem_jog_conf_{jogador.id}")
                            if st.button("Remover", key=f"rem_jog_{jogador.id}", disabled=not confirma_rem):
                                try:
                                    equipe.remover_jogador(jogador.id)
                                    dao.salvar(camp)
                                    st.success(f"✅ Jogador {jogador.nome} removido com sucesso!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Erro: {e}")
                        st.divider()
        else:
            st.info("Digite o nome de um jogador para buscar")

elif choice == "Equipes":
    st.subheader("⚽ Equipes")
    
    if is_admin():
        tab_listar, tab_criar, tab_upload, tab_editar, tab_remover = st.tabs(["Listar", "Cadastrar", "Upload em massa", "Editar", "Remover"])
    else:
        tab_listar = st.tabs(["Listar"])[0]

    with tab_listar:
        if not camp.equipes_inscritas:
            st.info("Nenhuma equipe cadastrada.")
        else:
            for e in camp.equipes_inscritas:
                with st.container():
                    col1, col2, col3 = st.columns([2, 1, 1])
                    with col1:
                        st.write(f"### {e.nome}")
                        st.caption(f"Técnico: {e.tecnico}")
                    with col2:
                        st.metric("Pontos", e.pontos)
                        st.metric("Jogadores", len(e.elenco))
                    with col3:
                        st.metric("Vitórias", e.vitorias)
                        st.metric("Saldo", e.saldo_gols)
                    st.divider()

    if is_admin():
        with tab_criar:
            nome = st.text_input("Nome da equipe", key="eq_nome", max_chars=50)
            tecnico = st.text_input("Técnico", key="eq_tecnico", max_chars=50)
            if st.button("Salvar equipe", key="eq_salvar"):
                # Validações
                if not nome.strip():
                    st.error("⚠️ O nome da equipe é obrigatório.")
                elif len(nome.strip()) < 3:
                    st.error("⚠️ O nome da equipe deve ter pelo menos 3 caracteres.")
                elif any(e.nome.lower() == nome.strip().lower() for e in camp.equipes_inscritas):
                    st.error("⚠️ Já existe uma equipe com este nome.")
                else:
                    try:
                        camp.cadastrar_equipe(Equipe(nome=nome.strip(), tecnico=tecnico.strip() or "Sem técnico"))
                        dao.salvar(camp)
                        st.success(f"✅ Equipe '{nome.strip()}' cadastrada com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erro ao cadastrar equipe: {e}")

        with tab_upload:
            st.subheader("📥 Upload em massa de equipes (CSV)")
            st.caption("Colunas: nome (obrigatório), tecnico (opcional). Ex.: nome,tecnico")
            arquivo = st.file_uploader("Selecione o arquivo CSV", type=["csv"], key="eq_upload_file")

            if arquivo:
                try:
                    conteudo = arquivo.getvalue().decode("utf-8")
                    leitor = csv.DictReader(io.StringIO(conteudo))
                    linhas = list(leitor)

                    if not linhas:
                        st.error("⚠️ O arquivo está vazio.")
                    else:
                        colunas = [c.strip().lower() for c in (leitor.fieldnames or [])]
                        if "nome" not in colunas:
                            st.error("⚠️ Coluna obrigatória ausente: nome")
                        else:
                            st.dataframe(linhas, use_container_width=True)
                            confirma = st.checkbox("Confirmo a importação dessas equipes", key="eq_upload_confirm")

                            if st.button("Importar equipes", disabled=not confirma, key="eq_upload_btn"):
                                inseridas = 0
                                ignoradas = 0
                                erros = []

                                existentes = {e.nome.strip().lower() for e in camp.equipes_inscritas}

                                def get_valor(row, chave):
                                    for k, v in row.items():
                                        if k.strip().lower() == chave:
                                            return v
                                    return ""

                                for row in linhas:
                                    nome_row = (get_valor(row, "nome") or "").strip()
                                    tecnico_row = (get_valor(row, "tecnico") or "").strip() or "Sem técnico"

                                    if not nome_row or len(nome_row) < 3:
                                        erros.append(f"Nome inválido: '{nome_row}'")
                                        ignoradas += 1
                                        continue

                                    if nome_row.lower() in existentes:
                                        ignoradas += 1
                                        continue

                                    camp.cadastrar_equipe(Equipe(nome=nome_row, tecnico=tecnico_row))
                                    existentes.add(nome_row.lower())
                                    inseridas += 1

                                dao.salvar(camp)
                                if inseridas:
                                    st.success(f"✅ {inseridas} equipes importadas com sucesso!")
                                if ignoradas:
                                    st.warning(f"⚠️ {ignoradas} linhas ignoradas (duplicadas ou inválidas).")
                                if erros:
                                    st.info("Detalhes das linhas inválidas:")
                                    for msg in erros[:10]:
                                        st.write(f"- {msg}")
                                st.rerun()
                except Exception as e:
                    st.error(f"❌ Erro ao ler o CSV: {e}")

        with tab_editar:
            if not camp.equipes_inscritas:
                st.info("Nenhuma equipe para editar.")
            else:
                equipe_edit = st.selectbox(
                    "Selecione a equipe",
                    camp.equipes_inscritas,
                    format_func=lambda e: e.nome,
                    key="eq_edit_sel"
                )
                novo_nome = st.text_input("Novo nome", value=equipe_edit.nome, key="eq_edit_nome")
                novo_tecnico = st.text_input("Novo técnico", value=equipe_edit.tecnico, key="eq_edit_tecnico")
                
                if st.button("Salvar alterações", key="eq_edit_salvar"):
                    if not novo_nome.strip():
                        st.error("⚠️ O nome é obrigatório.")
                    else:
                        try:
                            equipe_edit.nome = novo_nome.strip()
                            equipe_edit.tecnico = novo_tecnico.strip()
                            dao.salvar(camp)
                            st.success("✅ Equipe atualizada com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erro: {e}")

        with tab_remover:
            if not camp.equipes_inscritas:
                st.info("Nenhuma equipe para remover.")
            else:
                equipe_rem = st.selectbox(
                    "Selecione a equipe",
                    camp.equipes_inscritas,
                    format_func=lambda e: e.nome,
                    key="eq_rem_sel"
                )
                
                st.warning(f"⚠️ Tem certeza que deseja remover **{equipe_rem.nome}**?")
                st.info(f"Esta equipe tem {len(equipe_rem.elenco)} jogadores")
                
                confirma = st.checkbox("Sim, remover esta equipe", key="eq_rem_confirm")
                
                if st.button("🗑️ Remover Equipe", key="eq_rem_btn", disabled=not confirma, type="primary"):
                    try:
                        camp.remover_equipe(equipe_rem.id)
                        dao.salvar(camp)
                        st.success(f"✅ Equipe '{equipe_rem.nome}' removida!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erro: {e}")

elif choice == "Jogadores":
    st.subheader("👥 Jogadores")
    if not camp.equipes_inscritas:
        st.info("Cadastre uma equipe antes de adicionar jogadores.")
    else:
        if is_admin():
            tab_listar, tab_criar, tab_editar, tab_remover = st.tabs(["Listar", "Cadastrar", "Editar", "Remover"])
        else:
            tab_listar = st.tabs(["Listar"])[0]

        with tab_listar:
            equipe_sel = st.selectbox(
                "Selecione a equipe",
                camp.equipes_inscritas,
                format_func=lambda e: e.nome,
                key="jog_list_eq",
            )
            if equipe_sel.elenco:
                for j in equipe_sel.elenco:
                    st.write(f"**#{j.numero}** - {j.nome} | {j.posicao}")
            else:
                st.info("Equipe sem jogadores.")

        if is_admin():
            with tab_criar:
                equipe_sel = st.selectbox(
                    "Equipe",
                    camp.equipes_inscritas,
                    format_func=lambda e: e.nome,
                    key="jog_add_eq",
                )
                nome = st.text_input("Nome do jogador", key="jog_nome", max_chars=50)
                numero = st.number_input("Número", min_value=1, max_value=99, step=1, key="jog_num")
                posicao = st.selectbox("Posição", ["Goleiro", "Zagueiro", "Lateral", "Volante", "Meia", "Atacante"], key="jog_pos")
                if st.button("Salvar jogador", key="jog_salvar"):
                    # Validações
                    if not nome.strip():
                        st.error("⚠️ O nome do jogador é obrigatório.")
                    elif len(nome.strip()) < 3:
                        st.error("⚠️ O nome deve ter pelo menos 3 caracteres.")
                    elif any(j.numero == numero for j in equipe_sel.elenco):
                        st.error(f"⚠️ O número {numero} já está sendo usado nesta equipe.")
                    else:
                        try:
                            # Encontra a equipe correta no campeonato
                            for equipe in camp.equipes_inscritas:
                                if equipe.id == equipe_sel.id:
                                    equipe.contratar_jogador(
                                        Jogador(nome=nome.strip(), numero=int(numero), posicao=posicao)
                                    )
                                    break
                            dao.salvar(camp)
                            st.success(f"✅ Jogador '{nome.strip()}' cadastrado com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erro ao cadastrar jogador: {e}")

            with tab_editar:
                equipe_edit = st.selectbox(
                    "Selecione a equipe",
                    [e for e in camp.equipes_inscritas if e.elenco],
                    format_func=lambda e: e.nome,
                    key="jog_edit_eq"
                )
                if equipe_edit and equipe_edit.elenco:
                    jogador_edit = st.selectbox(
                        "Selecione o jogador",
                        equipe_edit.elenco,
                        format_func=lambda j: f"{j.nome} (#{j.numero})",
                        key="jog_edit_sel"
                    )
                    novo_nome = st.text_input("Novo nome", value=jogador_edit.nome, key="jog_edit_nome")
                    novo_numero = st.number_input("Novo número", value=jogador_edit.numero, min_value=1, max_value=99, key="jog_edit_num")
                    nova_posicao = st.selectbox("Nova posição", ["Goleiro", "Zagueiro", "Lateral", "Volante", "Meia", "Atacante"], 
                                               index=["Goleiro", "Zagueiro", "Lateral", "Volante", "Meia", "Atacante"].index(jogador_edit.posicao),
                                               key="jog_edit_pos")
                    
                    if st.button("Salvar alterações", key="jog_edit_salvar"):
                        if not novo_nome.strip():
                            st.error("⚠️ O nome é obrigatório.")
                        else:
                            try:
                                jogador_edit.nome = novo_nome.strip()
                                jogador_edit.numero = int(novo_numero)
                                jogador_edit.posicao = nova_posicao
                                dao.salvar(camp)
                                st.success("✅ Jogador atualizado com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Erro: {e}")
                else:
                    st.info("Nenhuma equipe com jogadores.")

            with tab_remover:
                equipes_com_jogadores = [e for e in camp.equipes_inscritas if e.elenco]
                if not equipes_com_jogadores:
                    st.info("Nenhuma equipe com jogadores.")
                else:
                    equipe_rem = st.selectbox(
                        "Selecione a equipe",
                        equipes_com_jogadores,
                        format_func=lambda e: e.nome,
                        key="jog_rem_eq"
                    )
                    jogador_rem = st.selectbox(
                        "Selecione o jogador",
                        equipe_rem.elenco,
                        format_func=lambda j: f"{j.nome} (#{j.numero})",
                        key="jog_rem_sel"
                    )

                    st.warning(f"⚠️ Tem certeza que deseja remover **{jogador_rem.nome}**?")
                    confirma = st.checkbox("Sim, remover este jogador", key="jog_rem_confirm")

                    if st.button("🗑️ Remover Jogador", key="jog_rem_btn", disabled=not confirma, type="primary"):
                        try:
                            equipe_rem.remover_jogador(jogador_rem.id)
                            dao.salvar(camp)
                            st.success(f"✅ Jogador '{jogador_rem.nome}' removido!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erro: {e}")

elif choice == "Gerenciar Partidas":
    st.subheader("Partidas")
    if len(camp.equipes_inscritas) < 2:
        st.info("Cadastre pelo menos duas equipes para criar partidas.")
    else:
        tab_criar, tab_resultado = st.tabs(["Criar", "Finalizar"])

        with tab_criar:
            col1, col2 = st.columns(2)
            with col1:
                mandante = st.selectbox(
                    "Mandante",
                    camp.equipes_inscritas,
                    format_func=lambda x: x.nome,
                    key="jogo_mandante",
                )
            with col2:
                visitante = st.selectbox(
                    "Visitante",
                    camp.equipes_inscritas,
                    format_func=lambda x: x.nome,
                    key="jogo_visitante",
                )
            
            # Selecionar fase para Mata-mata
            if get_camp_tipo(camp) == "Mata-mata" and camp.fases:
                fase_selecionada = st.selectbox(
                    "Fase",
                    camp.fases,
                    format_func=lambda f: f.nome,
                    key="jogo_fase",
                )
            else:
                if get_camp_tipo(camp) == "Mata-mata" and not camp.fases:
                    st.info("Crie fases de mata-mata antes de cadastrar partidas.")
                fase_selecionada = None
            
            col3, col4 = st.columns(2)
            with col3:
                data_jogo = st.date_input("Data do jogo", value=datetime.now(), key="jogo_data")
            with col4:
                hora_jogo = st.time_input("Horário", value=datetime.now().time(), key="jogo_hora")
            
            local_jogo = st.text_input("Local/Estádio", value="Estádio Central", key="jogo_local", max_chars=100)
            
            # Escalação
            st.subheader("Escalação")
            st.caption("Regras: 11 titulares obrigatórios, até 12 reservas, total máx. 23 relacionados e 1 goleiro entre os titulares.")
            col_mand, col_visit = st.columns(2)
            
            with col_mand:
                st.write(f"**{mandante.nome}**")
                titulares_mand = st.multiselect(
                    "Titulares",
                    mandante.elenco,
                    format_func=lambda j: f"#{j.numero} - {j.nome}",
                    key="tit_mandante"
                )
                reservas_mand = st.multiselect(
                    "Reservas",
                    [j for j in mandante.elenco if j not in titulares_mand],
                    format_func=lambda j: f"#{j.numero} - {j.nome}",
                    key="res_mandante"
                )
            
            with col_visit:
                st.write(f"**{visitante.nome}**")
                titulares_visit = st.multiselect(
                    "Titulares",
                    visitante.elenco,
                    format_func=lambda j: f"#{j.numero} - {j.nome}",
                    key="tit_visitante"
                )
                reservas_visit = st.multiselect(
                    "Reservas",
                    [j for j in visitante.elenco if j not in titulares_visit],
                    format_func=lambda j: f"#{j.numero} - {j.nome}",
                    key="res_visitante"
                )
            
            if st.button("Criar jogo"):
                # Validações
                if mandante.id == visitante.id:
                    st.error("⚠️ Escolha equipes diferentes para o jogo.")
                elif not local_jogo.strip():
                    st.error("⚠️ Informe o local do jogo.")
                elif get_camp_tipo(camp) == "Mata-mata" and not fase_selecionada:
                    st.error("⚠️ Selecione uma fase para um campeonato Mata-mata.")
                else:
                    erros = []
                    if len(mandante.elenco) < REGRAS_ESCALACAO["titulares_exatos"]:
                        erros.append(f"⚠️ {mandante.nome}: elenco insuficiente para escalação (mínimo {REGRAS_ESCALACAO['titulares_exatos']}).")
                    if len(visitante.elenco) < REGRAS_ESCALACAO["titulares_exatos"]:
                        erros.append(f"⚠️ {visitante.nome}: elenco insuficiente para escalação (mínimo {REGRAS_ESCALACAO['titulares_exatos']}).")

                    erros += validar_escalacao(mandante, titulares_mand, reservas_mand, "Mandante")
                    erros += validar_escalacao(visitante, titulares_visit, reservas_visit, "Visitante")

                    if erros:
                        for msg in erros:
                            st.error(msg)
                    else:
                        try:
                            # Encontra as equipes corretas no campeonato
                            equipe_mandante = next(e for e in camp.equipes_inscritas if e.id == mandante.id)
                            equipe_visitante = next(e for e in camp.equipes_inscritas if e.id == visitante.id)

                            # Combina data e hora
                            data_hora = datetime.combine(data_jogo, hora_jogo)

                            novo_jogo = Jogo(
                                mandante=equipe_mandante,
                                visitante=equipe_visitante,
                                data=data_hora,
                                local=local_jogo.strip(),
                            )

                            # Define escalações
                            novo_jogo.escalacao_mandante = Escalacao(
                                titulares=[j.id for j in titulares_mand],
                                reservas=[j.id for j in reservas_mand]
                            )
                            novo_jogo.escalacao_visitante = Escalacao(
                                titulares=[j.id for j in titulares_visit],
                                reservas=[j.id for j in reservas_visit]
                            )

                            # Adiciona jogo à fase correta
                            if get_camp_tipo(camp) == "Mata-mata":
                                fase_selecionada.adicionar_jogo(novo_jogo)
                            else:
                                if not camp.fases:
                                    camp.adicionar_fase(Fase("Fase Única", 1))
                                camp.fases[0].adicionar_jogo(novo_jogo)

                            dao.salvar(camp)
                            if get_camp_tipo(camp) == "Mata-mata":
                                st.success(f"✅ Jogo criado na fase '{fase_selecionada.nome}': {mandante.nome} x {visitante.nome}")
                            else:
                                st.success(f"✅ Jogo criado: {mandante.nome} x {visitante.nome}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erro ao criar jogo: {e}")

        with tab_resultado:
            partidas_pendentes = [j for f in camp.fases for j in f.jogos if not j.finalizada]
            if not partidas_pendentes:
                st.info("Não há partidas pendentes.")
            else:
                jogo_sel = st.selectbox(
                    "Jogo",
                    partidas_pendentes,
                    format_func=lambda x: f"{x.mandante.nome} x {x.visitante.nome}",
                    key="jogo_sel",
                )
                
                # Abas para resultado e gols
                tab_placar, tab_gols = st.tabs(["Placar", "Gols Marcados"])
                
                with tab_placar:
                    col1, col2 = st.columns(2)
                    with col1:
                        g_m = st.number_input(
                            f"Gols {jogo_sel.mandante.nome}",
                            min_value=0,
                            max_value=50,
                            step=1,
                            key="g_m",
                        )
                    with col2:
                        g_v = st.number_input(
                            f"Gols {jogo_sel.visitante.nome}",
                            min_value=0,
                            max_value=50,
                            step=1,
                            key="g_v",
                        )
                    
                    st.info(f"📊 Resultado: {jogo_sel.mandante.nome} {g_m} x {g_v} {jogo_sel.visitante.nome}")
                    
                    if st.button("✅ Finalizar partida", type="primary"):
                        if get_camp_tipo(camp) == "Mata-mata" and int(g_m) == int(g_v):
                            st.error("⚠️ Em mata-mata não pode haver empate. Registre o vencedor (prorrogação/pênaltis).")
                        else:
                            try:
                                jogo_sel.finalizar_partida(int(g_m), int(g_v))
                                dao.salvar(camp)
                                st.success(f"✅ Partida finalizada: {jogo_sel.mandante.nome} {g_m} x {g_v} {jogo_sel.visitante.nome}")
                                st.balloons()
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Erro ao finalizar partida: {e}")
                
                with tab_gols:
                    st.write("### Registrar Gols")
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.subheader(f"{jogo_sel.mandante.nome}")
                        if st.button("➕ Adicionar Gol", key="add_gol_m"):
                            st.session_state['adding_gol_mandante'] = True
                        
                        if st.session_state.get('adding_gol_mandante'):
                            jogadores_mand = [jogo_sel.mandante.elenco_dict.get(jid) for jid in jogo_sel.escalacao_mandante.titulares + jogo_sel.escalacao_mandante.reservas]
                            jogadores_mand = [j for j in jogadores_mand if j]
                            
                            if jogadores_mand:
                                jogador_gol = st.selectbox(
                                    "Quem marcou?",
                                    jogadores_mand,
                                    format_func=lambda j: f"#{j.numero} - {j.nome}",
                                    key="jog_gol_m"
                                )
                                minuto = st.number_input("Minuto", min_value=0, max_value=120, key="min_gol_m")
                                
                                if st.button("Confirmar Gol", key="conf_gol_m"):
                                    novo_gol = Gol(
                                        jogador_id=jogador_gol.id,
                                        jogador_nome=jogador_gol.nome,
                                        equipe_id=jogo_sel.mandante.id,
                                        minuto=int(minuto)
                                    )
                                    jogo_sel.gols.append(novo_gol)
                                    st.success(f"⚽ Gol de {jogador_gol.nome}!")
                                    st.session_state['adding_gol_mandante'] = False
                            else:
                                st.warning("Nenhum jogador escalado para este time")
                        
                        st.write("**Gols marcados:**")
                        gols_mand = [g for g in jogo_sel.gols if g.equipe_id == jogo_sel.mandante.id]
                        if gols_mand:
                            for gol in gols_mand:
                                st.write(f"⚽ {gol.jogador_nome} ({gol.minuto}')")
                        else:
                            st.info("Nenhum gol registrado")
                    
                    with col2:
                        st.subheader(f"{jogo_sel.visitante.nome}")
                        if st.button("➕ Adicionar Gol", key="add_gol_v"):
                            st.session_state['adding_gol_visitante'] = True
                        
                        if st.session_state.get('adding_gol_visitante'):
                            jogadores_visit = [jogo_sel.visitante.elenco_dict.get(jid) for jid in jogo_sel.escalacao_visitante.titulares + jogo_sel.escalacao_visitante.reservas]
                            jogadores_visit = [j for j in jogadores_visit if j]
                            
                            if jogadores_visit:
                                jogador_gol = st.selectbox(
                                    "Quem marcou?",
                                    jogadores_visit,
                                    format_func=lambda j: f"#{j.numero} - {j.nome}",
                                    key="jog_gol_v"
                                )
                                minuto = st.number_input("Minuto", min_value=0, max_value=120, key="min_gol_v")
                                
                                if st.button("Confirmar Gol", key="conf_gol_v"):
                                    novo_gol = Gol(
                                        jogador_id=jogador_gol.id,
                                        jogador_nome=jogador_gol.nome,
                                        equipe_id=jogo_sel.visitante.id,
                                        minuto=int(minuto)
                                    )
                                    jogo_sel.gols.append(novo_gol)
                                    st.success(f"⚽ Gol de {jogador_gol.nome}!")
                                    st.session_state['adding_gol_visitante'] = False
                            else:
                                st.warning("Nenhum jogador escalado para este time")
                        
                        st.write("**Gols marcados:**")
                        gols_visit = [g for g in jogo_sel.gols if g.equipe_id == jogo_sel.visitante.id]
                        if gols_visit:
                            for gol in gols_visit:
                                st.write(f"⚽ {gol.jogador_nome} ({gol.minuto}')")
                        else:
                            st.info("Nenhum gol registrado")

elif choice == "Fases/Grupos":
    st.subheader("📋 Gerenciar Fases e Grupos")
    
    if not camp.fases:
        st.info("Nenhuma fase criada ainda.")
    
    tab_listar, tab_criar, tab_editar = st.tabs(["Listar", "Criar Fase", "Editar"])
    
    with tab_listar:
        if not camp.fases:
            st.info("Nenhuma fase cadastrada.")
        else:
            for fase in camp.fases:
                with st.container():
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        tipo_badge = "📊 Corridos" if fase.tipo == "Corridos" else "⚔️ Mata-Mata"
                        st.write(f"### {fase.nome}")
                        st.caption(tipo_badge)
                    with col2:
                        if fase.grupo:
                            st.metric("Grupo", fase.grupo)
                        st.metric("Ordem", fase.ordem)
                    with col3:
                        st.metric("Jogos", len(fase.jogos))
                    st.divider()
    
    with tab_criar:
        nome_fase = st.text_input("Nome da Fase", key="fase_nome", max_chars=50, placeholder="Ex: Primeira Rodada")
        ordem = st.number_input("Ordem", min_value=1, step=1, key="fase_ordem")
        tipo_fase = st.selectbox("Tipo", ["Corridos", "Mata-mata"], key="fase_tipo")
        usar_grupo = st.checkbox("Usar grupos?", key="usar_grupo")
        grupo_fase = ""
        
        if usar_grupo:
            grupo_fase = st.text_input("Letra do Grupo", key="grupo_letra", max_chars=1, placeholder="A").upper()
        
        if st.button("Criar Fase", key="criar_fase"):
            if not nome_fase.strip():
                st.error("⚠️ Informe o nome da fase.")
            elif usar_grupo and (not grupo_fase or grupo_fase not in "ABCDEFGH"):
                st.error("⚠️ Informe uma letra de A a H para o grupo.")
            else:
                try:
                    nova_fase = Fase(nome=nome_fase.strip(), ordem=int(ordem), tipo=tipo_fase, grupo=grupo_fase)
                    camp.adicionar_fase(nova_fase)
                    dao.salvar(camp)
                    st.success(f"✅ Fase '{nome_fase.strip()}' criada!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Erro: {e}")
    
    with tab_editar:
        if not camp.fases:
            st.info("Nenhuma fase para editar.")
        else:
            fase_edit = st.selectbox(
                "Selecione a fase",
                camp.fases,
                format_func=lambda f: f.nome,
                key="fase_edit_sel"
            )
            
            novo_nome = st.text_input("Novo nome", value=fase_edit.nome, key="fase_edit_nome")
            novo_tipo = st.selectbox("Tipo", ["Corridos", "Mata-mata"], 
                                    index=0 if fase_edit.tipo == "Corridos" else 1,
                                    key="fase_edit_tipo")
            
            if st.button("Salvar alterações", key="fase_edit_salvar"):
                if not novo_nome.strip():
                    st.error("⚠️ O nome é obrigatório.")
                else:
                    try:
                        fase_edit.nome = novo_nome.strip()
                        fase_edit.tipo = novo_tipo
                        dao.salvar(camp)
                        st.success("✅ Fase atualizada!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erro: {e}")

elif choice == "Campeonatos":
    st.subheader("Gerenciar Campeonatos")
    tab_listar, tab_criar, tab_editar, tab_excluir = st.tabs(["Listar", "Criar", "Editar", "Excluir"])
    
    with tab_listar:
        todos = dao.listar_todos()
        if not todos:
            st.info("Nenhum campeonato cadastrado.")
        else:
            for c in todos:
                ativo = "✅" if c.id == camp.id else ""
                st.write(f"{ativo} **{c.nome}** - {c.ano} - {get_camp_tipo(c)} (ID: {c.id[:8]}...)")
    
    with tab_criar:
        nome_novo = st.text_input("Nome do campeonato", key="camp_nome", max_chars=100)
        ano_novo = st.number_input("Ano", min_value=2000, max_value=2100, value=datetime.now().year, step=1, key="camp_ano")
        tipo_novo = st.selectbox("Formato", ["Pontos corridos", "Mata-mata"], key="camp_tipo")
        if st.button("Criar campeonato", key="camp_criar"):
            # Validações
            if not nome_novo.strip():
                st.error("⚠️ O nome do campeonato é obrigatório.")
            elif len(nome_novo.strip()) < 3:
                st.error("⚠️ O nome deve ter pelo menos 3 caracteres.")
            elif any(c.nome.lower() == nome_novo.strip().lower() and c.ano == ano_novo for c in dao.listar_todos()):
                st.error(f"⚠️ Já existe um campeonato '{nome_novo.strip()}' em {ano_novo}.")
            else:
                try:
                    novo_camp = Campeonato(nome=nome_novo.strip(), ano=int(ano_novo), tipo=tipo_novo)
                    dao.salvar(novo_camp)
                    st.session_state.campeonato_id = novo_camp.id
                    st.success(f"✅ Campeonato '{nome_novo.strip()}' criado e selecionado!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Erro ao criar campeonato: {e}")
    
    with tab_editar:
        if not dao.listar_todos():
            st.info("Nenhum campeonato para editar.")
        else:
            camp_edit = st.selectbox(
                "Selecione o campeonato",
                dao.listar_todos(),
                format_func=lambda c: f"{c.nome} ({c.ano}) - {get_camp_tipo(c)}",
                key="camp_edit_select"
            )
            novo_nome = st.text_input("Novo nome", value=camp_edit.nome, key="camp_edit_nome")
            novo_ano = st.number_input("Novo ano", min_value=2000, max_value=2100, value=camp_edit.ano, step=1, key="camp_edit_ano")
            novo_tipo = st.selectbox(
                "Formato",
                ["Pontos corridos", "Mata-mata"],
                index=0 if camp_edit.tipo == "Pontos corridos" else 1,
                key="camp_edit_tipo"
            )
            if st.button("Salvar alterações", key="camp_edit_salvar"):
                if not novo_nome.strip():
                    st.error("Informe o nome do campeonato.")
                else:
                    camp_edit.nome = novo_nome.strip()
                    camp_edit.ano = int(novo_ano)
                    camp_edit.tipo = novo_tipo
                    dao.salvar(camp_edit)
                    st.success("Campeonato atualizado.")
                    st.rerun()
    
    with tab_excluir:
        if not dao.listar_todos():
            st.info("Nenhum campeonato para excluir.")
        else:
            camp_del = st.selectbox(
                "Selecione o campeonato",
                dao.listar_todos(),
                format_func=lambda c: f"{c.nome} ({c.ano})",
                key="camp_del_select"
            )
            
            # Mostrar informações do campeonato
            st.warning(f"⚠️ **ATENÇÃO:** Você está prestes a excluir:")
            st.write(f"- **Campeonato:** {camp_del.nome} ({camp_del.ano})")
            st.write(f"- **Equipes:** {len(camp_del.equipes_inscritas)}")
            total_jogos = sum(len(f.jogos) for f in camp_del.fases)
            st.write(f"- **Jogos:** {total_jogos}")
            st.write("")
            st.error("Esta ação não pode ser desfeita!")
            
            # Confirmação dupla
            confirma = st.checkbox("Sim, quero excluir este campeonato", key="confirm_del")
            
            if st.button("🗑️ EXCLUIR DEFINITIVAMENTE", key="camp_del_confirm", disabled=not confirma, type="primary"):
                try:
                    if dao.excluir(camp_del.id):
                        # Recarregar dados do arquivo para sincronizar
                        dao.reload()
                        # Limpar o campeonato ativo se foi o excluído
                        if camp_del.id == st.session_state.campeonato_id:
                            st.session_state.campeonato_id = None
                        st.success(f"✅ Campeonato '{camp_del.nome}' excluído com sucesso.")
                        st.rerun()
                    else:
                        st.error("❌ Erro: Campeonato não encontrado.")
                except Exception as e:
                    st.error(f"❌ Erro ao excluir campeonato: {e}")

st.sidebar.markdown("---")
st.sidebar.caption(f"👤 Logado como: **{st.session_state.get('username', 'Admin')}** ({st.session_state.get('user_role', 'admin')})")
if st.sidebar.button("Sair"):
    st.session_state.logged_in = False
    st.session_state.user_role = None
    st.session_state.username = None
    st.rerun()