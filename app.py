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

def gerar_resposta_ia(prompt, modelo_nome='gemini-3.6-flash'):
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    modelo = genai.GenerativeModel(modelo_nome)
    resposta = modelo.generate_content(prompt)
    texto_limpo = resposta.text.replace("```json", "").replace("```", "").strip()
    return json.loads(texto_limpo)


# ==========================================
# 1. ARQUITETURA DE BANCOS DE DADOS
# ==========================================
st.set_page_config(page_title="Controle Financeiro Pessoal", layout="wide", page_icon="💰")

# --- BANCO PESSOAL (Conecta direto no Turso do Usuário Logado) ---
def get_personal_connection():
    return libsql.connect(
        database=st.session_state["user"]["turso_url"],
        auth_token=st.session_state["user"]["turso_token"]
    )

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
            CREATE TABLE IF NOT EXISTS tarefas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                data_vencimento DATE,
                status TEXT NOT NULL
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
    ["Dashboard", "Finanças", "Tarefas", "Agenda", "Estudos", "Projetos"]
)

st.sidebar.divider()
if menu_principal == "Finanças":
    menu = st.sidebar.radio("Sub-menu", ["Lançamentos", "Receitas", "Despesas", "Orçamento", "Análises", "Contas por mês", "Gerar Recorrentes"])
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

elif menu in ["Receitas", "Despesas"]:
    st.header(f"📉 {menu}")
    conn = get_personal_connection()
    df = pd.read_sql_query("SELECT * FROM lancamentos", conn)
    conn.close()

    if not df.empty:
        if menu == "Receitas":
            df_filtered = df[df["valor"] > 0] # Assuming positive values or by category? Let's assume user inputs 'Receitas' in category or has a specific method.
            # Actually, standard way is to assume positive or let user filter.
            # We will use category 'Receita' or 'Salário' or just show the table filtered.
            df_filtered = df[df['categoria'].str.contains('Receita|Salário|Rendimento', case=False, na=False)]
        else:
            df_filtered = df[~df['categoria'].str.contains('Receita|Salário|Rendimento', case=False, na=False)]

        st.dataframe(df_filtered, use_container_width=True)
    else:
        st.info("Nenhum dado encontrado.")

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
                dados_ia = gerar_resposta_ia(prompt)
                
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
# ==========================================
# MÓDULO: TAREFAS
# ==========================================
if menu_principal == "Tarefas":
    st.header("✅ Gestão de Tarefas")
    menu_tarefas = st.sidebar.radio("Tarefas", ["Hoje", "Próximas", "Atrasadas", "Concluídas", "Nova Tarefa"])

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
            df_tarefas['data_vencimento'] = pd.to_datetime(df_tarefas['data_vencimento']).dt.date
            hoje = datetime.date.today()

            if menu_tarefas == "Hoje":
                df_exibir = df_tarefas[(df_tarefas['data_vencimento'] == hoje) & (df_tarefas['status'] != 'Concluída')]
            elif menu_tarefas == "Próximas":
                df_exibir = df_tarefas[(df_tarefas['data_vencimento'] > hoje) & (df_tarefas['status'] != 'Concluída')]
            elif menu_tarefas == "Atrasadas":
                df_exibir = df_tarefas[(df_tarefas['data_vencimento'] < hoje) & (df_tarefas['status'] != 'Concluída')]
            else: # Concluídas
                df_exibir = df_tarefas[df_tarefas['status'] == 'Concluída']

            st.dataframe(df_exibir, use_container_width=True)
        else:
            st.info("Nenhuma tarefa encontrada.")

