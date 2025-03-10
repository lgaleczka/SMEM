import os
import shutil
import zipfile
from flask import Flask, render_template, request, redirect, url_for, send_file, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from datetime import datetime

ALLOWED_EXTENSIONS = {'pdf', 'dxf'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app = Flask(__name__)
# Używamy absolutnej ścieżki dla bazy danych w katalogu /data (poza /app)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////data/blachy.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Folder uploads – wewnątrz katalogu /app
upload_folder = os.path.join(app.root_path, 'uploads')
app.config['UPLOAD_FOLDER'] = upload_folder
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Ustawienie tajnego klucza
app.secret_key = 'your_secret_key'

db = SQLAlchemy(app)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_image_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


# MODELE
class MaterialOption(db.Model):
    __tablename__ = 'material_option'
    id = db.Column(db.Integer, primary_key=True)
    nazwa = db.Column(db.String(100), unique=True, nullable=False)


class ThicknessOption(db.Model):
    __tablename__ = 'thickness_option'
    id = db.Column(db.Integer, primary_key=True)
    wartosc = db.Column(db.String(50), unique=True, nullable=False)


class Blacha(db.Model):
    __tablename__ = 'blacha'
    id = db.Column(db.Integer, primary_key=True)
    nazwa = db.Column(db.String(100), nullable=False)
    nazwa_prosta = db.Column(db.String(100), nullable=True)
    kod = db.Column(db.String(50), nullable=False, unique=True)
    stan_obecny = db.Column(db.Integer, nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey('material_option.id'), nullable=True)
    thickness_id = db.Column(db.Integer, db.ForeignKey('thickness_option.id'), nullable=True)
    rodzaj_obrobki = db.Column(db.String(50), nullable=True)
    pdf_filename = db.Column(db.String(200), nullable=True)
    dxf_filename = db.Column(db.String(200), nullable=True)
    image_filename = db.Column(db.String(200), nullable=True)
    project_items = db.relationship("ProjectItem", back_populates="blacha", lazy=True)

    @property
    def material(self):
        if self.material_id:
            m = db.session.get(MaterialOption, self.material_id)
            return m.nazwa if m else None
        return None

    @property
    def grubosc(self):
        if self.thickness_id:
            t = ThicknessOption.query.get(self.thickness_id)
            return t.wartosc if t else None
        return None

    @property
    def stan_potrzebny(self):
        return sum(item.ilosc for item in self.project_items if not item.fulfilled)


class Project(db.Model):
    __tablename__ = 'project'
    __table_args__ = {'extend_existing': True}
    id = db.Column(db.Integer, primary_key=True)
    nazwa = db.Column(db.String(100), nullable=False)
    items = db.relationship("ProjectItem", backref="project", lazy=True)

class ProjectItem(db.Model):
    __tablename__ = 'project_item'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    blacha_id = db.Column(db.Integer, db.ForeignKey("blacha.id"), nullable=False)
    ilosc = db.Column(db.Integer, nullable=False)
    fulfilled = db.Column(db.Boolean, default=False)
    blacha = db.relationship("Blacha", back_populates="project_items")

class Order(db.Model):
    __tablename__ = 'order'
    id = db.Column(db.Integer, primary_key=True)
    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship("OrderItem", backref="order", lazy=True)

class OrderItem(db.Model):
    __tablename__ = 'order_item'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    blacha_id = db.Column(db.Integer, db.ForeignKey("blacha.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    blacha = db.relationship("Blacha")

# ROUTES DLA OFERTY / ZAMÓWIEŃ

# Route: Generowanie oferty - tutaj możemy pozostawić prosty widok oferty (alternatywnie używamy offer_override)
@app.route('/orders', methods=['GET', 'POST'])
def orders():
    if request.method == 'POST':
        # Przetwarzamy dane z formularza override, zapisujemy je w sesji, itd.
        sheet_ids = session.get('override_ids', [])
        order_items = []
        for sid in sheet_ids:
            sheet = Blacha.query.get(int(sid))
            override_qty = request.form.get(f"order_qty_{sid}")
            try:
                qty = int(override_qty) if override_qty and override_qty.strip() else (sheet.stan_potrzebny - sheet.stan_obecny)
            except ValueError:
                qty = (sheet.stan_potrzebny - sheet.stan_obecny)
            if qty > 0:
                order_items.append({'sheet': sheet, 'qty': qty})
        session['order_items'] = [(item['sheet'].id, item['qty']) for item in order_items]
        return render_template('orders.html', order_items=order_items)
    else:
        order_data = session.get('order_items', [])
        if not order_data:
            # Zamiast przekierowywać, wyświetlamy pustą stronę z komunikatem:
            flash("Brak danych zamówienia. Wygeneruj ofertę najpierw.")
            return render_template('orders.html', order_items=[])
        order_items = []
        for sid, qty in order_data:
            sheet = Blacha.query.get(sid)
            if sheet and qty > 0:
                order_items.append({'sheet': sheet, 'qty': qty})
        return render_template('orders.html', order_items=order_items)


@app.route('/order_form', methods=['POST'])
def order_form():
    # Pobierz zaznaczone ID z głównego formularza
    override_ids = request.form.getlist("override")
    try:
        override_ids = [int(x) for x in override_ids]
    except ValueError:
        override_ids = []

    # Pobierz wszystkie blachy
    all_blachy = Blacha.query.all()

    # Automatycznie do zamówienia trafiają blachy z niedoborem
    shortage_blachy = [b for b in all_blachy if b.stan_obecny < b.stan_potrzebny]

    # Łączymy te z niedoborem z dodatkowymi (override_ids)
    combined_ids = set([b.id for b in shortage_blachy] + override_ids)

    # Ustal domyślną ilość dla każdej pozycji:
    # Dla blach z niedoborem: (stan_potrzebny - stan_obecny)
    # Dla dodatkowych (checkbox): domyślnie 1 (lub możesz ustalić inną wartość)
    order_items = {}
    for b in Blacha.query.filter(Blacha.id.in_(list(combined_ids))).all():
        if b.stan_obecny < b.stan_potrzebny:
            default_qty = b.stan_potrzebny - b.stan_obecny
        else:
            default_qty = 1
        order_items[b.id] = default_qty

    orders = []
    for b_id, qty in order_items.items():
        sheet = Blacha.query.get(b_id)
        orders.append({'sheet': sheet, 'qty': qty})

    session['order_items'] = [(item['sheet'].id, item['qty']) for item in orders]
    return render_template('order_form.html', order_items=orders)


@app.route('/export_order/<int:order_id>', methods=['GET'])
def export_order(order_id):
    order = Order.query.get_or_404(order_id)

    # Katalog bazowy eksportu – np. "exports" w folderze uploadów
    export_base = os.path.join(app.config['UPLOAD_FOLDER'], "exports")
    if not os.path.exists(export_base):
        os.makedirs(export_base)

    # Tworzymy unikalną nazwę folderu eksportu, np. "order_3_20250310_153045"
    folder_name = f"order_{order.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    export_folder = os.path.join(export_base, folder_name)
    os.makedirs(export_folder)

    # Generujemy plik TXT z ofertą
    header = "Oferta Na Braki:\n"
    separator = "----------------------------------------------------------\n"
    col_headers = "{:<4}{:<8}{:<12}{:<10}{:<15}\n".format("lp.", "KOD", "Materiał", "Grubość", "Brak (szt.)")
    content = header + separator + col_headers + separator
    for i, item in enumerate(order.items, start=1):
        sheet = item.blacha
        missing_str = f"{item.quantity} szt."
        content += "{:<4}{:<8}{:<12}{:<10}{:<15}\n".format(i, sheet.kod, sheet.material or '-', sheet.grubosc or '-',
                                                           missing_str)

    txt_path = os.path.join(export_folder, "oferta_braki.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(content)

    # Kopiujemy pliki DXF i PDF dla każdej pozycji, o ile istnieją
    for item in order.items:
        sheet = item.blacha
        if sheet.dxf_filename:
            src_dxf = os.path.join(app.config['UPLOAD_FOLDER'], sheet.dxf_filename)
            if os.path.exists(src_dxf):
                shutil.copy(src_dxf, export_folder)
        if sheet.pdf_filename:
            src_pdf = os.path.join(app.config['UPLOAD_FOLDER'], sheet.pdf_filename)
            if os.path.exists(src_pdf):
                shutil.copy(src_pdf, export_folder)

    # Tworzymy plik ZIP z zawartością folderu eksportu
    zip_filename = folder_name + ".zip"
    zip_path = os.path.join(export_base, zip_filename)
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(export_folder):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, export_folder)
                zipf.write(file_path, arcname)

    # Usuwamy tymczasowy folder eksportu
    shutil.rmtree(export_folder)

    # Wysyłamy plik ZIP do pobrania (przeglądarka otworzy okno pobierania)
    return send_file(zip_path, as_attachment=True)

# Route: Offer Override - user enters override quantities for selected sheets.
@app.route('/offer_override', methods=['POST'])
def offer_override():
    override_ids = request.form.getlist("override")
    if not override_ids:
        flash("Nie wybrano żadnych blach do zamówienia!")
        return redirect(url_for('index'))
    try:
        override_ids = [int(x) for x in override_ids]
    except ValueError:
        override_ids = []
    # Zapisujemy wybrane ID do sesji
    session['override_ids'] = override_ids
    # Pobieramy tylko wybrane blachy
    sheets = Blacha.query.filter(Blacha.id.in_(override_ids)).all()
    return render_template('offer_override.html', sheets=sheets)


# Route: Generate TXT Offer based on override quantities entered by user.
@app.route('/generate_txt', methods=['POST'])
def generate_txt():
    sheet_ids = request.form.getlist("sheet_ids")
    override_data = {}
    for sid in sheet_ids:
        qty_str = request.form.get(f"override_qty_{sid}")
        try:
            override_data[int(sid)] = int(qty_str) if qty_str and qty_str.strip() else None
        except ValueError:
            override_data[int(sid)] = None

    # Pobieramy wybrane blachy
    sheets = Blacha.query.filter(Blacha.id.in_(override_data.keys())).all()
    offer_items = []
    for b in sheets:
        default_qty = b.stan_potrzebny - b.stan_obecny
        qty = override_data.get(b.id) if override_data.get(b.id) is not None else default_qty
        # Dodajemy tylko, gdy ilość > 0
        if qty > 0:
            offer_items.append({'sheet': b, 'qty': qty})

    if not offer_items:
        flash("Brak blach do oferty!")
        return redirect(url_for('index'))

    # Generujemy treść oferty TXT
    header = "Oferta Na Braki:\n"
    separator = "----------------------------------------------------------\n"
    col_headers = "{:<4}{:<8}{:<12}{:<10}{:<15}\n".format("lp.", "KOD", "Materiał", "Grubość", "Brak (szt.)")
    content = header + separator + col_headers + separator
    for i, item in enumerate(offer_items, start=1):
        qty_str = f"{item['qty']} szt."
        content += "{:<4}{:<8}{:<12}{:<10}{:<15}\n".format(i, item['sheet'].kod, item['sheet'].material or '-', item['sheet'].grubosc or '-', qty_str)

    txt_path = os.path.join(app.config['UPLOAD_FOLDER'], 'oferta_braki.txt')
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(content)

    # Możesz przekierować do podsumowania zamówienia lub wysłać plik
    # Na przykład, zapisz dane zamówienia w sesji i przekieruj do /orders:
    session['order_items'] = [(item['sheet'].id, item['qty']) for item in offer_items]
    return redirect(url_for('orders'))

@app.route('/delete_order_item/<int:order_item_id>', methods=['POST'])
def delete_order_item(order_item_id):
    order_item = OrderItem.query.get_or_404(order_item_id)
    order_id = order_item.order_id
    db.session.delete(order_item)
    db.session.commit()
    flash("Pozycja zamówienia została usunięta.")
    return redirect(url_for('order_details', order_id=order_id))

@app.route('/delete_order/<int:order_id>', methods=['POST'])
def delete_order(order_id):
    order = Order.query.get_or_404(order_id)
    # Usuń wszystkie powiązane OrderItem
    for item in order.items:
        db.session.delete(item)
    db.session.delete(order)
    db.session.commit()
    flash("Zamówienie zostało usunięte.")
    return redirect(url_for('orders_list'))

# Confirm Order Route - update stock based on confirmed order.
@app.route('/confirm_order', methods=['POST'])
def confirm_order():
    # Pobierz przesłane ID blach
    order_sheet_ids = request.form.getlist("order_sheet_id")
    if not order_sheet_ids:
        flash("Brak pozycji w zamówieniu.")
        return redirect(url_for('order_form'))

    # Utwórz nowe zamówienie
    new_order = Order()
    db.session.add(new_order)

    # Dla każdej blachy pobierz zamówioną ilość
    for sid in order_sheet_ids:
        sheet = Blacha.query.get(int(sid))
        override_qty = request.form.get(f"order_qty_{sid}")
        try:
            qty = int(override_qty)
        except (ValueError, TypeError):
            qty = 0
        if qty > 0:
            # Dodajemy pozycję do zamówienia
            order_item = OrderItem(order=new_order, blacha_id=sheet.id, quantity=qty)
            db.session.add(order_item)
            # Aktualizacja stanu magazynowego – dodajemy zamówioną ilość
            sheet.stan_obecny += qty

    db.session.commit()
    # Czyścimy dane zamówienia z sesji
    session.pop('order_items', None)
    session.pop('override_ids', None)
    flash("Zamówienie potwierdzone, stany zaktualizowane!")
    return redirect(url_for('orders_list'))


@app.route('/orders_list')
def orders_list():
    orders = Order.query.order_by(Order.order_date.desc()).all()
    return render_template('orders_list.html', orders=orders)

@app.route('/order_details/<int:order_id>')
def order_details(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template('order_details.html', order=order)

# GŁÓWNE TRASY DLA BLACH
@app.route('/')
def index():
    blachy = Blacha.query.all()
    return render_template('index.html', blachy=blachy)


@app.route('/dodaj', methods=['GET', 'POST'])
def dodaj():
    if request.method == 'POST':
        nowa_blacha = Blacha(
            nazwa=request.form['nazwa'],
            nazwa_prosta=request.form['nazwa_prosta'],
            kod=request.form['kod'],
            stan_obecny=int(request.form['stan_obecny']),
            material_id=int(request.form['material_id']),
            thickness_id=int(request.form['thickness_id']),
            rodzaj_obrobki=request.form['rodzaj_obrobki']
        )
        db.session.add(nowa_blacha)
        db.session.commit()
        return redirect(url_for('index'))
    materials = MaterialOption.query.all()
    thicknesses = ThicknessOption.query.all()
    return render_template('dodaj.html', materials=materials, thicknesses=thicknesses)


@app.route('/materialy')
def materialy():
    materials = MaterialOption.query.all()
    thicknesses = ThicknessOption.query.all()
    return render_template('materialy.html', materials=materials, thicknesses=thicknesses)


@app.route('/materialy/dodaj_material', methods=['GET', 'POST'])
def dodaj_material():
    if request.method == 'POST':
        nazwa = request.form['nazwa']
        new_material = MaterialOption(nazwa=nazwa)
        db.session.add(new_material)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash("Błąd przy dodawaniu materiału: " + str(e))
        return redirect(url_for('materialy'))
    return render_template('dodaj_material.html')


@app.route('/materialy/dodaj_thickness', methods=['GET', 'POST'])
def dodaj_thickness():
    if request.method == 'POST':
        wartosc = request.form['wartosc']
        new_thickness = ThicknessOption(wartosc=wartosc)
        db.session.add(new_thickness)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash("Błąd przy dodawaniu grubości: " + str(e))
        return redirect(url_for('materialy'))
    return render_template('dodaj_thickness.html')


@app.route('/edytuj/<int:blacha_id>', methods=['GET', 'POST'])
def edytuj_blacha(blacha_id):
    blacha = Blacha.query.get_or_404(blacha_id)
    if request.method == 'POST':
        blacha.nazwa = request.form['nazwa']
        blacha.nazwa_prosta = request.form['nazwa_prosta']
        blacha.kod = request.form['kod']
        blacha.stan_obecny = int(request.form['stan_obecny'])
        blacha.material_id = int(request.form['material_id'])
        blacha.thickness_id = int(request.form['thickness_id'])
        blacha.rodzaj_obrobki = request.form['rodzaj_obrobki']
        db.session.commit()
        return redirect(url_for('index'))
    materials = MaterialOption.query.all()
    thicknesses = ThicknessOption.query.all()
    return render_template('edytuj.html', blacha=blacha, materials=materials, thicknesses=thicknesses)

@app.route('/projekty')
def projekty():
    projekty = Project.query.all()
    return render_template('projekty.html', projekty=projekty)

@app.route('/projekty/dodaj', methods=['GET', 'POST'], endpoint='dodaj_projekt')
def dodaj_projekt():
    if request.method == 'POST':
        nowy_projekt = Project(nazwa=request.form['nazwa'])
        db.session.add(nowy_projekt)
        db.session.commit()
        return redirect(url_for('projekty'))
    return render_template('dodaj_projekt.html')


@app.route('/projekty/<int:projekt_id>', methods=['GET', 'POST'])
def projekt_szczegoly(projekt_id):
    projekt = Project.query.get_or_404(projekt_id)
    if request.method == 'POST':
        # Odczytanie wybranej blachy oraz ilości
        try:
            blacha_id = int(request.form['blacha_id'])
            ilosc = int(request.form['ilosc'])
        except (KeyError, ValueError):
            flash("Niepoprawne dane formularza!")
            return redirect(url_for('projekt_szczegoly', projekt_id=projekt_id))

        # Dodajemy nowy wpis do projektu
        nowy_element = ProjectItem(project_id=projekt.id, blacha_id=blacha_id, ilosc=ilosc)
        db.session.add(nowy_element)
        db.session.commit()
        flash("Wpis został dodany do projektu!")
        return redirect(url_for('projekt_szczegoly', projekt_id=projekt.id))

    # Pobieramy wszystkie blachy, aby umożliwić wybór przy dodawaniu wpisu
    wszystkie_blachy = Blacha.query.all()
    return render_template('projekt_szczegoly.html', projekt=projekt, blachy=wszystkie_blachy)

@app.route('/projekty/item/edit/<int:item_id>', methods=['GET', 'POST'], endpoint='edit_project_item')
def edit_project_item(item_id):
    item = ProjectItem.query.get_or_404(item_id)
    if request.method == 'POST':
        item.blacha_id = int(request.form['blacha_id'])
        item.ilosc = int(request.form['ilosc'])
        db.session.commit()
        return redirect(url_for('projekt_szczegoly', projekt_id=item.project_id))
    all_blachy = Blacha.query.all()
    return render_template('edit_project_item.html', item=item, blachy=all_blachy)

@app.route('/projekty/item/delete/<int:item_id>', methods=['POST'], endpoint='delete_project_item')
def delete_project_item(item_id):
    item = ProjectItem.query.get_or_404(item_id)
    projekt_id = item.project_id
    db.session.delete(item)
    db.session.commit()
    flash("Wpis projektu został usunięty.")
    return redirect(url_for('projekt_szczegoly', projekt_id=projekt_id))


@app.route('/project/archive/<int:project_id>', methods=['POST'])
def archive_project(project_id):
    project = Project.query.get_or_404(project_id)
    for item in project.items:
        item.fulfilled = True
    # Optionally set an archive flag on project if needed
    # project.archived = True
    db.session.commit()
    flash("Projekt zarchiwizowany, zapotrzebowanie usunięte.")
    return redirect(url_for('projekty'))


@app.route('/usun/<int:blacha_id>', methods=['POST'])
def usun_blacha(blacha_id):
    blacha = Blacha.query.get_or_404(blacha_id)
    db.session.delete(blacha)
    db.session.commit()
    flash("Blacha została usunięta")
    return redirect(url_for('index'))


@app.route('/upload/<int:blacha_id>', methods=['GET', 'POST'])
def upload_file(blacha_id):
    blacha = Blacha.query.get_or_404(blacha_id)
    if request.method == 'POST':
        # Upload PDF
        if 'pdf' in request.files:
            file_pdf = request.files['pdf']
            if file_pdf and allowed_file(file_pdf.filename) and file_pdf.filename.lower().endswith('.pdf'):
                filename = secure_filename(file_pdf.filename)
                pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file_pdf.save(pdf_path)
                blacha.pdf_filename = filename

        # Upload DXF
        if 'dxf' in request.files:
            file_dxf = request.files['dxf']
            if file_dxf and allowed_file(file_dxf.filename) and file_dxf.filename.lower().endswith('.dxf'):
                filename = secure_filename(file_dxf.filename)
                dxf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file_dxf.save(dxf_path)
                blacha.dxf_filename = filename

        # Upload obrazu
        if 'image' in request.files:
            file_image = request.files['image']
            if file_image and allowed_image_file(file_image.filename):
                filename = secure_filename(file_image.filename)
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file_image.save(image_path)
                blacha.image_filename = filename

        db.session.commit()
        flash('Pliki zostały załadowane')
        return redirect(url_for('index'))

    return render_template('upload.html', blacha=blacha)

@app.route('/files/<filename>')
def uploaded_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    return send_file(file_path, mimetype='application/pdf', as_attachment=False)


if __name__ == '__main__':
    with app.app_context():
        # Create the database if it doesn't exist
        db.create_all()

        # Add material options if they don't exist
        if not MaterialOption.query.filter_by(nazwa="Stal").first():
            stal = MaterialOption(nazwa="Stal")
            db.session.add(stal)
        if not MaterialOption.query.filter_by(nazwa="Aluminium").first():
            aluminium = MaterialOption(nazwa="Aluminium")
            db.session.add(aluminium)
        db.session.commit()

        # Add thickness options if they don't exist
        if not ThicknessOption.query.filter_by(wartosc="3mm").first():
            t3mm = ThicknessOption(wartosc="3mm")
            db.session.add(t3mm)
        if not ThicknessOption.query.filter_by(wartosc="2mm").first():
            t2mm = ThicknessOption(wartosc="2mm")
            db.session.add(t2mm)
        if not ThicknessOption.query.filter_by(wartosc="5mm").first():
            t5mm = ThicknessOption(wartosc="5mm")
            db.session.add(t5mm)
        db.session.commit()

        # Seed example sheets only if none exist
        if Blacha.query.count() == 0:
            stal = MaterialOption.query.filter_by(nazwa="Stal").first()
            aluminium = MaterialOption.query.filter_by(nazwa="Aluminium").first()
            t3mm = ThicknessOption.query.filter_by(wartosc="3mm").first()
            t2mm = ThicknessOption.query.filter_by(wartosc="2mm").first()
            t5mm = ThicknessOption.query.filter_by(wartosc="5mm").first()

            przykładowe_blachy = [
                Blacha(nazwa="Blacha A", nazwa_prosta="kątownik", kod="A001", stan_obecny=10,
                       material_id=stal.id, thickness_id=t3mm.id, rodzaj_obrobki="CNC"),
                Blacha(nazwa="Blacha B", nazwa_prosta="płyta", kod="B001", stan_obecny=20,
                       material_id=aluminium.id, thickness_id=t2mm.id, rodzaj_obrobki="Palenie"),
                Blacha(nazwa="Blacha C", nazwa_prosta="blacha robocza", kod="C001", stan_obecny=5,
                       material_id=stal.id, thickness_id=t5mm.id, rodzaj_obrobki="Gięcie + Palenie"),
            ]
            db.session.add_all(przykładowe_blachy)
            db.session.commit()
    app.run(debug=True, host='0.0.0.0')
