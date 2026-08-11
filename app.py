import streamlit as st
import sqlite3
import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta
import plotly.express as px

# ==========================================
# 1. CONFIGURAÇÃO E BANCO DE DADOS
# ==========================================
st.set_page_config(page_title="Controle Financeiro Inteligente", layout="wide", page_icon="📊")

def get_connection():
    if "TURSO_URL" in st.secrets and "TURSO_AUTH_TOKEN" in st.secrets:
        try:
            import libsql_experimental as libsql
            return libsql.connect(
                database=st.secrets["TURSO_URL"],
                auth_token=st.secrets["TURSO_AUTH_TOKEN"]
            )
        except Exception as e:
            st.warning(f"Erro ao conectar ao Turso: {e}")
            
    return sqlite3.connect("financeiro.db", check_same_thread=False)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            nome TEXT NOT NULL,
            senha TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lancamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            data DATE NOT NULL,
            descricao TEXT NOT NULL,
            valor REAL NOT NULL,
            observacao TEXT,
            recorrente TEXT NOT NULL,
            status TEXT NOT NULL,
            categoria TEXT NOT NULL,
            metodo_pagamento TEXT NOT NULL,
            frequencia TEXT,
            valor_pago REAL,
            FOREIGN KEY (user_id) REFERENCES usuarios (id)
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 2. AUTO-CATEGORIZAÇÃO INTELIGENTE
# ==========================================
MAPEAMENTO_CATEGORIAS = {
    "Alimentação": ["mercado", "supermercado", "ifood", "restaurante", "padaria", "mcdonalds", "burger", "feira"],
    "Transporte": ["uber", "99", "combustivel", "gasolina", "estacionamento", "pedagio", "ipva", "mecanico"],
    "Moradia & Infra": ["aluguel", "condominio", "luz", "energia", "agua", "internet", "iptu"],
    "Serviços & Software": ["aws", "cloud", "github", "chatgpt", "openai", "google", "contabilidade", "servidor"],
    "Lazer & Assinaturas": ["netflix", "spotify", "steam", "cinema", "prime"],
    "Saúde & Bem-estar": ["farmacia", "drogaria", "academia", "consulta", "exame"]
}

MAPEAMENTO_METODOS = {
    "Cartão de Crédito": ["uber", "ifood", "netflix", "spotify", "aws", "steam", "chatgpt"],
    "Pix": ["aluguel", "condominio", "mercado", "pix"],
    "Boleto": ["luz", "agua", "internet", "iptu", "ipva", "contabilidade"]
}

def sugerir_categoria_e_metodo(descricao):
    desc_lower = descricao.lower().strip()
    categoria_sugerida = ""
    metodo_sugerido = "Pix"
    
    for cat, palavras in MAPEAMENTO_CATEGORIAS.items():
        if any(p in desc_lower for p in palavras):
            categoria_sugerida = cat
            break
            
    for met, palavras in MAPEAMENTO_METODOS.items():
        if any(p in desc_lower for p in palavras):
            metodo_sugerido = met
            break
            
    return categoria_sugerida, metodo_sugerido

# ==========================================
# 3. AUTENTICAÇÃO
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
    except Exception as e:
        if "UNIQUE constraint failed" in str(e) or "SQLITE_CONSTRAINT" in str(e):
            return False
        raise e
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
            # O atributo autocomplete ativa o preenchimento automático/salvamento do navegador
            usuario = st.text_input("Usuário / E-mail", autocomplete="username")
            senha = st.text_input("Senha", type="password", autocomplete="current-password")
            if st.form_submit_button("Entrar"):
                user = autenticar_usuario(usuario, senha)
                if user:
                    st.session_state["user"] = user
                    st.rerun()
                else:
                    st.error("Usuário ou senha incorretos.")
                    
    with aba_cadastro:
        with st.form("form_cadastro"):
            novo_usuario = st.text_input("Usuário / E-mail", autocomplete="new-username")
            novo_nome = st.text_input("Seu Nome")
            nova_senha = st.text_input("Senha", type="password", autocomplete="new-password")
            if st.form_submit_button("Criar Conta"):
                if cadastrar_usuario(novo_usuario, novo_nome, nova_senha):
                    st.success("Conta criada! Faça login.")
                else:
                    st.error("Nome de usuário já em uso.")
    st.stop()

# ==========================================
# 4. PAINEL PRINCIPAL
# ==========================================
user_id = st.session_state["user"]["id"]
nome_usuario = st.session_state["user"]["nome"]

st.sidebar.title(f"👤 {nome_usuario}")
if st.sidebar.button("Sair"):
    st.session_state["user"] = None
    st.rerun()

