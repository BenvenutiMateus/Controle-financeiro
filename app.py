import streamlit as st
import sqlite3
import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta
import plotly.express as px
import numpy as np
from sklearn.ensemble import RandomForestRegressor
import libsql_experimental as libsql
import google.generativeai as genai
import json
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar']

CATEGORIAS_DESPESA = [
    "Moradia", "Alimentação", "Transporte", "Saúde", "Educação", "Lazer",
    "Assinaturas", "Impostos", "Mercado", "Farmácia", "Outros"
]

CATEGORIAS_RECEITA = [
    "Salário", "Freelance", "Investimentos", "Vendas", "Reembolso", "Outros"
]

METODOS_PAGAMENTO = ["Pix", "Cartão de Crédito", "Boleto", "Dinheiro", "Transferência"]
FREQUENCIAS = ["Mensal", "Único", "Anual", "Semanal"]
STATUS_DESPESA = ["Pendente", "Pago", "Agendado", "Cancelado"]

def normalizar_texto(valor):
    return " ".join(str(valor).strip().split()) if valor is not None else ""

def validar_lancamento_despesa(data, descricao, categoria, valor, valor_pago, status):
    erros = []
    descricao = normalizar_texto(descricao)
    categoria = normalizar_texto(categoria)
    status = normalizar_texto(status)

    if not isinstance(data, datetime.date):
        erros.append("Data inválida.")
    if not descricao:
        erros.append("Descrição é obrigatória.")
    if len(descricao) > 120:
        erros.append("Descrição deve ter no máximo 120 caracteres.")
    if not categoria:
        erros.append("Categoria é obrigatória.")
    if valor is None or valor < 0:
        erros.append("Valor previsto deve ser maior ou igual a zero.")
    if valor_pago is None or valor_pago < 0:
        erros.append("Valor pago deve ser maior ou igual a zero.")
    if status not in STATUS_DESPESA:
        erros.append("Status inválido.")
    if status == "Pago" and valor_pago <= 0:
        erros.append("Para status Pago, informe valor pago maior que zero.")
    if valor == 0 and valor_pago == 0:
        erros.append("Informe ao menos um valor maior que zero.")
    if valor > 0 and valor_pago > valor and status != "Pago":
        erros.append("Valor pago não pode ser maior que o valor previsto quando o status não é Pago.")

    return erros, descricao, categoria

def validar_receita(data, descricao, categoria, valor):
    erros = []
    descricao = normalizar_texto(descricao)
    categoria = normalizar_texto(categoria)

    if not isinstance(data, datetime.date):
        erros.append("Data inválida.")
    if not descricao:
        erros.append("Descrição é obrigatória.")
    if len(descricao) > 120:
        erros.append("Descrição deve ter no máximo 120 caracteres.")
    if not categoria:
        erros.append("Categoria é obrigatória.")
    if valor is None or valor <= 0:
        erros.append("Valor da receita deve ser maior que zero.")

    return erros, descricao, categoria

def get_google_calendar_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                st.warning("Arquivo credentials.json não encontrado. A integração com o Google Calendar está desativada.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('calendar', 'v3', credentials=creds)

def gerar_resposta_ia(prompt, modelo_nome='gemini-3.6-flash'):
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    modelo = genai.GenerativeModel(modelo_nome)
    resposta = modelo.generate_content(prompt)
    texto_limpo = resposta.text.replace("```json", "").replace("```", "").strip()
    return json.loads(texto_limpo)


# ==========================================
# 1. ARQUITETURA DE BANCOS DE DADOS
# ==========================================
st.set_page_config(page_title="Controle Pessoal", layout="wide", page_icon="💰")
st.markdown("""
<style>
    :root {
        --ink: #263a35;
        --muted: #71827c;
        --line: #e5eee9;
        --surface: #ffffff;
        --mint: #e8f4ef;
        --lavender: #f1eef8;
    }
    .stApp {
        background: #f8faf9;
        color: var(--ink);
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f2f8f5 0%, #f7f6fb 100%);
        border-right: 1px solid var(--line);
    }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        color: var(--ink);
    }
    .block-container {
        max-width: 1180px;
        padding-top: 2.5rem;
        padding-bottom: 3rem;
    }
    h1, h2, h3 { color: var(--ink); letter-spacing: -0.02em; }
    [data-testid="stMetric"] {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 18px;
        padding: 1rem 1.1rem;
        box-shadow: 0 8px 24px rgba(54, 76, 68, .04);
    }
    [data-testid="stMetricLabel"] { color: var(--muted); }
    [data-testid="stMetricValue"] { color: var(--ink); }
    input, textarea, [data-baseweb="select"] > div,
    [data-testid="stNumberInput"] input,
    [data-testid="stDateInput"] input {
        background: #ffffff !important;
        color: var(--ink) !important;
        border-color: var(--line) !important;
    }
    input::placeholder, textarea::placeholder { color: #9aaaa4 !important; }
    [data-baseweb="popover"], [data-baseweb="menu"],
    [data-baseweb="select"] [role="listbox"] {
        background: #ffffff !important;
        color: var(--ink) !important;
    }
    [data-baseweb="menu"] li, [role="option"] {
        color: var(--ink) !important;
        background: #ffffff !important;
    }
    [data-baseweb="menu"] li:hover, [role="option"]:hover {
        background: var(--mint) !important;
    }
    [data-testid="stDataFrame"], [data-testid="stTable"] {
        border: 1px solid var(--line);
        border-radius: 16px;
        overflow: hidden;
        background: #ffffff !important;
    }
    [data-testid="stDataFrame"] > div,
    [data-testid="stDataFrame"] iframe,
    [data-testid="stTable"] > div {
        background: #ffffff !important;
    }
    [data-testid="stDataFrame"] * { color: var(--ink) !important; }
    [data-testid="stDataFrame"] [role="columnheader"],
    [data-testid="stDataFrame"] [role="gridcell"] {
        background: #ffffff !important;
        border-color: var(--line) !important;
    }
    [data-testid="stDataFrame"] [role="columnheader"] {
        background: #f1f7f4 !important;
        font-weight: 700 !important;
    }
    [data-testid="stDataFrame"] svg { fill: var(--muted) !important; }
    [data-testid="stDataEditor"] {
        background: #ffffff !important;
        border: 1px solid var(--line);
        border-radius: 16px;
        overflow: hidden;
    }
    [data-testid="stDataEditor"] iframe { background: #ffffff !important; }
    [data-testid="stAlert"] {
        background: #ffffff !important;
        color: var(--ink) !important;
        border-radius: 14px;
    }
    button[kind="secondary"] {
        background: #ffffff !important;
        color: var(--ink) !important;
        border-color: var(--line) !important;
    }
    button[kind="primary"] {
        background: #7eb79f !important;
        color: #ffffff !important;
        border-color: #7eb79f !important;
    }
    div[data-testid="stForm"], div[data-testid="stExpander"] {
        border: 1px solid var(--line);
        border-radius: 18px;
        background: rgba(255,255,255,.72);
    }
    .dashboard-hero {
        padding: 1.5rem 1.7rem;
        border-radius: 26px;
        background: linear-gradient(135deg, #eaf6f0 0%, #f3f0fa 100%);
        border: 1px solid #e1eee8;
        margin-bottom: 1.3rem;
    }
    .dashboard-hero h1 { margin: 0; }
    .dashboard-hero p { margin: .45rem 0 0; color: var(--muted); }
    .section-label {
        color: #769188;
        font-size: .78rem;
        font-weight: 700;
        letter-spacing: .08em;
        text-transform: uppercase;
        margin: 1.4rem 0 .65rem;
    }
    .soft-card {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 20px;
        padding: 1rem 1.15rem;
        box-shadow: 0 8px 24px rgba(54, 76, 68, .035);
    }
    .task-card {
        background: #ffffff;
        border: 1px solid var(--line);
        border-left: 5px solid #9bcbb5;
        border-radius: 17px;
        padding: .9rem 1rem;
        margin: .55rem 0;
        box-shadow: 0 6px 18px rgba(54, 76, 68, .035);
    }
    .task-card.overdue { border-left-color: #d99a9a; background: #fffafa; }
    .task-card.done { border-left-color: #aeb6d8; background: #fafaff; }
    .task-title { color: var(--ink); font-weight: 700; font-size: 1rem; }
    .task-meta { color: var(--muted); font-size: .82rem; margin-top: .3rem; }
    .mobile-actions button { min-height: 2.8rem; }
    @media (max-width: 700px) {
        .block-container {
            padding: 1.1rem .8rem 2rem;
        }
        [data-testid="stSidebar"] {
            min-width: 82vw;
            max-width: 82vw;
        }
        .dashboard-hero {
            padding: 1.1rem 1rem;
            border-radius: 20px;
        }
        h1 { font-size: 1.65rem !important; }
        h2 { font-size: 1.3rem !important; }
        h3 { font-size: 1.1rem !important; }
        [data-testid="stMetric"] {
            padding: .75rem;
            border-radius: 14px;
        }
        [data-testid="stMetricValue"] { font-size: 1.25rem; }
        .task-card {
            padding: .75rem;
            margin: .45rem 0;
        }
        [data-testid="stHorizontalBlock"] {
            gap: .55rem;
        }
        button, input, textarea {
            min-height: 2.7rem;
        }
        [data-testid="stDataFrame"] {
            overflow-x: auto;
        }
    }
</style>
""", unsafe_allow_html=True)

# --- BANCO PESSOAL (Conecta direto no Turso do Usuário Logado) ---
def get_personal_connection():
    conn = libsql.connect(
        database=st.session_state["user"]["turso_url"],
        auth_token=st.session_state["user"]["turso_token"]
    )
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rotinas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            icone TEXT NOT NULL DEFAULT '✨',
            cor TEXT NOT NULL DEFAULT '#8EC5B5',
            ativa INTEGER NOT NULL DEFAULT 1
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rotina_registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rotina_id INTEGER NOT NULL,
            data DATE NOT NULL,
            concluida INTEGER NOT NULL DEFAULT 0,
            UNIQUE(rotina_id, data)
        )
    ''')
    cursor.execute("PRAGMA table_info(receitas)")
    colunas_receitas = {linha[1] for linha in cursor.fetchall()}
    if not colunas_receitas:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS receitas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data DATE NOT NULL,
                descricao TEXT NOT NULL,
                valor REAL NOT NULL,
                observacao TEXT,
                recorrente TEXT NOT NULL,
                frequencia TEXT,
                categoria TEXT NOT NULL DEFAULT 'Outros'
            )
        ''')
    elif "categoria" not in colunas_receitas:
        cursor.execute("ALTER TABLE receitas ADD COLUMN categoria TEXT NOT NULL DEFAULT 'Outros'")
    conn.commit()
    return conn

