import streamlit as st
import sqlite3
import os
from datetime import datetime
from PIL import Image
import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import base64

# ============================
#     CONFIGURAÇÕES
# ============================

st.set_page_config(page_title="Denúncias", layout="wide")

DB_PATH = "denuncias.db"
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ============================
#     BANCO DE DADOS
# ============================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS denuncias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        code TEXT UNIQUE
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS imagens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        denuncia_id INTEGER,
        filename TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()

def get_conn():
    return sqlite3.connect(DB_PATH)

# ============================
#     PDF
# ============================

def gerar_pdf(denuncia, imagens):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    x = 50
    y = 800

    c.setFont("Helvetica-Bold", 14)
    c.drawString(x, y, f"Ordem de Serviço - {denuncia['code']}")
    y -= 30

    c.setFont("Helvetica", 11)
    for campo, valor in denuncia.items():
        if campo in ["id", "code"]:
            continue
        c.drawString(x, y, f"{campo.capitalize()}: {valor}")
        y -= 18
        if y < 100:
            c.showPage()
            y = 800

    y -= 20
    c.drawString(x, y, "IMAGENS:")
    y -= 20

    for img_path in imagens:
        try:
            c.drawInlineImage(img_path, x, y - 150, width=200, height=150)
            y -= 170
        except:
            pass

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.read()

# ============================
#     GELOCALIZAÇÃO JS
# ============================

GEO_JS = """
<script>
function pegarLocalizacao(){
    navigator.geolocation.getCurrentPosition(function(pos){
        const lat = pos.coords.latitude;
        const lon = pos.coords.longitude;

        const streamlitSend = window.parent.postMessage;
        streamlitSend({lat: lat, lon: lon}, "*");
    });
}
</script>
<button onclick="pegarLocalizacao()">📍 Obter Localização</button>
"""

# ============================
#     FUNÇÕES AUXILIARES
# ============================

def salvar_denuncia(data, imagens):
    conn = get_conn()
    cur = conn.cursor()

    code = f"DEN-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    cur.execute("""
        INSERT INTO denuncias 
        (tipo,rua,numero,bairro,cidade,estado,cep,lat,lon,descricao,observacao,code)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        data["tipo"], data["rua"], data["numero"], data["bairro"], data["cidade"], data["estado"],
        data["cep"], data["lat"], data["lon"], data["descricao"], data["observacao"], code
    ))

    denuncia_id = cur.lastrowid

    # salva imagens
    folder = os.path.join(UPLOAD_DIR, str(denuncia_id))
    os.makedirs(folder, exist_ok=True)

    for img in imagens:
        path = os.path.join(folder, img.name)
        with open(path, "wb") as f:
            f.write(img.getbuffer())

        cur.execute("INSERT INTO imagens (denuncia_id, filename) VALUES (?,?)",
                    (denuncia_id, img.name))

    conn.commit()
    conn.close()

def carregar_denuncias():
    conn = get_conn()
    df = conn.execute("SELECT * FROM denuncias ORDER BY id DESC").fetchall()
    conn.close()
    return df

def carregar_uma(id_):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT * FROM denuncias WHERE id=?", (id_,))
    row = cur.fetchone()

    cur.execute("SELECT filename FROM imagens WHERE denuncia_id=?", (id_,))
    imgs = cur.fetchall()

    conn.close()

    return row, imgs

def excluir(id_):
    conn = get_conn()
    conn.execute("DELETE FROM denuncias WHERE id=?", (id_,))
    conn.execute("DELETE FROM imagens WHERE denuncia_id=?", (id_,))
    conn.commit()
    conn.close()

# ============================
#     INTERFACE
# ============================

menu = st.sidebar.selectbox("Menu", ["Registrar", "Pesquisar/Editar"])