st.sidebar.divider()
menu = st.sidebar.radio("Navegação", ["Dashboard Analytics", "Todas as Contas (Editável)", "Novo Lançamento", "Gerar Recorrentes Futuras"])

# ==========================================
# DASHBOARD ANALYTICS
# ==========================================
if menu == "Dashboard Analytics":
    st.header("📈 Dashboard Analytics & Tendências")
    
    col_f1, col_f2 = st.columns(2)
    filtro_mes = col_f1.selectbox("Selecione o Mês", list(range(1, 13)), index=datetime.date.today().month - 1)
    filtro_ano = col_f2.number_input("Ano", min_value=2024, max_value=2030, value=datetime.date.today().year)
    
    conn = get_connection()
    df_mes = pd.read_sql_query("""
        SELECT * FROM lancamentos 
        WHERE user_id = ? AND strftime('%m', data) = ? AND strftime('%Y', data) = ?
    """, conn, params=(user_id, f"{filtro_mes:02d}", str(filtro_ano)))
    
    df_ano = pd.read_sql_query("""
        SELECT data, valor, valor_pago, status, categoria FROM lancamentos 
        WHERE user_id = ? AND strftime('%Y', data) = ?
    """, conn, params=(user_id, str(filtro_ano)))
    conn.close()
    
    if df_mes.empty:
        st.info("Nenhum lançamento encontrado para este mês.")
    else:
        hoje = datetime.date.today()
        df_mes["dt_data"] = pd.to_datetime(df_mes["data"]).dt.date
        
        def classificar_alerta(row):
            if row["status"] == "Pago":
                return "🟢 Pago"
            elif row["dt_data"] < hoje:
                return "🔴 Atrasado"
            else:
                return "🟡 A Pagar (No Prazo)"

        df_mes["Alerta"] = df_mes.apply(classificar_alerta, axis=1)
        
        tot_previsto = df_mes["valor"].sum()
        tot_pago = df_mes["valor_pago"].sum()
        tot_atrasado = df_mes[df_mes["Alerta"] == "🔴 Atrasado"]["valor"].sum()
        tot_a_vencer = df_mes[df_mes["Alerta"] == "🟡 A Pagar (No Prazo)"]["valor"].sum()
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Previsto", f"R$ {tot_previsto:,.2f}")
        m2.metric("Total Pago (🟢)", f"R$ {tot_pago:,.2f}")
        m3.metric("A Pagar no Prazo (🟡)", f"R$ {tot_a_vencer:,.2f}")
        m4.metric("Em Atraso (🔴)", f"R$ {tot_atrasado:,.2f}", delta_color="inverse")
        
        st.divider()
        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            st.subheader("📊 Situação das Contas do Mês")
            df_status = df_mes.groupby("Alerta")["valor"].sum().reset_index()
            fig_status = px.pie(
                df_status, values="valor", names="Alerta", hole=0.4,
                color="Alerta",
                color_discrete_map={
                    "🟢 Pago": "#2ecc71",
                    "🔴 Atrasado": "#e74c3c",
                    "🟡 A Pagar (No Prazo)": "#f1c40f"
                }
            )
            st.plotly_chart(fig_status, width="stretch")
            
        with col_g2:
            st.subheader("🍕 Gastos por Categoria")
            df_cat = df_mes.groupby("categoria")["valor"].sum().reset_index()
            fig_pizza = px.pie(df_cat, values="valor", names="categoria", hole=0.4, color_discrete_sequence=px.colors.qualitative.Set3)
            st.plotly_chart(fig_pizza, width="stretch")

        st.divider()
        col_g3, col_g4 = st.columns(2)
        
        with col_g3:
            st.subheader("📈 Evolução de Gastos ao Longo do Ano")
            if not df_ano.empty:
                df_ano["Mes_Num"] = pd.to_datetime(df_ano["data"]).dt.month
                df_evolucao = df_ano.groupby("Mes_Num")[["valor", "valor_pago"]].sum().reset_index()
                df_evolucao["Mês"] = df_evolucao["Mes_Num"].apply(lambda x: datetime.date(2000, x, 1).strftime('%b'))
                
                fig_linha = px.line(
                    df_evolucao, x="Mês", y=["valor", "valor_pago"],
                    labels={"value": "R$", "variable": "Tipo"},
                    markers=True,
                    color_discrete_map={"valor": "#e74c3c", "valor_pago": "#2ecc71"}
                )
                st.plotly_chart(fig_linha, width="stretch")
                
        with col_g4:
            st.subheader("💳 Formas de Pagamento Utilizadas")
            df_met = df_mes.groupby("metodo_pagamento")["valor"].sum().reset_index()
            fig_barras = px.bar(df_met, x="metodo_pagamento", y="valor", text_auto=".2f", color="metodo_pagamento")
            st.plotly_chart(fig_barras, width="stretch")

