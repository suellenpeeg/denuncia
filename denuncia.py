import streamlit as st
import sqlite3
import os
from datetime import datetime
from PIL import Image
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# -------------- CONFIG --------------
st.set_page_config(page_title="Denúncias - Protótipo", layout="wide")

DB_FILE = "denuncias.db"
UPLOAD_ROOT = "uploads"
os.makedirs(UPLOAD_ROOT, exist_ok=True)
LOGO_PATH = "logo.png"  # opcional: se existir, será incluído no PDF
# -------------------------------------

# -------------- DB HELPERS --------------
def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS denuncias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        tipo TEXT,
        rua TEXT,
        numero TEXT,
        bairro TEXT,
        lat REAL,
        lon REAL,
        descricao TEXT,
        observacao TEXT,
        created_date TEXT,
        created_time TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS imagens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        denuncia_id INTEGER,
        filename TEXT,
        FOREIGN KEY(denuncia_id) REFERENCES denuncias(id) ON DELETE CASCADE
    )
    """)
    conn.commit()
    conn.close()

def make_code(next_id):
    # código legível com timestamp e id
    return f"DEN-{datetime.now().strftime('%Y%m%d')}-{next_id:05d}"

def next_seq():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT seq FROM sqlite_sequence WHERE name='denuncias'")
    row = cur.fetchone()
    conn.close()
    seq = (row[0] if row else 0) + 1
    return seq

def row_to_dict(row):
    # row is a sqlite3.Row or tuple: we'll handle tuple positions if tuple
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    # If row is a tuple, map by schema order
    # denuncias columns: id,code,tipo,rua,numero,bairro,lat,lon,descricao,observacao,created_date,created_time
    return {
        "id": row[0],
        "code": row[1],
        "tipo": row[2],
        "rua": row[3],
        "numero": row[4],
        "bairro": row[5],
        "lat": row[6],
        "lon": row[7],
        "descricao": row[8],
        "observacao": row[9],
        "created_date": row[10],
        "created_time": row[11]
    }

init_db()

# -------------- UTIL --------------
def safe_float(value):
    if value is None:
        return None
    v = str(value).strip()
    if v == "":
        return None
    v = v.replace(",", ".")
    try:
        return float(v)
    except:
        return None

def save_images_files(denuncia_id, uploaded_files):
    folder = os.path.join(UPLOAD_ROOT, str(denuncia_id))
    os.makedirs(folder, exist_ok=True)
    conn = get_conn()
    cur = conn.cursor()
    for f in uploaded_files:
        fname = f.name
        path = os.path.join(folder, fname)
        # evitar sobrescrever: se já existir, adiciona sufixo
        base, ext = os.path.splitext(fname)
        i = 1
        while os.path.exists(path):
            fname = f"{base}_{i}{ext}"
            path = os.path.join(folder, fname)
            i += 1
        with open(path, "wb") as out:
            out.write(f.getbuffer())
        cur.execute("INSERT INTO imagens (denuncia_id, filename) VALUES (?,?)", (denuncia_id, fname))
    conn.commit()
    conn.close()

def list_images(denuncia_id):
    folder = os.path.join(UPLOAD_ROOT, str(denuncia_id))
    if not os.path.isdir(folder):
        return []
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT filename FROM imagens WHERE denuncia_id=?", (denuncia_id,))
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]

def delete_denuncia_and_files(denuncia_id):
    # delete files
    folder = os.path.join(UPLOAD_ROOT, str(denuncia_id))
    if os.path.isdir(folder):
        for fname in os.listdir(folder):
            try:
                os.remove(os.path.join(folder, fname))
            except:
                pass
        try:
            os.rmdir(folder)
        except:
            pass
    # delete db rows
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM imagens WHERE denuncia_id=?", (denuncia_id,))
    cur.execute("DELETE FROM denuncias WHERE id=?", (denuncia_id,))
    conn.commit()
    conn.close()

# -------------- PDF (estilo profissional) --------------
def generate_pdf(den_dict, image_paths):
    """
    den_dict: dict with fields:
    code, tipo, rua, numero, bairro, lat, lon, descricao, observacao, created_date, created_time
    image_paths: list of absolute paths to image files
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    W, H = A4
    margin = 40
    x = margin
    y = H - margin

    # Header (logo + title)
    if os.path.exists(LOGO_PATH):
        try:
            logo = Image.open(LOGO_PATH)
            logo.thumbnail((120, 60))
            logo_buf = io.BytesIO()
            logo.save(logo_buf, format="PNG")
            logo_buf.seek(0)
            c.drawImage(ImageReader(logo_buf), x, y - 60, width=120, height=60)
        except:
            pass

    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(W/2, y - 20, "ORDEM DE SERVIÇO")
    y -= 80

    # Info box 1: identificação
    box_height = 90
    c.setStrokeColor(colors.black)
    c.rect(x, y - box_height, W - 2*margin, box_height, stroke=1, fill=0)
    txt_x = x + 8
    txt_y = y - 20
    c.setFont("Helvetica-Bold", 11)
    c.drawString(txt_x, txt_y, f"CÓDIGO: {den_dict.get('code','')}")
    c.setFont("Helvetica", 10)
    c.drawString(txt_x + 300, txt_y, f"DATA: {den_dict.get('created_date','')}")
    c.drawString(txt_x + 430, txt_y, f"HORA: {den_dict.get('created_time','')}")
    txt_y -= 18
    c.drawString(txt_x, txt_y, f"Tipo: {den_dict.get('tipo','')}")
    c.drawString(txt_x + 200, txt_y, f"Rua: {den_dict.get('rua','')}")
    c.drawString(txt_x + 420, txt_y, f"Nº: {den_dict.get('numero','')}")
    txt_y -= 18
    c.drawString(txt_x, txt_y, f"Bairro: {den_dict.get('bairro','')}")
    txt_y -= 18
    c.drawString(txt_x, txt_y, f"Lat: {den_dict.get('lat','')}   Lon: {den_dict.get('lon','')}")

    y = y - box_height - 20

    # Info box 2: descrição
    box_h = 140
    c.rect(x, y - box_h, W - 2*margin, box_h, stroke=1, fill=0)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(txt_x, y - 18, "DESCRIÇÃO:")
    c.setFont("Helvetica", 10)
    # wrap description
    desc = den_dict.get('descricao') or ""
    text = c.beginText(txt_x, y - 36)
    text.setFont("Helvetica", 10)
    max_width = W - 2*margin - 16
    # naive wrap
    for line in desc.splitlines():
        line = line.strip()
        while line:
            # measure approximate chars per line
            # assume avg char width -> use 7 pixels per char approx for 10pt -> conservative
            approx_chars = int(max_width / 6.5)
            part = line[:approx_chars]
            text.textLine(part)
            line = line[len(part):]
    c.drawText(text)

    y = y - box_h - 20

    # Observação box with 10 blank lines
    obs_box_h = 10 * 14 + 30  # lines + header spacing
    c.rect(x, y - obs_box_h, W - 2*margin, obs_box_h, stroke=1, fill=0)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(txt_x, y - 18, "OBSERVAÇÃO:")
    c.setFont("Helvetica", 10)
    # existing observations
    obs = den_dict.get('observacao') or ""
    text_obs = c.beginText(txt_x, y - 36)
    text_obs.setFont("Helvetica", 10)
    max_width = W - 2*margin - 16
    for line in obs.splitlines():
        line = line.strip()
        while line:
            approx_chars = int(max_width / 6.5)
            part = line[:approx_chars]
            text_obs.textLine(part)
            line = line[len(part):]
    c.drawText(text_obs)
    # draw 10 blank lines inside the box (horizontal faint lines)
    start_y = y - 50
    line_gap = 14
    c.setStrokeColor(colors.lightgrey)
    for i in range(10):
        ly = start_y - i*line_gap
        c.line(txt_x, ly, W - margin - 8, ly)
    c.setStrokeColor(colors.black)

    y = y - obs_box_h - 20

    # Images: two per row
    if image_paths:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(txt_x, y - 10, "IMAGENS:")
        y = y - 30
        img_w = (W - 2*margin - 24) / 2  # two per row with small gap
        img_h = 150
        cur_x = txt_x
        cur_y = y
        for i, p in enumerate(image_paths):
            try:
                im = Image.open(p)
                # maintain aspect ratio inside box
                ratio = min(img_w / im.width, img_h / im.height)
                draw_w = im.width * ratio
                draw_h = im.height * ratio
                # center inside allocated box
                offset_x = cur_x + (img_w - draw_w)/2
                offset_y = cur_y - draw_h
                img_buf = io.BytesIO()
                im.save(img_buf, format="PNG")
                img_buf.seek(0)
                c.drawImage(ImageReader(img_buf), offset_x, offset_y, width=draw_w, height=draw_h)
            except Exception:
                # skip problematic image
                pass
            if (i % 2) == 0:
                cur_x = txt_x + img_w + 12
            else:
                # next row
                cur_x = txt_x
                cur_y -= (img_h + 18)
            # page break if low space
            if cur_y < margin + img_h:
                c.showPage()
                cur_y = H - margin - 60
                c.setFont("Helvetica-Bold", 11)
                c.drawString(txt_x, cur_y + 40, "IMAGENS (cont.):")
                cur_y -= 20

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.read()

