import streamlit as st
from streamlit.components.v1 import html
from datetime import datetime
import os
import sqlite3
from sqlite3 import Connection
from typing import List, Optional
import pandas as pd
import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from PIL import Image

# --------- CONFIG ----------
DATA_DIR = "data"
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "denuncias.db")
os.makedirs(UPLOAD_DIR, exist_ok=True)
# --------------------------

st.set_page_config(page_title="Registro de Denúncias", layout="wide")

# ---------- DB helpers ----------
def get_conn() -> Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS denuncias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        tipo TEXT,
        rua TEXT,
        numero TEXT,
        bairro TEXT,
        cidade TEXT,
        estado TEXT,
        cep TEXT,
        lat REAL,
        lon REAL,
        descricao TEXT,
        observacao TEXT,
        created_at TEXT
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS imagens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        denuncia_id INTEGER,
        filename TEXT,
        FOREIGN KEY(denuncia_id) REFERENCES denuncias(id) ON DELETE CASCADE
    )
    """)
    conn.commit()

def make_code(next_id: int) -> str:
    date = datetime.now().strftime("%Y%m%d")
    return f"DEN-{date}-{next_id:05d}"

def insert_denuncia(data: dict, image_files: List) -> int:
    conn = get_conn()
    c = conn.cursor()
    # get next id (autoincrement preview)
    c.execute("SELECT seq FROM sqlite_sequence WHERE name='denuncias'")
    row = c.fetchone()
    seq = (row[0] if row else 0) + 1
    code = make_code(seq)
    now = datetime.now().isoformat()
    c.execute("""
    INSERT INTO denuncias(code,tipo,rua,numero,bairro,cidade,estado,cep,lat,lon,descricao,observacao,created_at)
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        code,
        data.get("tipo"),
        data.get("rua"),
        data.get("numero"),
        data.get("bairro"),
        data.get("cidade"),
        data.get("estado"),
        data.get("cep"),
        data.get("lat"),
        data.get("lon"),
        data.get("descricao"),
        data.get("observacao"),
        now
    ))
    denuncia_id = c.lastrowid
    # save images
    folder = os.path.join(UPLOAD_DIR, str(denuncia_id))
    os.makedirs(folder, exist_ok=True)
    for uploaded in image_files:
        # uploaded is a UploadedFile from streamlit
        fname = uploaded.name
        path = os.path.join(folder, fname)
        with open(path, "wb") as f:
            f.write(uploaded.getbuffer())
        c.execute("INSERT INTO imagens(denuncia_id,filename) VALUES(?,?)", (denuncia_id, fname))
    conn.commit()
    return denuncia_id

def get_all_denuncias() -> List[sqlite3.Row]:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM denuncias ORDER BY created_at DESC")
    return c.fetchall()

def get_denuncia_by_id(den_id: int) -> Optional[sqlite3.Row]:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM denuncias WHERE id=?", (den_id,))
    return c.fetchone()

def get_images_for(den_id: int) -> List[str]:
    folder = os.path.join(UPLOAD_DIR, str(den_id))
    if not os.path.exists(folder):
        return []
    return os.listdir(folder)