# ==========================================
# 2. SISTEMA DE LOGIN COM SECRETS
# ==========================================
if "user" not in st.session_state:
    st.session_state["user"] = None

def autenticar_usuario(username, senha):
    usuarios = st.secrets.get("usuarios", {})
    perfil = usuarios.get(username)

    if not perfil:
        return None

    if perfil.get("senha") != senha:
        return None

    user_data = {
        "id": username,
        "username": username,
        "nome": perfil.get("nome", username),
        "turso_url": perfil.get("turso_url"),
        "turso_token": perfil.get("turso_token"),
    }

    try:
        conn_p = libsql.connect(database=user_data["turso_url"], auth_token=user_data["turso_token"])
        cursor_p = conn_p.cursor()
        cursor_p.execute('''
            CREATE TABLE IF NOT EXISTS lancamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data DATE NOT NULL,
                descricao TEXT NOT NULL,
                valor REAL NOT NULL,
                observacao TEXT,
                recorrente TEXT NOT NULL,
                status TEXT NOT NULL,
                categoria TEXT NOT NULL,
                metodo_pagamento TEXT NOT NULL,
                frequencia TEXT,
                valor_pago REAL
            )
        ''')
        cursor_p.execute('''
            CREATE TABLE IF NOT EXISTS receitas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data DATE NOT NULL,
                descricao TEXT NOT NULL,
                valor REAL NOT NULL,
                observacao TEXT,
                recorrente TEXT NOT NULL,
                frequencia TEXT,
                categoria TEXT NOT NULL
        )
        ''')
        cursor_p.execute('''
            CREATE TABLE IF NOT EXISTS tarefas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                data_vencimento DATE,
                status TEXT NOT NULL
            )
        ''')
        cursor_p.execute('''
            CREATE TABLE IF NOT EXISTS rotinas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                icone TEXT NOT NULL DEFAULT '✨',
                cor TEXT NOT NULL DEFAULT '#8EC5B5',
                ativa INTEGER NOT NULL DEFAULT 1
            )
        ''')
        cursor_p.execute('''
            CREATE TABLE IF NOT EXISTS rotina_registros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rotina_id INTEGER NOT NULL,
                data DATE NOT NULL,
                concluida INTEGER NOT NULL DEFAULT 0,
                UNIQUE(rotina_id, data)
            )
        ''')
        cursor_p.execute('''
            CREATE TABLE IF NOT EXISTS agenda (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT NOT NULL,
                titulo TEXT NOT NULL,
                data_hora DATETIME
            )
        ''')
        cursor_p.execute('''
            CREATE TABLE IF NOT EXISTS estudos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT NOT NULL,
                titulo TEXT NOT NULL,
                horas REAL,
                data DATE
            )
        ''')
        cursor_p.execute('''
            CREATE TABLE IF NOT EXISTS projetos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                categoria TEXT NOT NULL,
                nome TEXT NOT NULL,
                status TEXT NOT NULL
            )
        ''')
        conn_p.commit()
        conn_p.close()
        return user_data
    except Exception as e:
        st.error(f"Erro ao conectar ao seu banco Turso. Verifique suas chaves! Detalhes: {e}")
        return None

if st.session_state["user"] is None:
    st.title("💰 Controle Financeiro Pessoal")

    usuarios_disponiveis = sorted(st.secrets.get("usuarios", {}).keys())

    if not usuarios_disponiveis:
        st.warning("Nenhum usuário configurado em secrets. Adicione usuários em [usuarios.<nome>] no arquivo .streamlit/secrets.toml")
        st.stop()

    with st.form("form_login"):
        usuario = st.selectbox("Usuário", usuarios_disponiveis)
        senha = st.text_input("Senha", type="password", autocomplete="current-password")

        if st.form_submit_button("Entrar"):
            user = autenticar_usuario(usuario, senha)
            if user:
                st.session_state["user"] = user
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos.")

    st.stop()

# ==========================================
# 3. PAINEL PRINCIPAL
# ==========================================
nome_usuario = st.session_state["user"]["nome"]

st.sidebar.title(f"👤 {nome_usuario}")
st.sidebar.caption("Conectado ao Banco Privado (Turso) 🟢")
if st.sidebar.button("Sair"):
    st.session_state["user"] = None
    st.rerun()

st.sidebar.divider()
menu_principal = st.sidebar.selectbox(
    "Módulo",
    ["Dashboard", "Finanças", "Tarefas", "Rotinas"]
)

st.sidebar.divider()
if menu_principal == "Finanças":
    menu = st.sidebar.radio("Sub-menu", ["Lançamentos", "Receitas", "Despesas", "Orçamento", "Análises", "Gerar Recorrentes"])
else:
    menu = menu_principal

