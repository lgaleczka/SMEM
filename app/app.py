import os
from flask import Flask, render_template, request, redirect, url_for, send_file, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

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


# ROUTE: Upload plików dla blachy (PDF, DXF, zdjęcie)
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

        # Upload zdjęcia
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
            m = MaterialOption.query.get(self.material_id)
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




# ROUTES DLA OFERTY / ZAMÓWIEŃ

# Route: Generowanie oferty - tutaj możemy pozostawić prosty widok oferty (alternatywnie używamy offer_override)
@app.route('/offer', methods=['GET', 'POST'])
def offer():
    all_sheets = Blacha.query.all()
    # Here override_ids can be taken from session, if needed.
    override_ids = set(session.get('override_ids', []))
    offer_items = [b for b in all_sheets if (b.stan_obecny < b.stan_potrzebny) or (b.id in override_ids)]
    return render_template('offer.html', offer_items=offer_items, override_ids=override_ids)


# Route: Offer Override - user enters override quantities for selected sheets.
@app.route('/offer_override', methods=['POST'])
def offer_override():
    override_ids = request.form.getlist("override")
    if not override_ids:
        flash("Nie wybrano żadnych blach do oferty!")
        return redirect(url_for('index'))
    try:
        override_ids = [int(x) for x in override_ids]
    except ValueError:
        override_ids = []
    sheets = Blacha.query.filter(Blacha.id.in_(override_ids)).all()
    # Zapisujemy wybrane ID do sesji
    session['override_ids'] = override_ids
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

    # Build list of sheets: those with shortage or that are in override_data
    all_sheets = Blacha.query.all()
    offer_items = [b for b in all_sheets if (b.stan_obecny < b.stan_potrzebny) or (b.id in override_data)]

    if not offer_items:
        flash("Brak blach do oferty!")
        return redirect(url_for('index'))

    header = "Oferta Na Braki:\n"
    separator = "----------------------------------------------------------\n"
    col_headers = "{:<4}{:<8}{:<12}{:<10}{:<15}\n".format("lp.", "KOD", "Materiał", "Grubość", "Brak (szt.)")
    content = header + separator + col_headers + separator
    for i, b in enumerate(offer_items, start=1):
        if b.id in override_data and override_data[b.id] is not None:
            missing_str = f"{override_data[b.id]} szt."
        else:
            missing = b.stan_potrzebny - b.stan_obecny
            missing_str = f"{missing} szt."
        content += "{:<4}{:<8}{:<12}{:<10}{:<15}\n".format(i, b.kod, b.material or '-', b.grubosc or '-', missing_str)

    txt_path = os.path.join(app.config['UPLOAD_FOLDER'], 'oferta_braki.txt')
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(content)

    # For simplicity, send the file for download.
    return send_file(txt_path, as_attachment=True)


# Route: Orders - display order summary from override data.
@app.route('/orders', methods=['GET', 'POST'])
def orders():
    if request.method == 'POST':
        # Pobierz wybrane ID z sesji
        sheet_ids = session.get('override_ids', [])
        order_items = []
        for sid in sheet_ids:
            sheet = Blacha.query.get(int(sid))
            override_qty = request.form.get(f"override_qty_{sid}")
            if override_qty and override_qty.strip():
                try:
                    qty = int(override_qty)
                except ValueError:
                    qty = sheet.stan_potrzebny - sheet.stan_obecny
            else:
                qty = sheet.stan_potrzebny - sheet.stan_obecny
            order_items.append({'sheet': sheet, 'qty': qty})
        session['order_items'] = [(item['sheet'].id, item['qty']) for item in order_items]
        return render_template('orders.html', order_items=order_items)
    else:
        order_data = session.get('order_items', [])
        if not order_data:
            flash("Brak danych zamówienia. Wygeneruj ofertę najpierw.")
            return redirect(url_for('index'))
        order_items = []
        for sid, qty in order_data:
            sheet = Blacha.query.get(sid)
            order_items.append({'sheet': sheet, 'qty': qty})
        return render_template('orders.html', order_items=order_items)



# Confirm Order Route - update stock based on confirmed order.
@app.route('/confirm_order', methods=['POST'])
def confirm_order():
    order_sheet_ids = request.form.getlist("order_sheet_id")
    for sid in order_sheet_ids:
        sheet = Blacha.query.get(int(sid))
        override_qty = request.form.get(f"order_qty_{sid}")
        try:
            qty = int(override_qty)
        except (ValueError, TypeError):
            qty = 0
        sheet.stan_obecny += qty
    db.session.commit()
    flash("Zamówienie potwierdzone i stany zaktualizowane!")
    return redirect(url_for('index'))


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


@app.route('/files/<filename>')
def uploaded_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    return send_file(file_path)


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
