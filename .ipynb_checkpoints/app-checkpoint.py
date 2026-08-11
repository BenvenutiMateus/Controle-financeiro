import streamlit as st
import sqlite3
import pandas as pd
import datetime

# ==========================================
# 1. CONFIGURAÇÃO E BANCO DE DADOS (SQLite)
# ==========================================
st.set_page_config(page_title="Controle Financeiro Customizado", layout="wide", page_icon="💰")

def get_connection():
    return sqlite3.connect("financeiro.db", check_same_thread=False)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Tabela de Usuários
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            nome TEXT NOT NULL,
            senha TEXT NOT NULL
        )
    """)
    
    # Tabela de Lançamentos adaptada com as suas colunas exatas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lancamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            data DATE NOT NULL,
            descricao TEXT NOT NULL,
            valor REAL NOT NULL,
            observacao TEXT,
            recorrente TEXT NOT NULL, -- 'Sim' ou 'Não'
            status TEXT NOT NULL,     -- 'Pago', 'Pendente', etc.
            categoria TEXT NOT NULL,
            metodo_pagamento TEXT NOT NULL,
            frequencia TEXT,          -- 'Mensal', 'Anual', 'Única', etc.
            valor_pago REAL,
            FOREIGN KEY (user_id) REFERENCES usuarios (id)
        )
    """)
    
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 2. SISTEMA DE LOGIN
# ==========================================
if "user" not in st.session_state:
    st.session_state["user"] = None

def cadastrar_usuario(username, nome, senha):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO usuarios (username, nome, senha) VALUES (?, ?, ?)", (username, nome, senha))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def autenticar_usuario(username, senha):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, nome FROM usuarios WHERE username = ? AND senha = ?", (username, senha))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "username": row[1], "nome": row[2]}
    return None

if st.session_state["user"] is None:
    st.title("🔐 Acesso ao Controle Financeiro")
    aba_login, aba_cadastro = st.tabs(["Login", "Criar Conta"])
    
    with aba_login:
        with st.form("form_login"):
            usuario = st.text_input("Usuário / E-mail")
            senha = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar"):
                user = autenticar_usuario(usuario, senha)
                if user:
                    st.session_state["user"] = user
                    st.rerun()
                else:
                    st.error("Usuário ou senha incorretos.")
                    
    with aba_cadastro:
        with st.form("form_cadastro"):
            novo_usuario = st.text_input("Usuário / E-mail")
            novo_nome = st.text_input("Seu Nome")
            nova_senha = st.text_input("Senha", type="password")
            if st.form_submit_button("Criar Conta"):
                if cadastrar_usuario(novo_usuario, novo_nome, nova_senha):
                    st.success("Conta criada! Faça login.")
                else:
                    st.error("Nome de usuário já em uso.")
    st.stop()

# ==========================================
# 3. PAINEL PRINCIPAL
# ==========================================
user_id = st.session_state["user"]["id"]
nome_usuario = st.session_state["user"]["nome"]

st.sidebar.title(f"👤 {nome_usuario}")
if st.sidebar.button("Sair"):
    st.session_state["user"] = None
    st.rerun()

st.sidebar.divider()
menu = st.sidebar.radio("Navegação", ["Dashboard", "Novo Lançamento", "Recorrentes"])

# ==========================================
# NOVO LANÇAMENTO
# ==========================================
if menu == "Novo Lançamento":
    st.header("➕ Registrar Novo Lançamento")
    
    with st.form("form_lancamento"):
        col1, col2, col3 = st.columns(3)
        data = col1.date_input("Data", datetime.date.today())
        descricao = col2.text_input("Descrição")
        valor = col3.number_input("Valor Previsto (R$)", min_value=0.0, step=5.0)
        
        col4, col5, col6 = st.columns(3)
        categoria = col4.text_input("Categoria")
        metodo_pagamento = col5.selectbox("Método de Pagamento", ["Pix", "Cartão de Crédito", "Boleto", "Dinheiro", "Transferência"])
        status = col6.selectbox("Status", ["Pago", "Pendente", "Agendado", "Cancelado"])
        
        col7, col8, col9 = st.columns(3)
        recorrente = col7.selectbox("É Recorrente?", ["Não", "Sim"])
        frequencia = col8.selectbox("Frequência", ["Única", "Mensal", "Anual", "Semanal"])
        valor_pago = col9.number_input("Valor Pago (R$)", min_value=0.0, step=5.0)
        
        observacao = st.text_area("Observação")
        
        if st.form_submit_button("Salvar Lançamento"):
            if descricao and categoria:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO lancamentos 
                    (user_id, data, descricao, valor, observacao, recorrente, status, categoria, metodo_pagamento, frequencia, valor_pago)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (user_id, data, descricao, valor, observacao, recorrente, status, categoria, metodo_pagamento, frequencia, valor_pago))
                conn.commit()
                conn.close()
                st.success("Lançamento salvo com sucesso!")
            else:
                st.warning("Preencha ao menos Descrição e Categoria.")

# ==========================================
# RECORRENTES
# ==========================================
elif menu == "Recorrentes":
    st.header("🔄 Lançamentos Recorrentes")
    
    conn = get_connection()
    df_rec = pd.read_sql_query("""
        SELECT id, data, descricao, valor, categoria, metodo_pagamento, frequencia 
        FROM lancamentos 
        WHERE user_id = ? AND recorrente = 'Sim'
    """, conn, params=(user_id,))
    conn.close()
    
    st.subheader("Seus Registros Configurados como Recorrentes")
    st.dataframe(df_rec, use_container_width=True)

# ==========================================
# DASHBOARD
# ==========================================
elif menu == "Dashboard":
    st.header("📊 Painel de Controle Financeiro")
    
    col_m, col_a = st.columns(2)
    mes_sel = col_m.selectbox("Mês", range(1, 13), index=datetime.datetime.now().month - 1)
    ano_sel = col_a.number_input("Ano", min_value=2024, max_value=2030, value=datetime.datetime.now().year)
    
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT id, data, descricao, valor, observacao, recorrente, status, categoria, metodo_pagamento, frequencia, valor_pago
        FROM lancamentos 
        WHERE user_id = ? AND strftime('%m', data) = ? AND strftime('%Y', data) = ?
    """, conn, params=(user_id, f"{mes_sel:02d}", str(ano_sel)))
    conn.close()
    
    if df.empty:
        st.info("Nenhum registro encontrado para este mês.")
    else:
        # Métricas em destaque
        total_previsto = df["valor"].sum()
        total_pago = df["valor_pago"].sum()
        
        m1, m2 = st.columns(2)
        m1.metric("Total Previsto", f"R$ {total_previsto:,.2f}")
        m2.metric("Total Pago", f"R$ {total_pago:,.2f}")
        
        st.divider()
        
        # Agrupamentos
        col_c, col_m = st.columns(2)
        with col_c:
            st.subheader("Gastos por Categoria")
            st.dataframe(df.groupby("categoria")[["valor", "valor_pago"]].sum(), use_container_width=True)
            
        with col_m:
            st.subheader("Por Método de Pagamento")
            st.dataframe(df.groupby("metodo_pagamento")[["valor_pago"]].sum(), use_container_width=True)
            
        st.divider()
        st.subheader("Tabela Completa de Lançamentos")
        st.dataframe(df, use_container_width=True)