def update_denuncia(den_id: int, data: dict, new_images: List):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
    UPDATE denuncias SET tipo=?,rua=?,numero=?,bairro=?,cidade=?,estado=?,cep=?,lat=?,lon=?,descricao=?,observacao=?
    WHERE id=?
    """,(data.get("tipo"),data.get("rua"),data.get("numero"),data.get("bairro"),data.get("cidade"),data.get("estado"),
         data.get("cep"),data.get("lat"),data.get("lon"),data.get("descricao"),data.get("observacao"),den_id))
    folder = os.path.join(UPLOAD_DIR, str(den_id))
    os.makedirs(folder, exist_ok=True)
    for uploaded in new_images:
        fname = uploaded.name
        path = os.path.join(folder, fname)
        with open(path, "wb") as f:
            f.write(uploaded.getbuffer())
        c.execute("INSERT INTO imagens(denuncia_id,filename) VALUES(?,?)", (den_id, fname))
    conn.commit()

def delete_denuncia(den_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM denuncias WHERE id=?", (den_id,))
    # delete files
    folder = os.path.join(UPLOAD_DIR, str(den_id))
    if os.path.exists(folder):
        for f in os.listdir(folder):
            os.remove(os.path.join(folder, f))
        os.rmdir(folder)
    conn.commit()

# ---------- PDF generation ----------
def generate_pdf_for(denuncia_row: sqlite3.Row) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    x = 50
    y = height - 50
    c.setFont("Helvetica-Bold", 14)
    c.drawString(x, y, f"Ordem de Serviço - {denuncia_row['code']}")
    c.setFont("Helvetica", 11)
    y -= 30
    lines = [
        ("Tipo", denuncia_row["tipo"]),
        ("Rua", denuncia_row["rua"]),
        ("Número", denuncia_row["numero"]),
        ("Bairro", denuncia_row["bairro"]),
        ("Cidade", denuncia_row["cidade"]),
        ("Estado", denuncia_row["estado"]),
        ("CEP", denuncia_row["cep"]),
        ("Latitude", str(denuncia_row["lat"])),
        ("Longitude", str(denuncia_row["lon"])),
    ]
    for label, val in lines:
        c.drawString(x, y, f"{label}: {val}")
        y -= 16
    y -= 6
    c.drawString(x, y, "Descrição:")
    y -= 14
    text = c.beginText(x, y)
    text.setFont("Helvetica", 10)
    for line in (denuncia_row["descricao"] or "").split("\n"):
        text.textLine(line)
        y -= 12
    c.drawText(text)
    y -= 12
    c.drawString(x, y, "Observação:")
    y -= 14
    text2 = c.beginText(x, y)
    text2.setFont("Helvetica", 10)
    for line in (denuncia_row["observacao"] or "").split("\n"):
        text2.textLine(line)
        y -= 12
    c.drawText(text2)

    # imagens em anexo - mostrar thumbnails (até 4)
    imgs = get_images_for(denuncia_row["id"])
    if imgs:
        y -= 30
        c.drawString(x, y, "Imagens anexadas:")
        y -= 16
        folder = os.path.join(UPLOAD_DIR, str(denuncia_row["id"]))
        thumb_w = 120
        thumb_h = 90
        x_img = x
        for i, img_name in enumerate(imgs[:4]):
            img_path = os.path.join(folder, img_name)
            try:
                im = Image.open(img_path)
                im.thumbnail((thumb_w, thumb_h))
                tmp = io.BytesIO()
                im.save(tmp, format="PNG")
                tmp.seek(0)
                c.drawInlineImage(tmp, x_img, y - thumb_h, width=thumb_w, height=thumb_h)
                x_img += thumb_w + 10
            except Exception:
                pass

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.read()

# ---------- geolocation component ----------
GEO_HTML = """
<button onclick="getLocation()">Obter geolocalização do navegador</button>
<p id="status"></p>
<script>
async function getLocation() {
  const status = document.getElementById('status');
  status.innerText = 'Solicitando permissão...';
  if (!navigator.geolocation) {
    status.innerText = 'Geolocalização não suportada.';
    return;
  }
  navigator.geolocation.getCurrentPosition(success, error);
  function success(pos) {
    const lat = pos.coords.latitude;
    const lon = pos.coords.longitude;
    const msg = ${lat},${lon};
    // envia para Streamlit
    const el = document.createElement('div');
    el.innerText = msg;
    el.id = 'geo_result';
    el.style.display='none';
    document.body.appendChild(el);
    const event = new Event("geo-ready");
    window.dispatchEvent(event);
  }
  function error(err) {
    status.innerText = 'Erro ao obter localização: ' + err.message;
  }
}
</script>
"""

# ---------- UI ----------
init_db()
st.title("Sistema de Registro de Denúncias (Urbana / Ambiental)")

menu = st.sidebar.selectbox("Navegar", ["Registrar", "Pesquisar / Editar", "Exportar CSV", "Usuários (admin)"])

if menu == "Registrar":
    st.header("Registrar nova denúncia")
    with st.form("form_den"):
        tipo = st.selectbox("Tipo de denúncia", ["Urbana", "Ambiental"])
        rua = st.text_input("Rua")
        numero = st.text_input("Número")
        bairro = st.text_input("Bairro")
        cidade = st.text_input("Cidade")
        estado = st.text_input("Estado")
        cep = st.text_input("CEP")
        col1, col2 = st.columns(2)
        with col1:
            lat = st.text_input("Latitude (ou use 'Obter geolocalização')", "")
        with col2:
            lon = st.text_input("Longitude", "")
        st.markdown("*Geolocalização (opcional)*")
        html(GEO_HTML, height=120)
        # small JS listener: read invisible element text via streamlit experimental_get_query_params can't; 
        # simpler: ask user to paste coordinates that the button wrote in the page (we explained the browser will create text)
        st.info("Depois de clicar em 'Obter geolocalização', copie o texto invisível que aparece na página e cole em Latitude,Longitude se necessário.")
        descricao = st.text_area("Descrição")
        observacao = st.text_area("Observação (aparece na OS)")
        imagens = st.file_uploader("Imagens (várias)", accept_multiple_files=True, type=['png','jpg','jpeg'])
        submitted = st.form_submit_button("Salvar denúncia")
        if submitted:
            data = dict(tipo=tipo, rua=rua, numero=numero, bairro=bairro, cidade=cidade, estado=estado, cep=cep,
                        lat=(float(lat) if lat else None), lon=(float(lon) if lon else None),
                        descricao=descricao, observacao=observacao)
            new_id = insert_denuncia(data, imagens or [])
            den = get_denuncia_by_id(new_id)
            st.success(f"Denúncia salva com ID {new_id} e código {den['code']}")
            # show google maps link if coords present
            if den['lat'] and den['lon']:
                gmap = f"https://www.google.com/maps/search/?api=1&query={den['lat']},{den['lon']}"
                st.markdown(f"[Abrir no Google Maps]({gmap})")
            st.experimental_rerun()

elif menu == "Pesquisar / Editar":
    st.header("Pesquisar / Editar / Excluir denúncias")
    q = st.text_input("Pesquisar por código (ex: DEN-2025...) ou bairro / cidade")
    all_den = get_all_denuncias()
    df = pd.DataFrame(all_den)
    if q:
        mask = df.apply(lambda row: q.lower() in (str(row['code']) + " " + str(row['bairro']) + " " + str(row['cidade'])).lower(), axis=1)
        df = df[mask]
    st.write(f"Encontradas: {len(df)}")
    for _, row in df.iterrows():
        with st.expander(f"{row['code']} — {row['tipo']} — {row['bairro']} / {row['cidade']}"):
            cols = st.columns([2,1,1,1])
            cols[0].markdown(f"*Endereço:* {row['rua']}, {row['numero']} — {row['bairro']} — {row['cidade']}/{row['estado']}  \n"
                             f"*Descrição:* {row['descricao'][:200]}")
            if row['lat'] and row['lon']:
                gmap = f"https://www.google.com/maps/search/?api=1&query={row['lat']},{row['lon']}"
                cols[1].markdown(f"[Abrir no Google Maps]({gmap})")
            if cols[2].button("Gerar PDF", key=f"pdf_{row['id']}"):
                data_pdf = generate_pdf_for(row)
                st.download_button(label="Download PDF", data=data_pdf, file_name=f"OS_{row['code']}.pdf", mime="application/pdf")
            if cols[3].button("Editar", key=f"edit_{row['id']}"):
                st.session_state["edit_id"] = row['id']
                st.experimental_rerun()
            if st.button("Excluir", key=f"del_{row['id']}", help="Apaga definitivamente"):
                delete_denuncia(row['id'])
                st.success("Denúncia excluída.")
                st.experimental_rerun()

    # editar
    if "edit_id" in st.session_state:
        den_id = st.session_state["edit_id"]
        den = get_denuncia_by_id(den_id)
        st.markdown("---")
        st.subheader(f"Editando: {den['code']}")
        with st.form("form_edit"):
            tipo = st.selectbox("Tipo de denúncia", ["Urbana", "Ambiental"], index=0 if den['tipo']=="Urbana" else 1)
            rua = st.text_input("Rua", den['rua'])
            numero = st.text_input("Número", den['numero'])
            bairro = st.text_input("Bairro", den['bairro'])
            cidade = st.text_input("Cidade", den['cidade'])
            estado = st.text_input("Estado", den['estado'])
            cep = st.text_input("CEP", den['cep'])
            lat = st.text_input("Latitude", "" if den['lat'] is None else str(den['lat']))
            lon = st.text_input("Longitude", "" if den['lon'] is None else str(den['lon']))
            descricao = st.text_area("Descrição", den['descricao'])
            observacao = st.text_area("Observação", den['observacao'])
            novas_imagens = st.file_uploader("Adicionar novas imagens", accept_multiple_files=True, type=['png','jpg','jpeg'])
            save = st.form_submit_button("Salvar alterações")
            cancel = st.form_submit_button("Cancelar")
            if save:
                data = dict(tipo=tipo, rua=rua, numero=numero, bairro=bairro, cidade=cidade, estado=estado, cep=cep,
                            lat=(float(lat) if lat else None), lon=(float(lon) if lon else None),
                            descricao=descricao, observacao=observacao)
                update_denuncia(den_id, data, novas_imagens or [])
                st.success("Denúncia atualizada.")
                del st.session_state["edit_id"]
                st.experimental_rerun()
            if cancel:
                del st.session_state["edit_id"]
                st.experimental_rerun()

elif menu == "Exportar CSV":
    st.header("Exportar para planilha (CSV)")
    all_den = get_all_denuncias()
    rows = []
    for r in all_den:
        imgs = get_images_for(r['id'])
        rows.append({
            "id": r['id'],
            "code": r['code'],
            "tipo": r['tipo'],
            "rua": r['rua'],
            "numero": r['numero'],
            "bairro": r['bairro'],
            "cidade": r['cidade'],
            "estado": r['estado'],
            "cep": r['cep'],
            "lat": r['lat'],
            "lon": r['lon'],
            "descricao": r['descricao'],
            "observacao": r['observacao'],
            "imagens": ";".join(imgs),
            "created_at": r['created_at']
        })
    df = pd.DataFrame(rows)
    st.dataframe(df)
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("Download CSV (pode colar no Google Sheets)", csv, "denuncias.csv", "text/csv")

elif menu == "Usuários (admin)":
    st.header("Usuários (exemplo simples)")
    st.info("Para produção, use Firebase Auth, OAuth ou um provedor seguro. Aqui só mostramos onde gerenciar usuários.")
    st.write("Implementação de autenticação não incluída neste exemplo — recomendo usar streamlit-authenticator ou Firebase.")