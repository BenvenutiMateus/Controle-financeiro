import streamlit as st
import sqlite3
import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta
import plotly.express as px
import numpy as np
from sklearn.ensemble import RandomForestRegressor
import libsql_experimental as libsql

# ==========================================
# 1. ARQUITETURA DE BANCOS DE DADOS
# ==========================================
st.set_page_config(page_title="Controle Financeiro Pessoal", layout="wide", page_icon="💰")

# --- BANCO MASTER (Apenas para guardar os Logins e Chaves Turso) ---
def get_master_connection():
    return libsql.connect(
        database= st.secrets["TURSO_URL"],
        auth_token= st.secrets["TURSO_AUTH_TOKEN"]
    )

def init_master_db():
    conn = get_master_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            nome TEXT NOT NULL,
            senha TEXT NOT NULL,
            turso_url TEXT NOT NULL,
            turso_token TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_master_db()

# --- BANCO PESSOAL (Conecta direto no Turso do Usuário Logado) ---
def get_personal_connection():
    
    return libsql.connect(
        database=st.session_state["user"]["turso_url"],
        auth_token=st.session_state["user"]["turso_token"]
    )

# ==========================================
# 2. SISTEMA DE LOGIN E CADASTRO TURSO
# ==========================================
if "user" not in st.session_state:
    st.session_state["user"] = None

def cadastrar_usuario(username, nome, senha, url, token):
    conn = get_master_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO usuarios (username, nome, senha, turso_url, turso_token) VALUES (?, ?, ?, ?, ?)", 
                       (username, nome, senha, url, token))
        conn.commit()
        return True
    except Exception as e:
        if "UNIQUE constraint failed" in str(e) or "SQLITE_CONSTRAINT" in str(e):
            return False
        raise e
    finally:
        conn.close()

def autenticar_usuario(username, senha):
    conn = get_master_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, nome, turso_url, turso_token FROM usuarios WHERE username = ? AND senha = ?", (username, senha))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        user_data = {"id": row[0], "username": row[1], "nome": row[2], "turso_url": row[3], "turso_token": row[4]}
        
        try:
            import libsql_experimental as libsql
            conn_p = libsql.connect(database=user_data["turso_url"], auth_token=user_data["turso_token"])
            cursor_p = conn_p.cursor()
            # Removido o Centro de Custo, agora é 100% pessoal
            cursor_p.execute("""
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
            """)
            conn_p.commit()
            conn_p.close()
            return user_data
        except Exception as e:
            st.error(f"Erro ao conectar ao seu banco Turso. Verifique suas chaves! Detalhes: {e}")
            return None
    return None

if st.session_state["user"] is None:
    st.title("💰 Controle Financeiro Pessoal")
    
    # Abas mais claras para você achar o Turso facilmente!
    aba_login, aba_cadastro = st.tabs(["🔐 Já tenho conta (Entrar)", "🆕 Criar Conta e Conectar Turso"])
    
    with aba_login:
        with st.form("form_login"):
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
        st.info("Para garantir sua privacidade, seus dados ficam no seu próprio banco. Preencha as chaves abaixo para criar sua conta.")
        with st.form("form_cadastro"):
            novo_usuario = st.text_input("Usuário / E-mail", autocomplete="new-username")
            novo_nome = st.text_input("Seu Nome")
            nova_senha = st.text_input("Senha", type="password", autocomplete="new-password")
            
            st.divider()
            st.subheader("🔗 Credenciais do Turso")
            nova_url = st.text_input("URL do Banco (Ex: libsql://seu-banco.turso.io)")
            novo_token = st.text_input("Token de Autenticação", type="password")
            
            if st.form_submit_button("Cadastrar e Conectar Banco"):
                if nova_url and novo_token:
                    if cadastrar_usuario(novo_usuario, novo_nome, nova_senha, nova_url, novo_token):
                        st.success("Conta criada! Volte na aba 'Já tenho conta' para fazer o login.")
                    else:
                        st.error("Este usuário já está cadastrado.")
                else:
                    st.warning("A URL e o Token do Turso são obrigatórios.")
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
menu = st.sidebar.radio("Navegação", ["Dashboard Analytics", "Contas por mês", "Novo Lançamento", "Gerar Recorrentes"])