# ==========================================
# NOVO LANÇAMENTO
# ==========================================
elif menu == "Novo Lançamento":
    st.header("➕ Registrar Novo Lançamento")
    
    descricao_input = st.text_input("Descrição (digite ex: 'Uber', 'iFood', 'Mercado')")
    cat_sugerida, met_sugerido = sugerir_categoria_e_metodo(descricao_input)
    
    with st.form("form_lancamento"):
        col1, col2 = st.columns(2)
        data = col1.date_input("Data", datetime.date.today())
        valor = col2.number_input("Valor Previsto (R$)", min_value=0.0, step=5.0)
        
        col3, col4, col5 = st.columns(3)
        categoria = col3.text_input("Categoria", value=cat_sugerida)
        metodo_pagamento = col4.selectbox("Método de Pagamento", ["Pix", "Cartão de Crédito", "Boleto", "Dinheiro", "Transferência"], index=["Pix", "Cartão de Crédito", "Boleto", "Dinheiro", "Transferência"].index(met_sugerido))
        status = col5.selectbox("Status", ["Pendente", "Pago", "Agendado", "Cancelado"])
        
        col6, col7 = st.columns(2)
        frequencia = col6.selectbox("Frequência", ["Mensal", "Único", "Anual", "Semanal"])
        recorrente = "Não" if frequencia == "Único" else "Sim"
        valor_pago = col7.number_input("Valor Pago (R$)", min_value=0.0, step=5.0)
        
        observacao = st.text_area("Observação")
        
        if st.form_submit_button("Salvar Lançamento"):
            if descricao_input and categoria:
                # REGRA INTELIGENTE: Se previu 0 mas pagou algo, iguala os valores
                if valor == 0 and valor_pago > 0:
                    valor = valor_pago
                    
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO lancamentos 
                    (user_id, data, descricao, valor, observacao, recorrente, status, categoria, metodo_pagamento, frequencia, valor_pago)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (user_id, str(data), descricao_input, valor, observacao, recorrente, status, categoria, metodo_pagamento, frequencia, valor_pago))
                conn.commit()
                conn.close()
                st.success("Lançamento salvo com sucesso!")
            else:
                st.warning("Preencha ao menos Descrição e Categoria.")


