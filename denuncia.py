import streamlit as st
import pandas as pd
import hashlib
from datetime import datetime
import time
import pytz

from google.oauth2 import service_account
from gspread.exceptions import WorksheetNotFound
import gspread
from fpdf import FPDF

# ============================================================
# CONFIGURAÇÃO INICIAL E FUSO
# ============================================================
st.set_page_config(page_title="URB Fiscalização", layout="wide")
FUSO_BR = pytz.timezone('America/Recife')

# Nomes das abas
SHEET_DENUNCIAS = "denuncias_registro"
SHEET_REINCIDENCIAS = "reincidencias"
SHEET_USUARIOS = "usuarios"

# Listas atualizadas com novas opções de status
OPCOES_STATUS = ['Pendente', 'Em Andamento', 'Em Monitoramento', 'Revisoria', 'Concluída', 'Arquivada']
OPCOES_ORIGEM = ['Pessoalmente', 'Telefone', 'Whatsapp', 'Ministério Publico', 'Administração', 'Ouvidoria', 'Disk Denuncia']
OPCOES_TIPO = ['Urbana', 'Ambiental', 'Urbana e Ambiental']
OPCOES_ZONA = ['TODAS', 'NORTE', 'SUL', 'LESTE', 'OESTE', 'CENTRO']
OPCOES_FISCAIS_SELECT = ['Edvaldo Wilson Bezerra da Silva - 000.323', 'PATRICIA MIRELLY BEZERRA CAMPOS - 000.332', 'Raiany Nayara de Lima - 000.362', 'Suellen Bezerra do Nascimeto - 000.417']

# ============================================================
# CONEXÃO GOOGLE SHEETS
# ============================================================
class SheetsClient:
    _gc = None
    _spreadsheet_key = None

    @classmethod
    def get_client(cls):
        if cls._gc is None:
            try:
                secrets = st.secrets["gcp_service_account"]
                cls._spreadsheet_key = secrets["spreadsheet_key"]
                info = dict(secrets)
                if "private_key" in info:
                    info["private_key"] = info["private_key"].replace("\\n", "\n")
                creds = service_account.Credentials.from_service_account_info(
                    info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
                )
                cls._gc = gspread.authorize(creds)
            except Exception as e:
                st.error(f"Erro no Login do Google Sheets: {e}")
                return None, None
        return cls._gc, cls._spreadsheet_key

# ============================================================
# FUNÇÃO GERADORA DE PDF
# ============================================================
def clean_text(text):
    if text is None: return ""
    return str(text).encode('latin-1', 'replace').decode('latin-1')

def gerar_pdf(dados):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, clean_text(f"ORDEM DE SERVICO - {dados.get('external_id','')}"), ln=True, align='C')
    pdf.line(10, 20, 200, 20)
    pdf.ln(10)
    pdf.set_font("Arial", size=12)
    campos = [
        ("Data Abertura", dados.get('created_at', '')),
        ("Status Atual", dados.get('status', 'Pendente')),
        ("Tipo", dados.get('tipo', '')),
        ("Origem", dados.get('origem', '')),
        ("Fiscal", dados.get('quem_recebeu', '')),
        ("Endereco", f"{dados.get('rua','')} , {dados.get('numero','')} - {dados.get('bairro','')}"),
        ("Zona", dados.get('zona', '')),
    ]
    for titulo, valor in campos:
        pdf.set_font("Arial", 'B', 12); pdf.cell(50, 10, clean_text(f"{titulo}:"), border=0)
        pdf.set_font("Arial", '', 12); pdf.cell(0, 10, clean_text(valor), ln=True)
    pdf.ln(5); pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, clean_text("Relato:"), ln=True)
    pdf.set_font("Arial", '', 12); pdf.multi_cell(0, 7, clean_text(dados.get('descricao', '')))
    pdf_content = pdf.output(dest='S')
    return bytes(pdf_content) if not isinstance(pdf_content, str) else pdf_content.encode('latin-1')

# ============================================================
# FUNÇÕES DE BANCO DE DADOS
# ============================================================
def get_worksheet(sheet_name):
    gc, key = SheetsClient.get_client()
    if not gc: return None
    sh = gc.open_by_key(key)
    try: return sh.worksheet(sheet_name)
    except WorksheetNotFound: return None

