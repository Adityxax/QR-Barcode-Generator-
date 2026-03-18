from flask import Flask, render_template, request, send_file, jsonify
import qrcode
from qrcode.image.styledpil import StyledPilImage
import barcode
from barcode.writer import ImageWriter
from PIL import Image
from pyzbar.pyzbar import decode
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import csv
import io
import os
import uuid

app = Flask(__name__)
GENERATED_DIR = "static/generated"
UPLOAD_DIR = "uploads"
os.makedirs(GENERATED_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ──────────────────────────────────────────────
# HOME
# ──────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


# ──────────────────────────────────────────────
# GENERATE QR CODE
# ──────────────────────────────────────────────
@app.route("/generate/qr", methods=["POST"])
def generate_qr():
    data        = request.form.get("data", "").strip()
    fill_color  = request.form.get("fill_color", "#000000")
    back_color  = request.form.get("back_color", "#ffffff")
    error_level = request.form.get("error_level", "M")

    if not data:
        return jsonify({"error": "No data provided"}), 400

    ec_map = {"L": qrcode.constants.ERROR_CORRECT_L,
              "M": qrcode.constants.ERROR_CORRECT_M,
              "Q": qrcode.constants.ERROR_CORRECT_Q,
              "H": qrcode.constants.ERROR_CORRECT_H}

    qr = qrcode.QRCode(
        version=1,
        error_correction=ec_map.get(error_level, qrcode.constants.ERROR_CORRECT_M),
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color=fill_color, back_color=back_color)

    filename = f"qr_{uuid.uuid4().hex}.png"
    filepath = os.path.join(GENERATED_DIR, filename)
    img.save(filepath)

    return jsonify({"image_url": f"/static/generated/{filename}", "filename": filename})


# ──────────────────────────────────────────────
# GENERATE BARCODE
# ──────────────────────────────────────────────
@app.route("/generate/barcode", methods=["POST"])
def generate_barcode():
    data        = request.form.get("data", "").strip()
    format_type = request.form.get("format", "code128")

    if not data:
        return jsonify({"error": "No data provided"}), 400

    try:
        barcode_class = barcode.get_barcode_class(format_type)
        bc            = barcode_class(data, writer=ImageWriter())
        filename_base = f"barcode_{uuid.uuid4().hex}"
        filepath      = os.path.join(GENERATED_DIR, filename_base)
        bc.save(filepath)
        filename = filename_base + ".png"
        return jsonify({"image_url": f"/static/generated/{filename}", "filename": filename})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ──────────────────────────────────────────────
# DECODE QR / BARCODE FROM IMAGE
# ──────────────────────────────────────────────
@app.route("/decode", methods=["POST"])
def decode_code():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    file = request.files["image"]
    img  = Image.open(file.stream)
    decoded = decode(img)

    if not decoded:
        return jsonify({"error": "No QR or barcode found in image"}), 404

    results = [{"type": d.type, "data": d.data.decode("utf-8")} for d in decoded]
    return jsonify({"results": results})


# ──────────────────────────────────────────────
# BATCH GENERATION FROM CSV
# ──────────────────────────────────────────────
@app.route("/batch", methods=["POST"])
def batch_generate():
    if "csv_file" not in request.files:
        return jsonify({"error": "No CSV uploaded"}), 400

    code_type = request.form.get("type", "qr")
    file      = request.files["csv_file"]
    stream    = io.StringIO(file.stream.read().decode("utf-8"))
    reader    = csv.reader(stream)

    filenames = []
    for row in reader:
        if not row:
            continue
        data = row[0].strip()
        if not data:
            continue

        if code_type == "qr":
            qr  = qrcode.make(data)
            fname = f"batch_qr_{uuid.uuid4().hex}.png"
            qr.save(os.path.join(GENERATED_DIR, fname))
        else:
            try:
                bc    = barcode.get("code128", data, writer=ImageWriter())
                base  = f"batch_bc_{uuid.uuid4().hex}"
                bc.save(os.path.join(GENERATED_DIR, base))
                fname = base + ".png"
            except Exception:
                continue

        filenames.append({"data": data, "filename": fname,
                          "image_url": f"/static/generated/{fname}"})

    return jsonify({"results": filenames})


# ──────────────────────────────────────────────
# DOWNLOAD AS PDF
# ──────────────────────────────────────────────
@app.route("/download/pdf/<filename>")
def download_pdf(filename):
    img_path = os.path.join(GENERATED_DIR, filename)
    if not os.path.exists(img_path):
        return "File not found", 404

    pdf_buffer = io.BytesIO()
    c = canvas.Canvas(pdf_buffer, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, height - 60, "Generated Code")
    c.drawImage(img_path, (width - 250) / 2, height - 350, width=250, height=250)
    c.setFont("Helvetica", 10)
    c.drawCentredString(width / 2, height - 380, f"File: {filename}")
    c.save()

    pdf_buffer.seek(0)
    return send_file(pdf_buffer, mimetype="application/pdf",
                     as_attachment=True, download_name=filename.replace(".png", ".pdf"))


# ──────────────────────────────────────────────
# DOWNLOAD PNG
# ──────────────────────────────────────────────
@app.route("/download/png/<filename>")
def download_png(filename):
    filepath = os.path.join(GENERATED_DIR, filename)
    if not os.path.exists(filepath):
        return "File not found", 404
    return send_file(filepath, as_attachment=True, download_name=filename)


if __name__ == "__main__":
    app.run(debug=True)