# ==========================================
# TODAS AS CONTAS (EDITÁVEL COM CORES E EXCLUSÃO)
# ==========================================
elif menu == "Todas as Contas (Editável)":
    st.header("📋 Gestão Completa de Contas")
    
    col_f1, col_f2 = st.columns(2)
    filtro_mes = col_f1.selectbox("Filtrar por Mês", ["Todos"] + list(range(1, 13)), index=datetime.date.today().month)
    filtro_ano = col_f2.number_input("Filtrar por Ano", min_value=2024, max_value=2030, value=datetime.date.today().year)
    
    conn = get_connection()
    query = "SELECT id, data, descricao, valor, valor_pago, status, categoria, metodo_pagamento, recorrente, frequencia, observacao FROM lancamentos WHERE user_id = ?"
    params = [user_id]
    
    if filtro_mes != "Todos":
        query += " AND strftime('%m', data) = ? AND strftime('%Y', data) = ?"
        params.extend([f"{filtro_mes:02d}", str(filtro_ano)])
        
    query += " ORDER BY data ASC"
    
    df = pd.read_sql_query(query, conn, params=tuple(params))
    conn.close()
    
    if df.empty:
        st.info("Nenhum registro encontrado para este filtro.")
    else:
        hoje = datetime.date.today()
        
        df["data"] = pd.to_datetime(df["data"]).dt.date
        
        # Cria a coluna de exclusão, padrão é False (Desmarcada)
        df["Excluir"] = False
        
        def definir_situacao(row):
            if row["status"] == "Pago":
                return "🟢 Pago"
            elif row["data"] < hoje:
                return "🔴 Atrasado"
            else:
                return "🟡 A Pagar (No Prazo)"

        df["Situação"] = df.apply(definir_situacao, axis=1)
        
        # Reorganiza as colunas incluindo a caixinha "Excluir"
        df_exibicao = df[["id", "Excluir", "Situação", "data", "descricao", "valor", "valor_pago", "status", "categoria", "metodo_pagamento", "recorrente", "frequencia", "observacao"]]
        
        def colorir_tabela(val):
            if val == "🟢 Pago":
                return 'background-color: #d4edda; color: #155724; font-weight: bold'
            elif val == "🔴 Atrasado":
                return 'background-color: #f8d7da; color: #721c24; font-weight: bold'
            elif val == "🟡 A Pagar (No Prazo)":
                return 'background-color: #fff3cd; color: #856404; font-weight: bold'
            return ''
        
        df_colorido = df_exibicao.style.map(colorir_tabela, subset=["Situação"])
        
        df_editado = st.data_editor(
            df_colorido,
            column_config={
                "id": st.column_config.NumberColumn("ID", disabled=True),
                "Excluir": st.column_config.CheckboxColumn("❌ Excluir", default=False),
                "Situação": st.column_config.TextColumn("Situação", disabled=True),
                "data": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY"),
                "status": st.column_config.SelectboxColumn("Status", options=["Pendente", "Pago", "Agendado", "Cancelado"]),
                "recorrente": st.column_config.SelectboxColumn("Recorrente?", options=["Sim", "Não"]),
                "metodo_pagamento": st.column_config.SelectboxColumn("Método", options=["Pix", "Cartão de Crédito", "Boleto", "Dinheiro", "Transferência"]),
                "valor": st.column_config.NumberColumn("Valor Previsto (R$)", format="R$ %.2f"),
                "valor_pago": st.column_config.NumberColumn("Valor Pago (R$)", format="R$ %.2f"),
            },
            hide_index=True,
            width="stretch",
            key="editor_contas"
        )
        
        if st.button("💾 Salvar Alterações", type="primary"):
            conn = get_connection()
            cursor = conn.cursor()
            
            excluidos = 0
            atualizados = 0
            
            for _, row in df_editado.iterrows():
                if row["Excluir"]:
                    cursor.execute("DELETE FROM lancamentos WHERE id = ? AND user_id = ?", (row["id"], user_id))
                    excluidos += 1
                else:
                    # Lemos os valores da linha
                    valor_prev = row["valor"]
                    valor_pg = row["valor_pago"]
                    
                    # REGRA INTELIGENTE: Se previu 0 (ou vazio) mas pagou algo, iguala os valores
                    if (pd.isna(valor_prev) or valor_prev == 0) and valor_pg > 0:
                        valor_prev = valor_pg
                        
                    cursor.execute("""
                        UPDATE lancamentos 
                        SET data = ?, descricao = ?, valor = ?, valor_pago = ?, status = ?, categoria = ?, metodo_pagamento = ?, recorrente = ?, frequencia = ?, observacao = ?
                        WHERE id = ? AND user_id = ?
                    """, (
                        str(row["data"]), row["descricao"], valor_prev, valor_pg, 
                        row["status"], row["categoria"], row["metodo_pagamento"], 
                        row["recorrente"], row["frequencia"], row["observacao"], 
                        row["id"], user_id
                    ))
                    atualizados += 1
                    
            conn.commit()
            conn.close()
            st.success(f"Pronto! {atualizados} contas atualizadas e {excluidos} contas excluídas.")
            st.rerun()
# ==========================================
# GERAR RECORRENTES FUTURAS
# ==========================================
elif menu == "Gerar Recorrentes Futuras":
    st.header("🔮 Projetar Contas Futuras")
    qtd_meses = st.slider("Meses no futuro", min_value=1, max_value=12, value=3)
    
    if st.button("🚀 Gerar Contas Futuras", type="primary"):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT descricao, valor, categoria, metodo_pagamento, frequencia, observacao FROM lancamentos WHERE user_id = ? AND recorrente = 'Sim'", (user_id,))
        contas = cursor.fetchall()
        
        if not contas:
            st.warning("Nenhuma conta 'Recorrente = Sim' encontrada.")
        else:
            novos = 0
            hoje = datetime.date.today()
            for m in range(1, qtd_meses + 1):
                data_futura = hoje + relativedelta(months=m)
                for c in contas:
                    cursor.execute("SELECT id FROM lancamentos WHERE user_id = ? AND descricao = ? AND strftime('%m', data) = ? AND strftime('%Y', data) = ?", (user_id, c[0], f"{data_futura.month:02d}", str(data_futura.year)))
                    if not cursor.fetchone():
                        cursor.execute("""
                            INSERT INTO lancamentos 
                            (user_id, data, descricao, valor, observacao, recorrente, status, categoria, metodo_pagamento, frequencia, valor_pago)
                            VALUES (?, ?, ?, ?, ?, 'Sim', 'Pendente', ?, ?, ?, 0.0)
                        """, (user_id, str(data_futura), c[0], c[1], c[5], c[2], c[3], c[4]))
                        novos += 1
            conn.commit()
            conn.close()
            st.success(f"Gerados {novos} lançamentos para os próximos {qtd_meses} meses!")