# ==========================================
# DASHBOARD ANALYTICS 
# ==========================================
if menu == "Análises":
    st.header("📈 Dashboard Analytics Preditivo")
    
    c1, c2 = st.columns(2)
    filtro_mes = c1.selectbox("Mês", list(range(1, 13)) + ['Todos'], index=datetime.date.today().month - 1)
    filtro_ano = c2.number_input("Ano", min_value=2024, max_value=2030, value=datetime.date.today().year)
    
    conn = get_personal_connection()
    df_completo = pd.read_sql_query("SELECT * FROM lancamentos", conn)
    conn.close()
    
    if df_completo.empty:
        st.info("Nenhum dado encontrado para gerar análises.")
    else:
        df_completo["dt_data"] = pd.to_datetime(df_completo["data"])
    
        if filtro_mes != "Todos":
            df_filtrado = df_completo[
                (df_completo["dt_data"].dt.month == filtro_mes) &
                (df_completo["dt_data"].dt.year == filtro_ano)
            ]
            mes_anterior = filtro_mes - 1 if filtro_mes > 1 else 12
            ano_anterior = filtro_ano if filtro_mes > 1 else filtro_ano - 1
            df_anterior = df_completo[(df_completo["dt_data"].dt.month == mes_anterior) & (df_completo["dt_data"].dt.year == ano_anterior)]
        else:
            df_filtrado = df_completo[
                df_completo["dt_data"].dt.year == filtro_ano
            ]
            df_anterior = df_completo[df_completo["dt_data"].dt.year == (filtro_ano - 1)]
        
        tot_atual = df_filtrado["valor"].sum() if df_filtrado is not None else 0
        tot_anterior = df_anterior["valor"].sum() if df_anterior is not None else 0
        delta_perc = ((tot_atual - tot_anterior) / tot_anterior * 100) if tot_anterior > 0 else 0
        
        previsao_rf = 0
        if filtro_mes != "Todos":
            mes_inicio = filtro_mes if filtro_mes > 1 else 1
            df_historico = df_completo[df_completo["dt_data"] < datetime.datetime(filtro_ano, mes_inicio, 1)]
            if len(df_historico) > 10:
                df_historico["mes"] = df_historico["dt_data"].dt.month
                df_historico["ano"] = df_historico["dt_data"].dt.year
                df_rf = df_historico.groupby(["ano", "mes"])["valor"].sum().reset_index()
                if len(df_rf) > 3:
                    X = df_rf[["ano", "mes"]]
                    y = df_rf["valor"]
                    modelo_rf = RandomForestRegressor(n_estimators=50, random_state=42)
                    modelo_rf.fit(X, y)
                    previsao_rf = modelo_rf.predict([[filtro_ano, filtro_mes]])[0]
        
        st.subheader("Visão Geral do Mês")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Gasto Total", f"R$ {tot_atual:,.2f}", f"{delta_perc:.1f}% vs Mês Anterior", delta_color="inverse")
        m2.metric("Total Pago", f"R$ {df_filtrado['valor_pago'].sum():,.2f}")
        m3.metric("Pendente", f"R$ {(tot_atual - df_filtrado['valor_pago'].sum()):,.2f}")
        
        if previsao_rf > 0:
            m4.metric("Previsão Estatística (ML)", f"R$ {previsao_rf:,.2f}", "Modelo Random Forest", delta_color="off")
        else:
            m4.metric("Previsão Estatística", "Dados insuficientes")

        st.divider()
        st.subheader("🚨 Detecção de Anomalias")
        anomalias = []
        df_hist_cat = df_completo.groupby(["categoria", df_completo["dt_data"].dt.to_period("M")])["valor"].sum().reset_index()
        estatisticas = df_hist_cat.groupby("categoria")["valor"].agg(['mean', 'std']).fillna(0)
        
        gasto_cat_atual = df_filtrado.groupby("categoria")["valor"].sum()
        for cat, valor in gasto_cat_atual.items():
            if cat in estatisticas.index:
                media = estatisticas.loc[cat, 'mean']
                desvio = estatisticas.loc[cat, 'std']
                limite_superior = media + (2 * desvio)
                if valor > limite_superior and desvio > 0:
                    anomalias.append(f"O gasto em **{cat}** (R$ {valor:.2f}) está anormal. Sua média histórica é R$ {media:.2f}.")
        
        if anomalias:
            for alerta in anomalias:
                st.warning(alerta)
        else:
            st.success("Nenhuma anomalia financeira detectada neste mês.")
            
        st.divider()

        c_graf1, c_graf2 = st.columns(2)
        with c_graf1:
            st.subheader("Distribuição por Método de pagamento")
            df_pagamento = df_filtrado.groupby("metodo_pagamento")["valor"].sum().reset_index()
            fig_pagamento = px.pie(df_pagamento, values = "valor", names = 'metodo_pagamento', hole = 0.3)
            st.plotly_chart(fig_pagamento, width='stretch')
            
        with c_graf2:
            st.subheader("Distribuição por Categoria")
            df_pizza = df_filtrado.groupby("categoria")["valor"].sum().reset_index()
            fig_pizza = px.pie(df_pizza, values="valor", names="categoria", hole=0.4)
            st.plotly_chart(fig_pizza, width="stretch")
            
        st.divider()
        st.subheader("Top 5 Maiores Despesas")
        df_top5 = df_filtrado.sort_values(by="valor", ascending=False).head(5)[["descricao", "categoria", "valor"]]
        st.dataframe(df_top5, use_container_width=True, hide_index=True)
        
        
        st.subheader("Linha do Tempo últimos 12 Meses (Por Categoria)")
        um_ano_atras = datetime.date.today() - relativedelta(months=11)
        um_ano_atras = um_ano_atras.replace(day=1)
        df_12m = df_completo[df_completo["dt_data"].dt.date >= um_ano_atras].copy()
        
        if not df_12m.empty:
            df_12m["Mes_Ano"] = df_12m["dt_data"].dt.strftime('%m/%Y')

            df_linha = (
                df_12m
                .groupby(["Mes_Ano", "categoria"])["valor"]
                .sum()
                .reset_index()
            )
            
            ordem_meses = (
                df_12m[["Mes_Ano", "dt_data"]]
                .drop_duplicates()
                .sort_values("dt_data")["Mes_Ano"]
                .tolist()
            )
            
            fig_linha = px.bar(
                df_linha,
                x="Mes_Ano",
                y="valor",
                color="categoria",
                barmode="stack",
                category_orders={"Mes_Ano": ordem_meses}
            )
            
            st.plotly_chart(fig_linha, width="stretch")

# ==========================================
# NOVO LANÇAMENTO
# ==========================================

elif menu == "Despesas":   
    f1, f2 = st.columns(2)
    filtro_mes = f1.selectbox("Mês", ["Todos"] + list(range(1, 13)), index=datetime.date.today().month)
    filtro_ano = f2.number_input("Ano", min_value=2024, max_value=2030, value=datetime.date.today().year)
    
    conn = get_personal_connection()
    query = "SELECT id, data, descricao, valor, valor_pago, status, categoria, metodo_pagamento, recorrente, frequencia, observacao FROM lancamentos WHERE 1=1"
    params = []
    
    if filtro_mes != "Todos":
        query += " AND strftime('%m', data) = ? AND strftime('%Y', data) = ?"
        params.extend([f"{filtro_mes:02d}", str(filtro_ano)])
        
    query += " ORDER BY data ASC"
    df = pd.read_sql_query(query, conn, params=tuple(params))
    conn.close()
    
    if df.empty:
        st.info("Nenhum registro encontrado.")
    else:
        hoje = datetime.date.today()
        df["data"] = pd.to_datetime(df["data"]).dt.date
        total_previsto = df["valor"].sum()
        total_pago = df["valor_pago"].sum()
        total_pendente = max(total_previsto - total_pago, 0)
        resumo1, resumo2, resumo3 = st.columns(3)
        resumo1.metric("Total previsto", f"R$ {total_previsto:,.2f}")
        resumo2.metric("Total pago", f"R$ {total_pago:,.2f}")
        resumo3.metric("Em aberto", f"R$ {total_pendente:,.2f}")
        df["Excluir"] = False
        
        df["foi_pago"] = df["status"] == "Pago"
        
        def definir_situacao(row):
            if row["foi_pago"]: return "🟢 Pago"
            elif row["data"] < hoje: return "🔴 Atrasado"
            else: return "🟡 A Pagar (No Prazo)"

        df["Situação"] = df.apply(definir_situacao, axis=1)
        
        df_exibicao = df[["id", "Excluir", "foi_pago", "Situação", "data", "descricao", "valor", "valor_pago", "categoria", "metodo_pagamento", "recorrente", "frequencia", "observacao"]]
        
        def colorir_tabela(val):
            if val == "🟢 Pago": return 'background-color: #d4edda; color: #155724; font-weight: bold'
            elif val == "🔴 Atrasado": return 'background-color: #f8d7da; color: #721c24; font-weight: bold'
            elif val == "🟡 A Pagar (No Prazo)": return 'background-color: #fff3cd; color: #856404; font-weight: bold'
            return ''
        
        df_colorido = df_exibicao.style.map(colorir_tabela, subset=["Situação"])
        
        with st.form("form_edicao"):
            df_editado = st.data_editor(
                df_colorido,
                column_config={
                    "id": st.column_config.NumberColumn("ID", disabled=True),
                    "Excluir": st.column_config.CheckboxColumn("❌ Excluir", default=False),
                    "foi_pago": st.column_config.CheckboxColumn("✅ Pago?", default=False),
                    "Situação": st.column_config.TextColumn("Situação", disabled=True),
                    "data": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY"),
                    "valor": st.column_config.NumberColumn("Valor Previsto (R$)", format="R$ %.2f"),
                    "valor_pago": st.column_config.NumberColumn("Valor Pago (R$)", format="R$ %.2f"),
                },
                hide_index=True, width="stretch", key="editor_despesas"
            )
            
            if st.form_submit_button("💾 Salvar Alterações", type="primary"):
                conn = get_personal_connection()
                cursor = conn.cursor()
                excluidos, atualizados = 0, 0
                for _, row in df_editado.iterrows():
                    if row["Excluir"]:
                        cursor.execute("DELETE FROM lancamentos WHERE id = ?", (row["id"],))
                        excluidos += 1
                    else:
                        valor_prev = row["valor"]
                        valor_pg = row["valor_pago"]
                        
                        if row["foi_pago"] and valor_pg == 0:
                            valor_pg = valor_prev
                        elif not row["foi_pago"]:
                            valor_pg = 0.0
                            
                        novo_status = "Pago" if row["foi_pago"] else "Pendente"
                        
                        cursor.execute("""
                            UPDATE lancamentos 
                            SET data = ?, descricao = ?, valor = ?, valor_pago = ?, status = ?, categoria = ?, metodo_pagamento = ?, recorrente = ?, frequencia = ?, observacao = ?
                            WHERE id = ?
                        """, (str(row["data"]), row["descricao"], valor_prev, valor_pg, novo_status, row["categoria"], row["metodo_pagamento"], row["recorrente"], row["frequencia"], row["observacao"], row["id"]))
                        atualizados += 1
                conn.commit()
                conn.close()
                st.success(f"{atualizados} atualizados, {excluidos} excluídos.")
                st.rerun()


