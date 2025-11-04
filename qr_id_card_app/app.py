import os, json
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
import qrcode
import gspread
from google.oauth2.service_account import Credentials
from io import BytesIO
from PIL import Image
import pathlib

# Configuration
EXCEL_SHEET_ID_ENV = "SHEET_ID"
SERVICE_JSON_ENV = "SERVICE_ACCOUNT_JSON"
QR_FOLDER = "static/qrcodes"
FIELDS = [
    "GP_No", "Name", "Working Location", "Present Street Address", "Gender", "Age",
    "Emergency Contact No", "Blood Group", "Height", "Weight", "Blood Sugar",
    "Blood Pressure", "Major Operations", "Training Attended"
]

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "change_this")
pathlib.Path(QR_FOLDER).mkdir(parents=True, exist_ok=True)

def get_sheet():
    sa_json = os.environ.get(SERVICE_JSON_ENV)
    sheet_id = os.environ.get(EXCEL_SHEET_ID_ENV)
    if not sa_json or not sheet_id:
        raise RuntimeError("SERVICE_ACCOUNT_JSON or SHEET_ID not set in environment.")
    creds_dict = json.loads(sa_json)
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheet_id)
    ws = sh.sheet1
    return ws

def ensure_headers():
    ws = get_sheet()
    headers = ws.row_values(1)
    if not headers or len(headers) < len(FIELDS):
        ws.update('A1', [FIELDS])

def row_to_dict(row_vals):
    d = {}
    for i, key in enumerate(FIELDS):
        d[key] = row_vals[i] if i < len(row_vals) else ""
    return d

def find_row_by_gp(gp):
    ws = get_sheet()
    col = ws.col_values(1)
    for idx, val in enumerate(col, start=1):
        if str(val).strip() == str(gp).strip():
            return idx
    return None

@app.route('/', methods=['GET','POST'])
def index():
    if request.method == 'POST':
        gp = request.form.get('gp_no','').strip()
        if not gp:
            flash('Enter GP No','error')
            return redirect(url_for('index'))
        return redirect(url_for('edit', gp_no=gp))
    return render_template('index.html')

@app.route('/edit/<gp_no>', methods=['GET','POST'])
def edit(gp_no):
    ensure_headers()
    ws = get_sheet()
    row_idx = find_row_by_gp(gp_no)
    existing = None
    if row_idx:
        existing = row_to_dict(ws.row_values(row_idx))
    if request.method == 'POST':
        data = [ request.form.get(f,'').strip() for f in FIELDS ]
        if row_idx:
            ws.update(f'A{row_idx}', [data])
        else:
            ws.append_row(data, value_input_option='USER_ENTERED')
        # generate QR linking to card
        host_url = request.host_url.rstrip('/')
        card_url = f"{host_url}{url_for('card', gp_no=gp_no).lstrip('/')}"
        qr = qrcode.QRCode(version=2, box_size=8, border=3)
        qr.add_data(card_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white').convert('RGB')
        img.save(os.path.join(QR_FOLDER, f"{gp_no}.png"))
        flash('Saved and QR generated', 'success')
        return redirect(url_for('index'))
    return render_template('edit.html', gp_no=gp_no, existing=existing, fields=FIELDS)

@app.route('/card/<gp_no>')
def card(gp_no):
    ws = get_sheet()
    row_idx = find_row_by_gp(gp_no)
    if not row_idx:
        return render_template('card_not_found.html', gp_no=gp_no), 404
    data = row_to_dict(ws.row_values(row_idx))
    return render_template('card.html', data=data)

@app.route('/qrcode/<gp_no>')
def qrcode_image(gp_no):
    path = os.path.join(QR_FOLDER, f"{gp_no}.png")
    if not os.path.exists(path):
        return 'Not found', 404
    return send_from_directory(QR_FOLDER, f"{gp_no}.png")

if __name__ == '__main__':
    # for local dev, allow service_account.json file
    if os.path.exists('service_account.json') and not os.environ.get(SERVICE_JSON_ENV):
        with open('service_account.json','r',encoding='utf-8') as f:
            os.environ[SERVICE_JSON_ENV] = f.read()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',5000)), debug=True)