# ==========================================
# MÓDULO: AGENDA
# ==========================================
elif menu_principal == "Agenda":
    st.header("📅 Agenda")
    menu_agenda = st.sidebar.radio("Agenda", ["Aulas", "Compromissos", "Eventos", "Novo Evento"])

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
                    st.success("Evento inserido com sucesso!")
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
    menu_projetos = st.sidebar.radio("Projetos", ["Projetos pessoais", "PET", "IC", "Programação", "Novo Projeto"])

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
    st.header(f"📊 {menu_principal}")

    conn = get_personal_connection()
    try:
        df_lancamentos = pd.read_sql_query("SELECT * FROM lancamentos", conn)
        df_tarefas = pd.read_sql_query("SELECT * FROM tarefas", conn)
        df_agenda = pd.read_sql_query("SELECT * FROM agenda", conn)
        df_projetos = pd.read_sql_query("SELECT * FROM projetos", conn)
    finally:
        conn.close()

    c1, c2 = st.columns(2)

    with c1:
        st.subheader("💰 Situação Financeira")
        if not df_lancamentos.empty:
            df_lancamentos["dt_data"] = pd.to_datetime(df_lancamentos["data"])
            df_mes = df_lancamentos[(df_lancamentos["dt_data"].dt.month == datetime.date.today().month) & (df_lancamentos["dt_data"].dt.year == datetime.date.today().year)]
            receitas = df_mes[df_mes['categoria'].str.contains('Receita|Salário|Rendimento', case=False, na=False)]['valor'].sum()
            despesas = df_mes[~df_mes['categoria'].str.contains('Receita|Salário|Rendimento', case=False, na=False)]['valor'].sum()
            st.metric("Saldo do Mês", f"R$ {receitas - despesas:.2f}", f"Receitas: {receitas:.2f} | Despesas: {despesas:.2f}")
        else:
            st.info("Sem dados financeiros.")

        st.subheader("✅ Tarefas Pendentes")
        if not df_tarefas.empty:
            pendentes = df_tarefas[df_tarefas['status'] != 'Concluída']
            st.metric("Total Pendente", len(pendentes))
        else:
            st.info("Sem tarefas pendentes.")

    with c2:
        st.subheader("📅 Próximos Compromissos")
        if not df_agenda.empty:
            df_agenda["data_hora"] = pd.to_datetime(df_agenda["data_hora"])
            futuros = df_agenda[df_agenda["data_hora"] >= pd.Timestamp.now()]
            st.metric("Eventos Futuros", len(futuros))
        else:
            st.info("Sem eventos agendados.")

        st.subheader("📈 Progresso dos Projetos")
        if not df_projetos.empty:
            andamento = df_projetos[df_projetos['status'] == 'Em andamento']
            st.metric("Projetos em Andamento", len(andamento))
        else:
            st.info("Sem projetos ativos.")

    st.divider()
    if st.button("✨ Gerar Resumo com IA (Visão Global)", type="primary"):
        with st.spinner("A IA está analisando sua vida..."):
            resumo_dados = f"""
            Finanças do Mês: Receitas {receitas if not df_lancamentos.empty else 0}, Despesas {despesas if not df_lancamentos.empty else 0}.
            Tarefas Pendentes: {len(df_tarefas[df_tarefas['status'] != 'Concluída']) if not df_tarefas.empty else 0}.
            Eventos Futuros: {len(df_agenda[pd.to_datetime(df_agenda['data_hora']) >= pd.Timestamp.now()]) if not df_agenda.empty else 0}.
            Projetos Ativos: {len(df_projetos[df_projetos['status'] == 'Em andamento']) if not df_projetos.empty else 0}.
            """
            prompt_resumo = f"""
            Você é um assistente pessoal inteligente. Com base nos dados abaixo, faça um resumo motivacional
            e estratégico do momento do usuário, em um tom encorajador e direto. Retorne apenas o texto formatado em Markdown.
            DADOS:
            {resumo_dados}
            """
            try:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                modelo = genai.GenerativeModel('gemini-3.6-flash')
                resposta = modelo.generate_content(prompt_resumo)
                st.markdown(resposta.text)
            except Exception as e:
                st.error(f"Erro ao gerar resumo: {e}")