elif menu == "Receitas":   
    st.markdown(
        '<div class="dashboard-hero"><h1>💚 Receitas</h1>'
        '<p>Registre o que entra e acompanhe sua evolução com clareza.</p></div>',
        unsafe_allow_html=True
    )
    f1, f2 = st.columns(2)
    filtro_mes = f1.selectbox("Mês", ["Todos"] + list(range(1, 13)), index=datetime.date.today().month)
    filtro_ano = f2.number_input("Ano", min_value=2024, max_value=2030, value=datetime.date.today().year)
    
    conn = get_personal_connection()
    query = "SELECT id, data, descricao, valor, categoria, recorrente, frequencia, observacao FROM receitas WHERE 1=1"
    params = []
    
    if filtro_mes != "Todos":
        query += " AND strftime('%m', data) = ? AND strftime('%Y', data) = ?"
        params.extend([f"{filtro_mes:02d}", str(filtro_ano)])
        
    query += " ORDER BY data ASC"
    df = pd.read_sql_query(query, conn, params=tuple(params))
    conn.close()
    
    if df.empty:
        st.info("Nenhum registro encontrado.")
    else:
        df["data"] = pd.to_datetime(df["data"]).dt.date
        df["Excluir"] = False
        df_exibicao = df[["id", "Excluir", "data", "descricao", "categoria", "valor", "recorrente", "frequencia", "observacao"]]

        with st.form("form_edicao"):
            df_editado = st.data_editor(
                df_exibicao,
                column_config={
                    "id": st.column_config.NumberColumn("ID", disabled=True),
                    "Excluir": st.column_config.CheckboxColumn("❌ Excluir", default=False),
                    "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                    "descricao": st.column_config.TextColumn("Descrição"),
                    "categoria": st.column_config.SelectboxColumn("Categoria", options=CATEGORIAS_RECEITA),
                    "valor": st.column_config.NumberColumn("Valor (R$)", min_value=0.01, format="R$ %.2f"),
                },
                hide_index=True, width="stretch", key="editor_receitas"
            )
            
            if st.form_submit_button("💾 Salvar Alterações", type="primary"):
                conn = get_personal_connection()
                cursor = conn.cursor()
                excluidos, atualizados = 0, 0
                for _, row in df_editado.iterrows():
                    if row["Excluir"]:
                        cursor.execute("DELETE FROM receitas WHERE id = ?", (row["id"],))
                        excluidos += 1
                    else:
                        erros, descricao_ok, categoria_ok = validar_receita(row["data"], row["descricao"], row["categoria"], row["valor"])
                        if erros:
                            st.error(f"Receita ID {int(row['id'])}: {' | '.join(erros)}")
                            continue
                        cursor.execute("""
                            UPDATE receitas
                            SET data = ?, descricao = ?, categoria = ?, valor = ?, recorrente = ?, frequencia = ?, observacao = ?
                            WHERE id = ?
                        """, (str(row["data"]), descricao_ok, categoria_ok, float(row["valor"]), row["recorrente"], row["frequencia"], row["observacao"], row["id"]))
                        atualizados += 1
                conn.commit()
                conn.close()
                st.success(f"{atualizados} atualizados, {excluidos} excluídos.")
                st.rerun()


elif menu == "Orçamento":
    st.header("📊 Orçamento")
    st.info("Funcionalidade de orçamento em desenvolvimento. Aqui você poderá definir tetos de gastos por categoria.")