# -------------- UI --------------
st.title("Protótipo de Registro de Denúncias (Urbana / Ambiental)")

menu = st.sidebar.selectbox("Menu", ["Registrar", "Pesquisar / Editar"])

# ---------- Registrar ----------
if menu == "Registrar":
    st.header("Registrar nova denúncia")

    with st.form("form_new"):
        tipo = st.selectbox("Tipo de denúncia", ["Urbana", "Ambiental"])
        rua = st.text_input("Rua")
        # número menor: colocar em coluna estreita
        col1, col2 = st.columns([1,6])
        with col1:
            numero = st.text_input("Número")
        with col2:
            bairro = st.text_input("Bairro")
        # lat / lon
        c1, c2 = st.columns(2)
        with c1:
            lat = st.text_input("Latitude (use ponto)")
        with c2:
            lon = st.text_input("Longitude (use ponto)")
        descricao = st.text_area("Descrição")
        observacao = st.text_area("Observação (aparecerá na OS)")
        imagens = st.file_uploader("Imagens (várias)", accept_multiple_files=True, type=['png','jpg','jpeg'])
        submitted = st.form_submit_button("Salvar denúncia")

        if submitted:
            # validações e conversões
            lat_f = safe_float(lat)
            lon_f = safe_float(lon)
            seq = next_seq()
            code = make_code(seq)
            created_date = datetime.now().strftime("%Y-%m-%d")
            created_time = datetime.now().strftime("%H:%M:%S")

            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO denuncias (code,tipo,rua,numero,bairro,lat,lon,descricao,observacao,created_date,created_time)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (code, tipo, rua, numero, bairro, lat_f, lon_f, descricao, observacao, created_date, created_time))
            denuncia_id = cur.lastrowid
            conn.commit()
            conn.close()

            if imagens:
                save_images_files(denuncia_id, imagens)

            st.success(f"Denúncia salva: {code}")
            st.experimental_rerun()