def load_data(sheet_name):
    ws = get_worksheet(sheet_name)
    if not ws: return pd.DataFrame()
    return pd.DataFrame(ws.get_all_records()).fillna('')

def update_full_sheet(sheet_name, df):
    ws = get_worksheet(sheet_name)
    ws.clear()
    ws.update([df.columns.tolist()] + df.values.tolist())

def salvar_dados_seguro(sheet_name, row_dict):
    ws = get_worksheet(sheet_name)
    headers = ws.row_values(1)
    values = [str(row_dict.get(h, '')) for h in headers]
    ws.append_row(values)

# ============================================================
# AUTENTICAÇÃO
# ============================================================
def hash_password(password): return hashlib.sha256(str(password).encode()).hexdigest()

def check_login(u, p):
    df = load_data(SHEET_USUARIOS)
    user = df[(df['username'] == u.lower()) & (df['password'] == hash_password(p))]
    return user.iloc[0].to_dict() if not user.empty else None

# ============================================================
# TELA LOGIN
# ============================================================
if 'user' not in st.session_state: st.session_state.user = None

if st.session_state.user is None:
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        st.title("🔐 URB Fiscalização")
        with st.form("login"):
            u, p = st.text_input("Usuário").strip(), st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar"):
                ud = check_login(u, p)
                if ud: st.session_state.user = ud; st.rerun()
                else: st.error("Login inválido")
    st.stop()

# ============================================================
# APP PRINCIPAL
# ============================================================
user_info = st.session_state.user
page = st.sidebar.radio("Menu", ["Dashboard", "Registrar Denúncia", "Histórico / Editar", "Reincidências"])
if st.sidebar.button("Sair"): st.session_state.user = None; st.rerun()

# --- PÁGINA 1: DASHBOARD ---
if page == "Dashboard":
    st.title("📊 Visão Geral")
    df = load_data(SHEET_DENUNCIAS)
    if not df.empty:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", len(df))
        c2.metric("Pendentes", len(df[df['status'] == 'Pendente']))
        c3.metric("Monitoramento", len(df[df['status'] == 'Em Monitoramento']))
        c4.metric("Concluídas", len(df[df['status'] == 'Concluída']))
        st.dataframe(df.tail(10), use_container_width=True)

# --- PÁGINA 2: REGISTRO ---
elif page == "Registrar Denúncia":
    st.title("📝 Nova Denúncia")
    with st.form('reg'):
        c1, c2 = st.columns(2)
        origem, tipo = c1.selectbox('Origem', OPCOES_ORIGEM), c2.selectbox('Tipo', OPCOES_TIPO)
        rua = st.text_input('Rua')
        c3, c4, c5 = st.columns(3)
        num, bairro, zona = c3.text_input('Número'), c4.text_input('Bairro'), c5.selectbox('Zona', [z for z in OPCOES_ZONA if z != 'TODAS'])
        desc = st.text_area('Descrição')
        quem = st.selectbox('Quem recebeu', OPCOES_FISCAIS_SELECT)
        if st.form_submit_button('💾 Salvar'):
            df = load_data(SHEET_DENUNCIAS)
            nid = len(df) + 1
            ext_id = f"{nid:04d}/{datetime.now().year}"
            rec = {
                'id': nid, 'external_id': ext_id, 'created_at': datetime.now(FUSO_BR).strftime('%Y-%m-%d %H:%M:%S'),
                'origem': origem, 'tipo': tipo, 'rua': rua, 'numero': num, 'bairro': bairro, 'zona': zona,
                'descricao': desc, 'quem_recebeu': quem, 'status': 'Pendente', 'acao_noturna': 'FALSE'
            }
            salvar_dados_seguro(SHEET_DENUNCIAS, rec); st.success(f"Salvo: {ext_id}"); time.sleep(1); st.rerun()