# ==========================================
# DASHBOARD ANALYTICS 
# ==========================================
if menu == "Dashboard Analytics":
    st.header("📈 Dashboard Analytics Preditivo")
    
    c1, c2 = st.columns(2)
    filtro_mes = c1.selectbox("Mês", list(range(1, 13)), index=datetime.date.today().month - 1)
    filtro_ano = c2.number_input("Ano", min_value=2024, max_value=2030, value=datetime.date.today().year)
    
    conn = get_personal_connection()
    df_completo = pd.read_sql_query("SELECT * FROM lancamentos", conn)
    conn.close()
    
    if df_completo.empty:
        st.info("Nenhum dado encontrado para gerar análises.")
    else:
        df_completo["dt_data"] = pd.to_datetime(df_completo["data"])
        
        df_mes = df_completo[(df_completo["dt_data"].dt.month == filtro_mes) & (df_completo["dt_data"].dt.year == filtro_ano)]
        
        mes_anterior = filtro_mes - 1 if filtro_mes > 1 else 12
        ano_anterior = filtro_ano if filtro_mes > 1 else filtro_ano - 1
        df_mes_ant = df_completo[(df_completo["dt_data"].dt.month == mes_anterior) & (df_completo["dt_data"].dt.year == ano_anterior)]
        
        tot_atual = df_mes["valor"].sum()
        tot_anterior = df_mes_ant["valor"].sum()
        delta_perc = ((tot_atual - tot_anterior) / tot_anterior * 100) if tot_anterior > 0 else 0
        
        previsao_rf = 0
        df_historico = df_completo[df_completo["dt_data"] < datetime.datetime(filtro_ano, filtro_mes, 1) if filtro_mes > 1 else datetime.datetime(filtro_ano, 1, 1)]
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
        m2.metric("Total Pago", f"R$ {df_mes['valor_pago'].sum():,.2f}")
        m3.metric("Pendente", f"R$ {(tot_atual - df_mes['valor_pago'].sum()):,.2f}")
        
        if previsao_rf > 0:
            m4.metric("Previsão Estatística (ML)", f"R$ {previsao_rf:,.2f}", "Modelo Random Forest", delta_color="off")
        else:
            m4.metric("Previsão Estatística", "Dados insuficientes")

        st.divider()
        st.subheader("🚨 Detecção de Anomalias")
        anomalias = []
        df_hist_cat = df_completo.groupby(["categoria", df_completo["dt_data"].dt.to_period("M")])["valor"].sum().reset_index()
        estatisticas = df_hist_cat.groupby("categoria")["valor"].agg(['mean', 'std']).fillna(0)
        
        gasto_cat_atual = df_mes.groupby("categoria")["valor"].sum()
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
            df_pagamento = df_mes.groupby("metodo_pagamento")["valor"].sum().reset_index()
            fig_pagamento = px.pie(df_pagamento, values = "valor", names = 'metodo_pagamento', hole = 0.3)
            st.plotly_chart(fig_pagamento, width='stretch')
            
        with c_graf2:
            st.subheader("Distribuição por Categoria")
            df_pizza = df_mes.groupby("categoria")["valor"].sum().reset_index()
            fig_pizza = px.pie(df_pizza, values="valor", names="categoria", hole=0.4)
            st.plotly_chart(fig_pizza, width="stretch")
            
        st.divider()
        st.subheader("Top 5 Maiores Despesas")
        df_top5 = df_mes.sort_values(by="valor", ascending=False).head(5)[["descricao", "categoria", "valor"]]
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
elif menu == "Novo Lançamento":
    st.header("➕ Registrar Novo Lançamento")
    
    st.subheader("🤖 Inserção Inteligente com IA")
    texto_ia = st.text_input("Descreva o gasto naturalmente:", placeholder="Ex: Comprei 60 reais de farmácia hoje no cartão")
    
    if st.button("✨ Criar com IA", type="primary") and texto_ia:
        try:
            import google.generativeai as genai
            import json
            
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            modelo = genai.GenerativeModel('gemini-3.6-flash')
            
            prompt = f"""
            Analise a frase: "{texto_ia}"
            Retorne um JSON com estas chaves (focado em finanças pessoais):
            - "descricao": O local ou motivo (string)
            - "valor": Valor em numero (float)
            - "categoria": Sugira uma categoria logica (string)
            - "metodo_pagamento": 'Pix', 'Cartão de Crédito', 'Boleto', 'Dinheiro' ou 'Transferência' (string)
            - "data" : no Formato "%Y-%m-%d" usando como referência o dia de hoje ({datetime.date.today()})) (string)
            - "status": 'Pago' ou 'Pendente' (string)
            - "recorrente" : 'Sim' ou 'Não' (string)
            - "frequencia" :  "Mensal", "Único", "Anual", "Semanal" (string)
            """
            
            with st.spinner("A IA está analisando..."):
                resposta = modelo.generate_content(prompt)
                texto_limpo = resposta.text.replace("```json", "").replace("```", "").strip()
                dados_ia = json.loads(texto_limpo)
                
                conn = get_personal_connection()
                cursor = conn.cursor()
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
        except Exception as e:
            st.error(f"Erro na IA. Tente preencher manualmente. Detalhes: {e}")

    st.divider()
    
    st.subheader("✍️ Inserção Manual")
    with st.form("form_lancamento"):
        c1, c2 = st.columns(2)
        data = c1.date_input("Data", datetime.date.today())
        valor = c2.number_input("Valor Previsto (R$)", min_value=0.0, step=5.0)
        
        c3, c4, c5 = st.columns(3)
        categoria = c3.text_input("Categoria")
        metodo_pagamento = c4.selectbox("Método", ["Pix", "Cartão de Crédito", "Boleto", "Dinheiro", "Transferência"])
        status = c5.selectbox("Status", ["Pendente", "Pago", "Agendado", "Cancelado"])
        
        descricao_input = st.text_input("Descrição")
        
        c6, c7 = st.columns(2)
        frequencia = c6.selectbox("Frequência", ["Mensal", "Único", "Anual", "Semanal"])
        recorrente = "Não" if frequencia == "Único" else "Sim"
        valor_pago = c7.number_input("Valor Pago (R$)", min_value=0.0, step=5.0)
        observacao = st.text_area("Observação")
        
        if st.form_submit_button("Salvar Lançamento"):
            if descricao_input and categoria:
                if valor == 0 and valor_pago > 0:
                    valor = valor_pago
                conn = get_personal_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO lancamentos 
                    (data, descricao, valor, observacao, recorrente, status, categoria, metodo_pagamento, frequencia, valor_pago)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (str(data), descricao_input, valor, observacao, recorrente, status, categoria, metodo_pagamento, frequencia, valor_pago))
                conn.commit()
                conn.close()
                st.success("Salvo com sucesso!")
            else:
                st.warning("Preencha Descrição e Categoria.")

# ==========================================
# Contas por mês (Tabela Interativa)
# ==========================================
elif menu == "Contas por mês":
    st.header("📋 Gestão de Contas")
    
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
                hide_index=True, width="stretch", key="editor_contas"
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