# ---------------------------------------------------------
# REGISTRAR
# ---------------------------------------------------------
if menu == "Registrar":
    st.title("Registrar Denúncia")

    tipo = st.selectbox("Tipo", ["Urbana", "Ambiental"])
    rua = st.text_input("Rua")
    numero = st.text_input("Número")
    bairro = st.text_input("Bairro")
    cidade = st.text_input("Cidade")
    estado = st.text_input("Estado")
    cep = st.text_input("CEP")

    col1, col2 = st.columns(2)
    with col1:
        lat = st.text_input("Latitude")
    with col2:
        lon = st.text_input("Longitude")

    st.markdown(GEO_JS, unsafe_allow_html=True)

    descricao = st.text_area("Descrição")
    observacao = st.text_area("Observação")
    imagens = st.file_uploader("Imagens", accept_multiple_files=True)

    if st.button("Salvar"):
        # conversão segura
        def conv(v):
            if not v:
                return None
            v = v.replace(",", ".")
            try:
                return float(v)
            except:
                return None

        data = {
            "tipo": tipo,
            "rua": rua,
            "numero": numero,
            "bairro": bairro,
            "cidade": cidade,
            "estado": estado,
            "cep": cep,
            "lat": conv(lat),
            "lon": conv(lon),
            "descricao": descricao,
            "observacao": observacao
        }

        salvar_denuncia(data, imagens or [])
        st.success("Denúncia salva!")

# ---------------------------------------------------------
# PESQUISAR / EDITAR
# ---------------------------------------------------------
else:
    st.title("Pesquisar / Editar / Excluir")

    denuncias = carregar_denuncias()
    for d in denuncias:
        with st.expander(f"{d[12]} — {d[3]} ({d[4]})"):
            st.write(f"Descrição: {d[10]}")

            col1, col2, col3 = st.columns(3)

            if col1.button("Editar", key=f"edit_{d[0]}"):
                st.session_state["editar"] = d[0]

            if col2.button("Excluir", key=f"del_{d[0]}"):
                excluir(d[0])
                st.warning("Denúncia excluída!")
                st.experimental_rerun()

            if col3.button("PDF", key=f"pdf_{d[0]}"):
                row, imgs = carregar_uma(d[0])
                img_paths = [os.path.join(UPLOAD_DIR, str(d[0]), i[0]) for i in imgs]
                pdf = gerar_pdf(
                    {
                        "id": row[0],
                        "tipo": row[1],
                        "rua": row[2],
                        "numero": row[3],
                        "bairro": row[4],
                        "cidade": row[5],
                        "estado": row[6],
                        "cep": row[7],
                        "lat": row[8],
                        "lon": row[9],
                        "descricao": row[10],
                        "observacao": row[11],
                        "code": row[12]
                    },
                    img_paths
                )
                st.download_button("Baixar PDF", pdf, file_name=f"{row[12]}.pdf")

    # editar tela
    if "editar" in st.session_state:

        den_id = st.session_state["editar"]
        row, imgs = carregar_uma(den_id)

        st.subheader(f"Editando {row[12]}")

        tipo = st.selectbox("Tipo", ["Urbana", "Ambiental"], index=0 if row[1]=="Urbana" else 1)
        rua = st.text_input("Rua", row[2])
        numero = st.text_input("Número", row[3])
        bairro = st.text_input("Bairro", row[4])
        cidade = st.text_input("Cidade", row[5])
        estado = st.text_input("Estado", row[6])
        cep = st.text_input("CEP", row[7])
        lat = st.text_input("Latitude", str(row[8] or ""))
        lon = st.text_input("Longitude", str(row[9] or ""))
        descricao = st.text_area("Descrição", row[10])
        observacao = st.text_area("Observação", row[11])

        novas_imgs = st.file_uploader("Adicionar imagens", accept_multiple_files=True)

        if st.button("Salvar alterações"):

            def conv(v):
                if not v:
                    return None
                v = v.replace(",", ".")
                try:
                    return float(v)
                except:
                    return None

            conn = get_conn()
            conn.execute("""
                UPDATE denuncias SET
                tipo=?, rua=?, numero=?, bairro=?, cidade=?, estado=?, cep=?, lat=?, lon=?, descricao=?, observacao=?
                WHERE id=?
            """, (
                tipo, rua, numero, bairro, cidade, estado, cep,
                conv(lat), conv(lon), descricao, observacao,
                den_id
            ))
            conn.commit()

            if novas_imgs:
                folder = os.path.join(UPLOAD_DIR, str(den_id))
                os.makedirs(folder, exist_ok=True)
                for img in novas_imgs:
                    path = os.path.join(folder, img.name)
                    with open(path, "wb") as f:
                        f.write(img.getbuffer())
                    conn.execute("INSERT INTO imagens (denuncia_id,filename) VALUES (?,?)",
                                (den_id, img.name))

            conn.commit()
            conn.close()

            del st.session_state["editar"]
            st.success("Alterado com sucesso!")
            st.experimental_rerun()

        if st.button("Cancelar edição"):
            del st.session_state["editar"]
            st.experimental_rerun()