# --- PÁGINA 3: HISTÓRICO / GERENCIAR (MELHORADO) ---
elif page == "Histórico / Editar":
    st.title("🗂️ Gerenciar Fiscalizações")
    df = load_data(SHEET_DENUNCIAS)
    
    if df.empty: st.warning("Sem dados."); st.stop()

    # --- BARRA DE FILTROS ---
    with st.expander("🔍 Filtros de Busca", expanded=True):
        f1, f2, f3 = st.columns([2, 1, 1])
        f_bairro = f1.text_input("Filtrar por Bairro ou Rua")
        f_zona = f2.selectbox("Zona", OPCOES_ZONA)
        f_status = f3.selectbox("Status", ["TODOS"] + OPCOES_STATUS)

    # Aplicação dos filtros
    df_filt = df.copy()
    if f_bairro:
        df_filt = df_filt[df_filt['bairro'].str.contains(f_bairro, case=False) | df_filt['rua'].str.contains(f_bairro, case=False)]
    if f_zona != "TODAS":
        df_filt = df_filt[df_filt['zona'] == f_zona]
    if f_status != "TODOS":
        df_filt = df_filt[df_filt['status'] == f_status]

    # --- ÁREA DE EDIÇÃO ---
    if 'edit_id' in st.session_state:
        st.info(f"✏️ Editando: {st.session_state.edit_id}")
        idx = df.index[df['id'] == st.session_state.edit_id].tolist()[0]
        with st.form("form_edit"):
            nst = st.selectbox("Novo Status", OPCOES_STATUS, index=OPCOES_STATUS.index(df.at[idx, 'status']) if df.at[idx, 'status'] in OPCOES_STATUS else 0)
            ndesc = st.text_area("Descrição/Atualização", value=df.at[idx, 'descricao'], height=150)
            c_ed1, c_ed2 = st.columns(2)
            if c_ed1.form_submit_button("✅ Salvar Alterações"):
                df.at[idx, 'status'], df.at[idx, 'descricao'] = nst, ndesc
                update_full_sheet(SHEET_DENUNCIAS, df); del st.session_state.edit_id; st.rerun()
            if c_ed2.form_submit_button("❌ Cancelar"): del st.session_state.edit_id; st.rerun()
    
    # --- LISTAGEM ---
    st.write(f"Exibindo **{len(df_filt)}** resultados")
    for _, row in df_filt.sort_values(by='id', ascending=False).iterrows():
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([1, 3, 1.5, 1])
            col1.markdown(f"**{row['external_id']}**\n\n{row['created_at'][:10]}")
            col2.markdown(f"📍 **{row['bairro']}** - {row['rua']}, {row['numero']}\n\n📝 _{row['descricao'][:100]}..._")
            
            # Badge de Status
            cor = "orange" if row['status'] == "Pendente" else "blue" if "Monitoramento" in row['status'] else "green" if row['status'] == "Concluída" else "gray"
            col3.markdown(f":{cor}[**{row['status']}**]")
            col3.caption(f"Fiscal: {row['quem_recebeu'].split(' - ')[0]}")

            # Botões de Ação
            b1, b2, b3 = col4.columns(3)
            if b1.button("✏️", key=f"ed_{row['id']}"): st.session_state.edit_id = row['id']; st.rerun()
            
            # PDF
            pdf_b = gerar_pdf(row)
            b2.download_button("📄", pdf_b, f"OS_{row['id']}.pdf", "application/pdf", key=f"pdf_{row['id']}")
            
            # Botão Excluir com confirmação simples (via session_state para segurança)
            if b3.button("🗑️", key=f"del_{row['id']}"):
                if user_info['role'] == 'admin':
                    df = df[df['id'] != row['id']]
                    update_full_sheet(SHEET_DENUNCIAS, df)
                    st.toast("Registro excluído!"); time.sleep(1); st.rerun()
                else: st.error("Apenas admins excluem.")

# --- PÁGINA 4: REINCIDÊNCIAS ---
elif page == "Reincidências":
    st.title("🔄 Registrar Reincidência")
    df_den = load_data(SHEET_DENUNCIAS)
    if not df_den.empty:
        escolha = st.selectbox("Selecione a Denúncia", df_den['external_id'] + " - " + df_den['rua'])
        if escolha:
            eid = escolha.split(" - ")[0]
            idx = df_den.index[df_den['external_id'] == eid].tolist()[0]
            with st.form("reinc"):
                nova_desc = st.text_area("Novo Relato da Reincidência")
                if st.form_submit_button("Reabrir como Pendente"):
                    df_den.at[idx, 'status'] = 'Pendente'
                    df_den.at[idx, 'descricao'] += f"\n\n[REINCIDÊNCIA {datetime.now().strftime('%d/%m/%Y')}]: {nova_desc}"
                    update_full_sheet(SHEET_DENUNCIAS, df_den); st.success("Caso reaberto!"); time.sleep(1); st.rerun()