elif menu == "Lançamentos":
    st.header("➕ Registrar Novo Lançamento")
    
    st.subheader("🤖 Inserção Inteligente com IA")
    texto_ia = st.text_input("Descreva o gasto naturalmente:", placeholder="Ex: Comprei 60 reais de farmácia hoje no cartão")
    
    if st.button("✨ Criar com IA", type="primary") and texto_ia:
        try:
            prompt = f"""
            Analise a frase: "{texto_ia}"
            Identifique se é uma despesa ou receita. Se for uma despesa:
            Retorne um JSON com estas chaves (focado em finanças pessoais):
            - "tipo": 'Despesa' (string)
            - "descricao": O local ou motivo (string)
            - "valor": Valor em numero (float)
            - "categoria": Sugira uma categoria logica (string)
            - "metodo_pagamento": 'Pix', 'Cartão de Crédito', 'Boleto', 'Dinheiro' ou 'Transferência' (string)
            - "data" : no Formato "%Y-%m-%d" usando como referência o dia de hoje ({datetime.date.today()})) (string)
            - "status": 'Pago' ou 'Pendente' (string)
            - "recorrente" : 'Sim' ou 'Não' (string)
            - "frequencia" :  "Mensal", "Único", "Anual", "Semanal" (string)

            Se for receita:
            Retorne um JSON com estas chaves (focado em finanças pessoais):
            - "tipo": 'Receita' (string)
            - "data": no Formato "%Y-%m-%d" usando como referência o dia de hoje ({datetime.date.today()})) (string)
            - "descricao": O local ou motivo (string)
            - "categoria": Sugira uma categoria logica (string)
            - "valor": Valor em numero (float)
            - "recorrente" : 'Sim' ou 'Não' (string)
            - "frequencia" :  "Mensal", "Único", "Anual", "Semanal" (string)
            """
            
            with st.spinner("A IA está analisando..."):
                dados_ia = gerar_resposta_ia(prompt)
                
                conn = get_personal_connection()
                cursor = conn.cursor()
                if dados_ia['tipo'] == 'Despesa':
                    cursor.execute("""
                        INSERT INTO lancamentos 
                        (data, descricao, valor, observacao, recorrente, status, categoria, metodo_pagamento, frequencia, valor_pago)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        str(dados_ia['data']), dados_ia["descricao"], dados_ia["valor"], 
                        "Gerado via IA: " + texto_ia,dados_ia['recorrente'], dados_ia["status"], dados_ia["categoria"], 
                        dados_ia["metodo_pagamento"], dados_ia['frequencia'],dados_ia["valor"] if dados_ia["status"] == "Pago" else 0.0
                    ))
                    conn.commit()
                    conn.close()
                    st.success(f"Lançamento de R$ {dados_ia['valor']} inserido com sucesso!")
                    st.success(dados_ia)
                elif dados_ia['tipo'] == 'Receita':
                    cursor.execute("""
                        INSERT INTO receitas 
                        (data, descricao, valor, observacao, recorrente, frequencia, categoria)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        str(dados_ia['data']), dados_ia["descricao"], dados_ia["valor"], 
                        "Gerado via IA: " + texto_ia, dados_ia['recorrente'],
                        dados_ia['frequencia'], dados_ia['categoria']
                    ))
                    conn.commit()
                    conn.close()
                    st.success(f"Receita de R$ {dados_ia['valor']} inserido com sucesso!")
                    st.success(dados_ia)
                else:
                    st.error("Erro na IA. Tente preencher manualmente. Detalhes: {e}")
        except Exception as e:
            st.error(f"Erro na IA. Tente preencher manualmente. Detalhes: {e}")

    with st.expander("✍️ Inserir manualmente", expanded=True):
        tipo_manual = st.radio(
            "Tipo de lançamento",
            ["Despesa", "Receita"],
            horizontal=True,
            key="tipo_lancamento_manual"
        )
        if tipo_manual == "Receita":
            with st.form("form_receita_manual_lancamentos"):
                r1, r2 = st.columns(2)
                data_receita = r1.date_input(
                    "Data da receita", datetime.date.today(), format="DD/MM/YYYY"
                )
                valor_receita = r2.number_input(
                    "Valor (R$)", min_value=0.01, step=10.0, format="%.2f"
                )
                r3, r4 = st.columns(2)
                descricao_receita = r3.text_input(
                    "Descrição", placeholder="Ex.: Salário de setembro"
                )
                categoria_receita = r4.selectbox("Categoria", CATEGORIAS_RECEITA)
                r5, r6 = st.columns(2)
                frequencia_receita = r5.selectbox("Frequência", FREQUENCIAS)
                observacao_receita = r6.text_input("Observação (opcional)")
                if st.form_submit_button(
                    "Salvar receita", type="primary", use_container_width=True
                ):
                    erros, descricao_ok, categoria_ok = validar_receita(
                        data_receita,
                        descricao_receita,
                        categoria_receita,
                        valor_receita,
                    )
                    if erros:
                        for erro in erros:
                            st.warning(erro)
                    else:
                        conn = get_personal_connection()
                        cursor = conn.cursor()
                        cursor.execute(
                            """INSERT INTO receitas
                               (data, descricao, valor, observacao, recorrente, frequencia, categoria)
                               VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            (
                                str(data_receita),
                                descricao_ok,
                                float(valor_receita),
                                observacao_receita,
                                "Não" if frequencia_receita == "Único" else "Sim",
                                frequencia_receita,
                                categoria_ok,
                            ),
                        )
                        conn.commit()
                        conn.close()
                        st.success("Receita salva com sucesso. 💚")
                        st.rerun()
        else:
            with st.form("form_lancamento"):
                c1, c2 = st.columns(2)
                data = c1.date_input("Data", datetime.date.today())
                valor = c2.number_input("Valor Previsto (R$)", min_value=0.0, step=5.0)

                c3, c4, c5 = st.columns(3)
                categoria = c3.selectbox("Categoria", CATEGORIAS_DESPESA)
                metodo_pagamento = c4.selectbox("Método", METODOS_PAGAMENTO)
                status = c5.selectbox("Status", STATUS_DESPESA)

                descricao_input = st.text_input("Descrição")

                c6, c7 = st.columns(2)
                frequencia = c6.selectbox("Frequência", FREQUENCIAS)
                recorrente = "Não" if frequencia == "Único" else "Sim"
                valor_pago = c7.number_input("Valor Pago (R$)", min_value=0.0, step=5.0)
                observacao = st.text_area("Observação")

                if st.form_submit_button("Salvar despesa"):
                    erros, descricao_ok, categoria_ok = validar_lancamento_despesa(
                        data=data,
                        descricao=descricao_input,
                        categoria=categoria,
                        valor=valor,
                        valor_pago=valor_pago,
                        status=status
                    )
                    if erros:
                        for erro in erros:
                            st.warning(erro)
                    else:
                        if valor == 0 and valor_pago > 0:
                            valor = valor_pago
                        conn = get_personal_connection()
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO lancamentos
                            (data, descricao, valor, observacao, recorrente, status, categoria, metodo_pagamento, frequencia, valor_pago)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (str(data), descricao_ok, valor, observacao, recorrente, status, categoria_ok, metodo_pagamento, frequencia, valor_pago))
                        conn.commit()
                        conn.close()
                        st.success("Despesa salva com sucesso!")

# ==========================================
# GERAR RECORRENTES
# ==========================================
elif menu == "Gerar Recorrentes":
    st.header("🔮 Projetar Contas Futuras")
    qtd_meses = st.slider("Meses no futuro", min_value=1, max_value=12, value=3)
    
    if st.button("🚀 Gerar", type="primary"):
        conn = get_personal_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT descricao, valor, categoria, metodo_pagamento, frequencia, observacao FROM lancamentos WHERE recorrente = 'Sim'")
        contas = cursor.fetchall()
        if not contas:
            st.warning("Nenhuma conta recorrente encontrada.")
        else:
            novos = 0
            hoje = datetime.date.today()
            for m in range(1, qtd_meses + 1):
                data_futura = hoje + relativedelta(months=m)
                for c in contas:
                    cursor.execute(
                        "SELECT id FROM lancamentos WHERE descricao = ? AND strftime('%m', data) = ? AND strftime('%Y', data) = ?",
                        (c[0], f"{data_futura.month:02d}", str(data_futura.year))
                    )
                
                    if not cursor.fetchone():
                        cursor.execute("""
                            INSERT INTO lancamentos 
                            (data, descricao, valor, observacao, recorrente, status, categoria, metodo_pagamento, frequencia, valor_pago)
                            VALUES (?, ?, ?, ?, 'Sim', 'Pendente', ?, ?, ?, 0.0)
                        """, (
                            str(data_futura),
                            c[0],
                            c[1],
                            c[5],
                            c[2],
                            c[3],
                            c[4]
                        ))

                        novos += 1
            conn.commit()
            conn.close()
            st.success(f"{novos} lançamentos criados!")
# ==========================================
# MÓDULO: TAREFAS
# ==========================================
if menu_principal == "Tarefas":
    st.markdown(
        '<div class="dashboard-hero"><h1>✅ Minhas tarefas</h1>'
        '<p>Organize o que precisa ser feito sem deixar o dia pesado.</p></div>',
        unsafe_allow_html=True
    )
    menu_tarefas = st.sidebar.radio("Tarefas", ["A fazer", "Concluídas", "Nova Tarefa"])

    if menu_tarefas == "Nova Tarefa":
        st.subheader("🤖 Inserir Tarefa com IA")
        texto_tarefa = st.text_input("Descreva a tarefa:", placeholder="Ex: Preciso entregar o relatório amanhã")
        if st.button("Criar Tarefa", type="primary") and texto_tarefa:
            prompt = f"""
            Analise a tarefa: "{texto_tarefa}"
            Retorne um JSON:
            - "titulo": Nome da tarefa (string)
            - "data_vencimento": Data no formato "%Y-%m-%d" (referência: hoje é {datetime.date.today()})
            - "status": 'Pendente' (string)
            """
            with st.spinner("Analisando..."):
                try:
                    dados = gerar_resposta_ia(prompt)
                    conn = get_personal_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO tarefas (titulo, data_vencimento, status) VALUES (?, ?, ?)",
                        (dados["titulo"], str(dados["data_vencimento"]), dados["status"])
                    )
                    conn.commit()
                    conn.close()
                    st.success("Tarefa inserida com sucesso!")
                except Exception as e:
                    st.error(f"Erro ao inserir tarefa: {e}")

    else:
        conn = get_personal_connection()
        df_tarefas = pd.read_sql_query("SELECT * FROM tarefas", conn)
        conn.close()

        if not df_tarefas.empty:
            df_tarefas["data_vencimento"] = pd.to_datetime(
                df_tarefas["data_vencimento"], errors="coerce"
            ).dt.date
            hoje = datetime.date.today()
            concluidas = int((df_tarefas["status"] == "Concluída").sum())
            pendentes = len(df_tarefas) - concluidas
            atrasadas = int(
                (
                    (df_tarefas["status"] != "Concluída") &
                    df_tarefas["data_vencimento"].notna() &
                    (df_tarefas["data_vencimento"] < hoje)
                ).sum()
            )
            t1, t2, t3 = st.columns(3)
            t1.metric("Em aberto", pendentes)
            t2.metric("Atrasadas", atrasadas)
            t3.metric("Concluídas", concluidas)

            if menu_tarefas == "A fazer":
                df_exibir = df_tarefas[df_tarefas["status"] != "Concluída"].copy()
                df_exibir["data_ordem"] = df_exibir["data_vencimento"].apply(
                    lambda valor: valor or datetime.date.max
                )
                df_exibir = df_exibir.sort_values("data_ordem")
                titulo_lista = "Próximas tarefas"
            else:
                df_exibir = df_tarefas[df_tarefas["status"] == "Concluída"].copy()
                df_exibir = df_exibir.sort_values("data_vencimento", ascending=False)
                titulo_lista = "Tarefas concluídas"

            st.subheader(titulo_lista)
            if df_exibir.empty:
                st.success(
                    "Nenhuma tarefa nesta lista. Você está em dia por aqui. ✨"
                    if menu_tarefas == "A fazer"
                    else "Ainda não há tarefas concluídas."
                )
            else:
                for _, tarefa in df_exibir.iterrows():
                    data_tarefa = tarefa["data_vencimento"]
                    vencimento = (
                        data_tarefa.strftime("%d/%m/%Y")
                        if pd.notna(data_tarefa)
                        else "Sem prazo"
                    )
                    concluida = tarefa["status"] == "Concluída"
                    atrasada = not concluida and pd.notna(data_tarefa) and data_tarefa < hoje
                    classe = "done" if concluida else "overdue" if atrasada else ""
                    etiqueta = "Concluída" if concluida else "Atrasada" if atrasada else "Em aberto"
                    with st.form(f"form_tarefa_{int(tarefa['id'])}", clear_on_submit=False):
                        st.markdown(
                            f'<div class="task-card {classe}">'
                            f'<div class="task-title">{tarefa["titulo"]}</div>'
                            f'<div class="task-meta">{etiqueta} · prazo: {vencimento}</div>'
                            f'</div>',
                            unsafe_allow_html=True
                        )
                        marcada = st.checkbox(
                            "Marcar como concluída",
                            value=concluida,
                            key=f"concluida_tarefa_{int(tarefa['id'])}",
                        )
                        if st.form_submit_button(
                            "Salvar alteração", use_container_width=True
                        ):
                            novo_status = "Concluída" if marcada else "Pendente"
                            conn = get_personal_connection()
                            cursor = conn.cursor()
                            cursor.execute(
                                "UPDATE tarefas SET status = ? WHERE id = ?",
                                (novo_status, int(tarefa["id"])),
                            )
                            conn.commit()
                            conn.close()
                            st.success("Tarefa atualizada!")
                            st.rerun()
        else:
            st.markdown(
                '<div class="soft-card"><b>Seu espaço está livre.</b><br>'
                '<span style="color:#71827c">Crie uma tarefa para começar a organizar seu dia.</span></div>',
                unsafe_allow_html=True
            )

# ==========================================
# MÓDULO: ROTINAS
# ==========================================
elif menu_principal == "Rotinas":
    st.markdown("""
    <style>
    .rotina-card {
        padding: 1rem 1.15rem;
        border-radius: 18px;
        background: linear-gradient(135deg, #f6fbf8, #eef7f4);
        border: 1px solid #dceee7;
        margin-bottom: .7rem;
    }
    .rotina-card h4 { margin: 0; color: #315c50; }
    .rotina-card p { margin: .2rem 0 0; color: #6b8179; font-size: .9rem; }
    .rotina-destaque {
        padding: 1.2rem;
        border-radius: 22px;
        background: #f7f5fb;
        border: 1px solid #e9e3f4;
    }
    </style>
    """, unsafe_allow_html=True)

    st.header("🌿 Minhas rotinas")
    st.caption("Pequenos passos, acompanhados com leveza. Marque o que você conseguiu fazer hoje.")

    conn = get_personal_connection()
    df_rotinas = pd.read_sql_query(
        "SELECT id, nome, icone, cor FROM rotinas WHERE ativa = 1 ORDER BY id",
        conn
    )
    conn.close()

    data_selecionada = st.date_input(
        "Dia para acompanhar",
        datetime.date.today(),
        format="DD/MM/YYYY"
    )

    if df_rotinas.empty:
        st.markdown(
            '<div class="rotina-destaque"><h3>Seu espaço ainda está vazio</h3>'
            '<p>Comece com uma rotina pequena e possível. Você pode adicionar água, leitura, caminhada ou qualquer hábito importante para você.</p></div>',
            unsafe_allow_html=True
        )
    else:
        data_str = str(data_selecionada)
        conn = get_personal_connection()
        df_dia = pd.read_sql_query(
            "SELECT rotina_id, concluida FROM rotina_registros WHERE data = ?",
            conn,
            params=(data_str,)
        )
        conn.close()
        concluidas_dia = dict(zip(df_dia["rotina_id"], df_dia["concluida"])) if not df_dia.empty else {}
        total_dia = len(df_rotinas)
        feitas_dia = sum(1 for rotina_id in df_rotinas["id"] if concluidas_dia.get(rotina_id, 0))

        topo1, topo2, topo3 = st.columns(3)
        topo1.metric("Hoje", f"{feitas_dia}/{total_dia}")
        topo2.metric("Progresso do dia", f"{feitas_dia / total_dia * 100:.0f}%")
        topo3.metric("Data", data_selecionada.strftime("%d/%m"))
        st.progress(feitas_dia / total_dia)

        st.subheader("Como está o seu dia?")
        with st.form("form_rotinas_dia"):
            valores_rotinas = {}
            colunas = st.columns(2)
            for indice, (_, rotina) in enumerate(df_rotinas.iterrows()):
                coluna = colunas[indice % 2]
                with coluna:
                    valores_rotinas[rotina["id"]] = st.checkbox(
                        f'{rotina["icone"]}  {rotina["nome"]}',
                        value=bool(concluidas_dia.get(rotina["id"], 0)),
                        key=f'rotina_{rotina["id"]}_{data_str}'
                    )
            if st.form_submit_button("Salvar meu dia", type="primary", use_container_width=True):
                conn = get_personal_connection()
                cursor = conn.cursor()
                for rotina_id, concluida in valores_rotinas.items():
                    cursor.execute(
                        """INSERT INTO rotina_registros (rotina_id, data, concluida)
                           VALUES (?, ?, ?)
                           ON CONFLICT(rotina_id, data) DO UPDATE SET concluida = excluded.concluida""",
                        (int(rotina_id), data_str, int(concluida))
                    )
                conn.commit()
                conn.close()
                st.success("Dia atualizado com carinho. 🌱")
                st.rerun()

        st.divider()
        st.subheader("Seu ritmo nos últimos 30 dias")
        data_inicio = data_selecionada - datetime.timedelta(days=29)
        conn = get_personal_connection()
        df_periodo = pd.read_sql_query(
            """SELECT rotina_id, data, concluida FROM rotina_registros
               WHERE data BETWEEN ? AND ?""",
            conn,
            params=(str(data_inicio), data_str)
        )
        conn.close()

        resumo_rotinas = []
        for _, rotina in df_rotinas.iterrows():
            registros = df_periodo[df_periodo["rotina_id"] == rotina["id"]]
            feitos = int(registros["concluida"].sum())
            percentual = feitos / 30 * 100
            resumo_rotinas.append({
                "nome": rotina["nome"],
                "icone": rotina["icone"],
                "percentual": percentual,
                "feitos": feitos
            })

        colunas = st.columns(2)
        for indice, rotina in enumerate(resumo_rotinas):
            with colunas[indice % 2]:
                st.markdown(
                    f'<div class="rotina-card"><h4>{rotina["icone"]} {rotina["nome"]}</h4>'
                    f'<p>{rotina["feitos"]} de 30 dias · {rotina["percentual"]:.0f}% de constância</p></div>',
                    unsafe_allow_html=True
                )
                st.progress(min(rotina["percentual"] / 100, 1.0))

    st.divider()
    with st.expander("＋ Criar uma nova rotina"):
        with st.form("form_nova_rotina"):
            nome_rotina = st.text_input("Nome", placeholder="Ex.: Beber bastante água")
            icone_rotina = st.selectbox("Ícone", ["💧", "📚", "🏃", "🧘", "🌙", "🥗", "✨", "📝"])
            if st.form_submit_button("Adicionar rotina"):
                nome_rotina = normalizar_texto(nome_rotina)
                if not nome_rotina:
                    st.warning("Dê um nome para a sua rotina.")
                else:
                    conn = get_personal_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO rotinas (nome, icone) VALUES (?, ?)",
                        (nome_rotina, icone_rotina)
                    )
                    conn.commit()
                    conn.close()
                    st.success("Rotina adicionada. 🌿")
                    st.rerun()

# ==========================================
# MÓDULO: AGENDA
# ==========================================
elif menu_principal == "Agenda":
    st.header("📅 Agenda")
    menu_agenda = st.sidebar.radio("Agenda", ["Aulas", "Compromissos", "Eventos", "Novo Evento"])

    if st.sidebar.button("Sincronizar Google Calendar"):
        service = get_google_calendar_service()
        if service:
            with st.spinner("Sincronizando eventos..."):
                try:
                    now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
                    events_result = service.events().list(calendarId='primary', timeMin=now,
                                                        maxResults=50, singleEvents=True,
                                                        orderBy='startTime').execute()
                    events = events_result.get('items', [])

                    if not events:
                        st.sidebar.info("Nenhum evento futuro encontrado no Google Calendar.")
                    else:
                        conn = get_personal_connection()
                        cursor = conn.cursor()
                        novos_eventos = 0
                        for event in events:
                            start = event['start'].get('dateTime', event['start'].get('date'))
                            try:
                                # Convert ISO format to %Y-%m-%d %H:%M
                                dt_obj = datetime.datetime.fromisoformat(start.replace('Z', '+00:00'))
                                data_hora_str = dt_obj.strftime('%Y-%m-%d %H:%M')
                            except ValueError:
                                data_hora_str = start # Fallback

                            titulo = event.get('summary', 'Sem Título')

                            # Check if exists
                            cursor.execute("SELECT id FROM agenda WHERE titulo = ? AND data_hora = ?", (titulo, data_hora_str))
                            if not cursor.fetchone():
                                cursor.execute(
                                    "INSERT INTO agenda (tipo, titulo, data_hora) VALUES (?, ?, ?)",
                                    ("Evento", titulo, data_hora_str)
                                )
                                novos_eventos += 1

                        conn.commit()
                        conn.close()
                        if novos_eventos > 0:
                            st.sidebar.success(f"{novos_eventos} novos eventos sincronizados com sucesso!")
                            st.rerun()
                        else:
                            st.sidebar.info("Nenhum evento novo para sincronizar.")
                except Exception as e:
                    st.sidebar.error(f"Erro ao sincronizar: {e}")

    if menu_agenda == "Novo Evento":
        st.subheader("🤖 Inserir Evento com IA")
        texto_evento = st.text_input("Descreva o evento:", placeholder="Ex: Aula de matemática amanhã às 10h")
        if st.button("Criar Evento", type="primary") and texto_evento:
            prompt = f"""
            Analise a frase: "{texto_evento}"
            Retorne um JSON:
            - "tipo": 'Aula', 'Compromisso' ou 'Evento' (string)
            - "titulo": Título do evento (string)
            - "data_hora": Formato "%Y-%m-%d %H:%M" (referência: hoje é {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})
            """
            with st.spinner("Analisando..."):
                try:
                    dados = gerar_resposta_ia(prompt)
                    conn = get_personal_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO agenda (tipo, titulo, data_hora) VALUES (?, ?, ?)",
                        (dados["tipo"], dados["titulo"], str(dados["data_hora"]))
                    )
                    conn.commit()
                    conn.close()

                    # Push to Google Calendar
                    service = get_google_calendar_service()
                    if service:
                        try:
                            # Convert "%Y-%m-%d %H:%M" to ISO format
                            dt_obj = datetime.datetime.strptime(str(dados["data_hora"]), '%Y-%m-%d %H:%M')
                            start_iso = dt_obj.isoformat()
                            end_iso = (dt_obj + datetime.timedelta(hours=1)).isoformat() # Assume 1h duration

                            event_body = {
                                'summary': dados["titulo"],
                                'description': f"Gerado via IA: {texto_evento}",
                                'start': {
                                    'dateTime': start_iso,
                                    'timeZone': 'America/Sao_Paulo', # Use a valid default timezone
                                },
                                'end': {
                                    'dateTime': end_iso,
                                    'timeZone': 'America/Sao_Paulo',
                                },
                            }
                            service.events().insert(calendarId='primary', body=event_body).execute()
                            st.success("Evento inserido localmente e sincronizado no Google Calendar!")
                        except Exception as e_cal:
                            st.warning(f"Evento inserido localmente, mas falha ao enviar ao Google Calendar: {e_cal}")
                    else:
                        st.success("Evento inserido localmente com sucesso! (Google Calendar não configurado)")

                except Exception as e:
                    st.error(f"Erro ao inserir evento: {e}")

    else:
        conn = get_personal_connection()
        df_agenda = pd.read_sql_query("SELECT * FROM agenda", conn)
        conn.close()

        if not df_agenda.empty:
            df_agenda['tipo'] = df_agenda['tipo'].str.capitalize()
            # Handle pluralization matching (Aulas -> Aula)
            tipo_map = {"Aulas": "Aula", "Compromissos": "Compromisso", "Eventos": "Evento"}
            tipo_busca = tipo_map.get(menu_agenda, menu_agenda)

            df_exibir = df_agenda[df_agenda['tipo'] == tipo_busca]
            st.dataframe(df_exibir, use_container_width=True)
        else:
            st.info("Nenhum evento encontrado.")

# ==========================================
# MÓDULO: ESTUDOS
# ==========================================
elif menu_principal == "Estudos":
    st.header("🎓 Estudos")
    menu_estudos = st.sidebar.radio("Estudos", ["Disciplinas", "Trabalhos", "Provas", "Horas estudadas", "Novo Registro"])

    if menu_estudos == "Novo Registro":
        st.subheader("🤖 Inserir Registro de Estudo com IA")
        texto_estudo = st.text_input("Descreva a atividade:", placeholder="Ex: Estudei 2 horas de Física hoje")
        if st.button("Salvar Registro", type="primary") and texto_estudo:
            prompt = f"""
            Analise a frase: "{texto_estudo}"
            Retorne um JSON:
            - "tipo": 'Disciplina', 'Trabalho', 'Prova' ou 'Horas' (string)
            - "titulo": Assunto ou título (string)
            - "horas": Quantidade de horas se aplicável, senão 0 (float)
            - "data": Formato "%Y-%m-%d" (referência: hoje é {datetime.date.today()})
            """
            with st.spinner("Analisando..."):
                try:
                    dados = gerar_resposta_ia(prompt)
                    conn = get_personal_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO estudos (tipo, titulo, horas, data) VALUES (?, ?, ?, ?)",
                        (dados["tipo"], dados["titulo"], dados["horas"], str(dados["data"]))
                    )
                    conn.commit()
                    conn.close()
                    st.success("Registro salvo com sucesso!")
                except Exception as e:
                    st.error(f"Erro ao salvar registro: {e}")

    else:
        conn = get_personal_connection()
        df_estudos = pd.read_sql_query("SELECT * FROM estudos", conn)
        conn.close()

        if not df_estudos.empty:
            df_estudos['tipo'] = df_estudos['tipo'].str.capitalize()
            tipo_map = {"Disciplinas": "Disciplina", "Trabalhos": "Trabalho", "Provas": "Prova", "Horas estudadas": "Horas"}
            tipo_busca = tipo_map.get(menu_estudos, menu_estudos)

            df_exibir = df_estudos[df_estudos['tipo'] == tipo_busca]
            st.dataframe(df_exibir, use_container_width=True)
        else:
            st.info("Nenhum registro encontrado.")

# ==========================================
# MÓDULO: PROJETOS
# ==========================================
elif menu_principal == "Projetos":
    st.header("💼 Projetos")
    menu_projetos = st.sidebar.radio("Projetos", ["Projetos pessoais", "Faculdade", "Lançar Projeto"])

    if menu_projetos == "Novo Projeto":
        st.subheader("🤖 Inserir Projeto com IA")
        texto_projeto = st.text_input("Descreva o projeto:", placeholder="Ex: Iniciei um projeto de automação no PET")
        if st.button("Salvar Projeto", type="primary") and texto_projeto:
            prompt = f"""
            Analise a frase: "{texto_projeto}"
            Retorne um JSON:
            - "categoria": 'Projetos pessoais', 'PET', 'IC' ou 'Programação' (string)
            - "nome": Nome ou descrição curta do projeto (string)
            - "status": 'Em andamento', 'Planejado' ou 'Concluído' (string)
            """
            with st.spinner("Analisando..."):
                try:
                    dados = gerar_resposta_ia(prompt)
                    conn = get_personal_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO projetos (categoria, nome, status) VALUES (?, ?, ?)",
                        (dados["categoria"], dados["nome"], dados["status"])
                    )
                    conn.commit()
                    conn.close()
                    st.success("Projeto salvo com sucesso!")
                except Exception as e:
                    st.error(f"Erro ao salvar projeto: {e}")

    else:
        conn = get_personal_connection()
        df_projetos = pd.read_sql_query("SELECT * FROM projetos", conn)
        conn.close()

        if not df_projetos.empty:
            df_exibir = df_projetos[df_projetos['categoria'].str.contains(menu_projetos, case=False, na=False)]
            st.dataframe(df_exibir, use_container_width=True)
        else:
            st.info("Nenhum projeto encontrado.")

# ==========================================
# MÓDULO: VISÃO GERAL / DASHBOARD
# ==========================================
elif menu_principal == "Dashboard":
    hoje = datetime.date.today()
    nome_dia = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"][hoje.weekday()]
    st.markdown(
        f'<div class="dashboard-hero"><h1>Olá, {nome_usuario.split()[0]} 🌿</h1>'
        f'<p>Uma visão tranquila do que importa hoje, {nome_dia}, {hoje.strftime("%d/%m")}.</p></div>',
        unsafe_allow_html=True
    )

    conn = get_personal_connection()
    try:
        df_lancamentos = pd.read_sql_query("SELECT * FROM lancamentos", conn)
        df_receitas = pd.read_sql_query("SELECT * FROM receitas", conn)
        df_tarefas = pd.read_sql_query("SELECT * FROM tarefas", conn)
        df_rotinas = pd.read_sql_query("SELECT id, nome, icone FROM rotinas WHERE ativa = 1", conn)
        df_registros = pd.read_sql_query(
            "SELECT rotina_id, concluida FROM rotina_registros WHERE data = ?",
            conn,
            params=(str(hoje),)
        )
    finally:
        conn.close()

    inicio_mes = hoje.replace(day=1)
    if df_lancamentos.empty:
        despesas = 0.0
        df_mes_despesas = pd.DataFrame()
    else:
        df_lancamentos["dt_data"] = pd.to_datetime(df_lancamentos["data"])
        df_mes_despesas = df_lancamentos[
            (df_lancamentos["dt_data"].dt.date >= inicio_mes) &
            (df_lancamentos["dt_data"].dt.date <= hoje)
        ]
        despesas = float(df_mes_despesas["valor"].sum())

    if df_receitas.empty:
        receitas = 0.0
        df_mes_receitas = pd.DataFrame()
    else:
        df_receitas["dt_data"] = pd.to_datetime(df_receitas["data"])
        df_mes_receitas = df_receitas[
            (df_receitas["dt_data"].dt.date >= inicio_mes) &
            (df_receitas["dt_data"].dt.date <= hoje)
        ]
        receitas = float(df_mes_receitas["valor"].sum())

    saldo = receitas - despesas
    tarefas_pendentes = int((df_tarefas["status"] != "Concluída").sum()) if not df_tarefas.empty else 0
    rotinas_feitas = int(df_registros["concluida"].sum()) if not df_registros.empty else 0
    total_rotinas = len(df_rotinas)
    percentual_rotinas = rotinas_feitas / total_rotinas if total_rotinas else 0

    st.markdown('<div class="section-label">Resumo de hoje</div>', unsafe_allow_html=True)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Saldo do mês", f"R$ {saldo:,.2f}")
    k2.metric("Receitas", f"R$ {receitas:,.2f}")
    k3.metric("Despesas", f"R$ {despesas:,.2f}")
    k4.metric("Rotinas hoje", f"{rotinas_feitas}/{total_rotinas}")

    esquerda, direita = st.columns([1.35, 1], gap="large")
    with esquerda:
        st.markdown('<div class="section-label">Fluxo financeiro</div>', unsafe_allow_html=True)
        if receitas or despesas:
            df_fluxo = pd.DataFrame({
                "Tipo": ["Receitas", "Despesas"],
                "Valor": [receitas, despesas]
            })
            fig_fluxo = px.bar(
                df_fluxo, x="Tipo", y="Valor", color="Tipo",
                color_discrete_map={"Receitas": "#8fc8ae", "Despesas": "#c8b9df"},
                text_auto=".2s"
            )
            fig_fluxo.update_layout(
                showlegend=False, height=290, margin=dict(l=0, r=0, t=15, b=0),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                yaxis_title="", xaxis_title=""
            )
            st.plotly_chart(fig_fluxo, use_container_width=True, config={"displayModeBar": False})
        else:
            st.markdown('<div class="soft-card">Ainda não há movimentações neste mês.</div>', unsafe_allow_html=True)

    with direita:
        st.markdown('<div class="section-label">Rotinas de hoje</div>', unsafe_allow_html=True)
        if total_rotinas:
            st.progress(percentual_rotinas)
            st.caption(f"{percentual_rotinas:.0%} concluído hoje")
            for _, rotina in df_rotinas.iterrows():
                concluida = bool(
                    not df_registros.empty and
                    df_registros.loc[df_registros["rotina_id"] == rotina["id"], "concluida"].sum()
                )
                simbolo = "✓" if concluida else "○"
                st.markdown(
                    f'<div class="soft-card" style="padding:.65rem 1rem;margin:.45rem 0">'
                    f'<b>{simbolo} {rotina["icone"]} {rotina["nome"]}</b></div>',
                    unsafe_allow_html=True
                )
        else:
            st.markdown('<div class="soft-card">Crie sua primeira rotina para acompanhar seu ritmo.</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-label">Acompanhe seu dia</div>', unsafe_allow_html=True)
    tarefas_col, resumo_col = st.columns([1.35, 1], gap="large")
    with tarefas_col:
        st.subheader("Próximas tarefas")
        if not df_tarefas.empty:
            proximas = df_tarefas[df_tarefas["status"] != "Concluída"].copy()
            proximas["data_vencimento"] = pd.to_datetime(proximas["data_vencimento"], errors="coerce").dt.date
            proximas = proximas.sort_values("data_vencimento").head(5)
            if proximas.empty:
                st.success("Tudo em dia por aqui. ✨")
            else:
                st.dataframe(
                    proximas[["titulo", "data_vencimento", "status"]],
                    hide_index=True, use_container_width=True
                )
        else:
            st.info("Você ainda não tem tarefas cadastradas.")
    with resumo_col:
        st.subheader("Visão rápida")
        st.metric("Tarefas pendentes", tarefas_pendentes)
        if total_rotinas:
            st.metric("Constância hoje", f"{percentual_rotinas:.0%}")
        if st.button("✨ Gerar resumo com IA", use_container_width=True):
            with st.spinner("Preparando seu resumo..."):
                resumo_dados = (
                    f"Saldo do mês: R$ {saldo:.2f}. Receitas: R$ {receitas:.2f}. "
                    f"Despesas: R$ {despesas:.2f}. Tarefas pendentes: {tarefas_pendentes}. "
                    f"Rotinas concluídas hoje: {rotinas_feitas} de {total_rotinas}."
                )
                prompt_resumo = f"""
                Você é um assistente pessoal. Resuma estes dados em Markdown, com tom calmo,
                encorajador e objetivo. Sugira no máximo uma prioridade prática.
                DADOS: {resumo_dados}
                """
                try:
                    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                    modelo = genai.GenerativeModel("gemini-3.6-flash")
                    resposta = modelo.generate_content(prompt_resumo)
                    st.info(resposta.text)
                except Exception as e:
                    st.error(f"Erro ao gerar resumo: {e}")