# ---------- Pesquisar / Editar ----------
else:
    st.header("Pesquisar / Editar / Excluir")

    # search box
    q = st.text_input("Pesquisar por código, bairro ou rua (parte do texto)")

    conn = get_conn()
    cur = conn.cursor()
    if q and q.strip():
        like = f"%{q.strip()}%"
        cur.execute("SELECT id,code,tipo,rua,numero,bairro,created_date,created_time FROM denuncias WHERE code LIKE ? OR bairro LIKE ? OR rua LIKE ? ORDER BY id DESC", (like,like,like))
    else:
        cur.execute("SELECT id,code,tipo,rua,numero,bairro,created_date,created_time FROM denuncias ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()

    st.write(f"Registros encontrados: {len(rows)}")

    for row in rows:
        den_id = row[0]
        code = row[1]
        tipo = row[2]
        rua = row[3]
        numero = row[4]
        bairro = row[5]
        created_date = row[6]
        created_time = row[7]

        with st.expander(f"{code} — {tipo} — {bairro} — {rua}, {numero}  ({created_date} {created_time})"):
            # show small summary
            st.write(f"Endereço: {rua}, {numero} — {bairro}")
            # buttons: editar, excluir, pdf
            c1, c2, c3 = st.columns([1,1,1])
            if c1.button("Editar", key=f"edit_{den_id}"):
                st.session_state["edit_id"] = den_id
                st.experimental_rerun()
            if c2.button("Excluir", key=f"del_{den_id}"):
                # confirmar
                if st.confirm(f"Confirma exclusão de {code} ?"):
                    delete_denuncia_and_files(den_id)
                    st.success("Excluído.")
                    st.experimental_rerun()
            if c3.button("Gerar PDF", key=f"pdf_{den_id}"):
                # carregar dados completos
                conn = get_conn()
                cur = conn.cursor()
                cur.execute("SELECT id,code,tipo,rua,numero,bairro,lat,lon,descricao,observacao,created_date,created_time FROM denuncias WHERE id=?", (den_id,))
                row_full = cur.fetchone()
                cur.execute("SELECT filename FROM imagens WHERE denuncia_id=?", (den_id,))
                img_rows = cur.fetchall()
                conn.close()
                den = row_to_dict(row_full)
                img_paths = [os.path.join(UPLOAD_ROOT, str(den_id), r[0]) for r in img_rows]
                pdf_bytes = generate_pdf(den, img_paths)
                st.download_button("Download PDF", pdf_bytes, file_name=f"{den['code']}.pdf", mime="application/pdf")

    # Edição (form)
    if "edit_id" in st.session_state:
        edit_id = st.session_state["edit_id"]
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id,code,tipo,rua,numero,bairro,lat,lon,descricao,observacao,created_date,created_time FROM denuncias WHERE id=?", (edit_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            st.error("Registro não encontrado.")
            del st.session_state["edit_id"]
            st.experimental_rerun()
        den = row_to_dict(row)
        st.subheader(f"Editando {den['code']}")

        with st.form("form_edit"):
            tipo = st.selectbox("Tipo de denúncia", ["Urbana", "Ambiental"], index=0 if den['tipo']=="Urbana" else 1)
            rua = st.text_input("Rua", den['rua'])
            col1, col2 = st.columns([1,6])
            with col1:
                numero = st.text_input("Número", den['numero'])
            with col2:
                bairro = st.text_input("Bairro", den['bairro'])
            c1, c2 = st.columns(2)
            with c1:
                lat = st.text_input("Latitude", "" if den['lat'] is None else str(den['lat']))
            with c2:
                lon = st.text_input("Longitude", "" if den['lon'] is None else str(den['lon']))
            descricao = st.text_area("Descrição", den['descricao'])
            observacao = st.text_area("Observação", den['observacao'])
            novas_imagens = st.file_uploader("Adicionar novas imagens", accept_multiple_files=True)
            submitted = st.form_submit_button("Salvar alterações")
            cancel = st.form_submit_button("Cancelar")

            if submitted:
                lat_f = safe_float(lat)
                lon_f = safe_float(lon)
                conn = get_conn()
                cur = conn.cursor()
                cur.execute("""
                    UPDATE denuncias SET tipo=?, rua=?, numero=?, bairro=?, lat=?, lon=?, descricao=?, observacao=?
                    WHERE id=?
                """, (tipo, rua, numero, bairro, lat_f, lon_f, descricao, observacao, edit_id))
                conn.commit()
                conn.close()

                if novas_imagens:
                    save_images_files(edit_id, novas_imagens)

                st.success("Alterado com sucesso.")
                del st.session_state["edit_id"]
                st.experimental_rerun()

            if cancel:
                del st.session_state["edit_id"]
                st.experimental_rerun()
